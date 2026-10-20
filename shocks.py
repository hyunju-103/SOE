"""
Shock transmission engine. Shocks hit specific balance-sheet and income-
statement lines (not the Z-EM score directly) and are then rolled forward
through a simplified law of motion so effects compound across years. Every
simplifying assumption is documented inline and surfaced in the UI —
this is a policy-triage tool, not a precise multi-year forecast.

Transmission channels (see SOE_shock_framework.pdf, Section 3, extended
to FX/rate/revenue/arrears/refinancing per the boss-commissioned brief):
  - Fuel:      the fuel-cost increase phi * OpEx * fuel_oil_linkage * fuel_shock is first
               reduced by any end-user tariff increase (tariff_increase_pct * Revenue, or
               * max(0, Revenue - Government Grants) when tariff_revenue_base is
               "revenue_ex_grants" — policy Option B; 0 = Option A, tariff freeze).
               fuel_shock is fuel_shock_pct for shock_duration_years (step), or the
               year's value of fuel_shock_path when a per-year path is given (index 0 =
               projection year 1; zero beyond its end); the tariff increase applies in
               the fuel-shock years. What remains is split three ways:
               tariff_passthrough to customers (Case B), fuel_subsidy_share to the
               government (Case C — State compensation, reported as "Direct Fuel
               Subsidy"), and the rest absorbed by the SOE (Case A):
               ΔEBIT = -(phi * OpEx * fuel_shock - tariff increase) * (1 - tariff_passthrough - fuel_subsidy_share)
               With no tariff increase and fuel_subsidy_share = 0 this is the original formula.
  - Cash:      State compensation is recognised (it never hits EBIT), but only
               comp_paid_share of it arrives as cash in the year; the rest is a State
               compensation receivable, collected at comp_backlog_collected a year
               (comp_provision_share of it can be written off as a loss instead).
               Input VAT on the extra fuel bill that cannot be recovered
               (vat_rate * vat_trapped_share) is another cash outflow.
               Cash funding gap = -Net Income + Δreceivable + trapped VAT. Cash first:
               cash_buffer_share of it (capped at the opening "Cash and Equivalents"
               above a floor of cash_floor_opex_share * OpEx) is drawn from cash; the
               rest is borrowed: cash_gap_short_term_share in current liabilities (bank, or
               unpaid supplier bills for cash_gap_payables_share), the rest long-term.
               New bank and long-term debt carries new_debt_interest_rate (half a
               year on the year's draw). A cash surplus repays the short-term debt
               first, then rebuilds the cash drawn in earlier years. Defaults
               (config.DEFAULT_CASH_SETTINGS) reproduce the original model (everything
               paid in-year, gap funded long-term, no interest) except that an SOE
               reporting cash draws it down before borrowing; cash_buffer_share = 0
               restores borrow-everything.
  - FX (opex): ΔEBIT = -(fx_cost_share*OpEx - fx_revenue_share*Revenue) * fx_shock
  - Revenue:   ΔEBIT = revenue_elasticity * revenue_shock_pct * Revenue, where
               revenue_shock_pct = revenue_shock_std_devs * the SOE's own
               historical revenue-growth volatility (sector fallback if the
               SOE has under 3 years of data) — the standard DSA/DSF
               convention (default -1 std dev), not a flat percentage.
  - Rate:      ΔInterest = floating_debt_share * TotalLiabilities * rate_shock_bps/10000
  - Refinancing: ΔInterest += near_term_maturity_share * TotalLiabilities *
               refinancing_spread_bps/10000 — a maturity-wall shock, distinct
               from the floating-rate shock: this is rollover risk (the cost
               of refinancing debt coming due soon at a stressed spread), not
               the repricing of already-floating debt.
  - FX (debt): ΔEquity = -fx_debt_share * TotalLiabilities * fx_shock (revaluation)
  - Arrears:   ΔCurrentAssets = -arrears_pct_of_revenue * Revenue (receivables write-down proxy)

All shock magnitudes (fuel_shock_pct, fx_shock_pct, rate_shock_bps,
arrears_pct_of_revenue, refinancing_spread_bps) can be negative — a
favorable shock (cheaper fuel, currency appreciation, a rate cut, arrears
clearing) runs the same formulas in reverse. Slider ranges enforcing this
live on the Shock Scenarios page.

Simplifications flagged for future calibration:
  - Tax Expense held flat across the horizon; Current Liabilities move only
    through the short-term share of the cash funding gap (flat by default).
  - Net Income carries the reported figure plus the shock's incremental effect.
  - A cash shortfall is met from the opening cash buffer first (when the data
    report "Cash and Equivalents"), then borrowed. A loss that is borrowed leaves
    total assets unchanged and one paid from cash lowers them by the draw, so
    TA = TL + Equity holds; legacy_loss_assets=True restores the original rule,
    in which the loss also reduced total assets and no cash is drawn.
  - The model is annual; a payment delay is expressed as the share paid
    within the year (about 1 - delay_days / 365 for delays under a year).
  - Shocks apply at full magnitude for `shock_duration_years`, then EBIT/
    Interest revert to unshocked levels — but balance-sheet levels
    (debt, retained earnings, equity) that built up during the shock
    persist forward, which is what makes this "dynamic" rather than a
    one-off recomputation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import config
from calculations import classify_zem_from_values, compute_pd, compute_pd_from_rating


def run_scenario(base_row: pd.Series, params: dict, horizon_years: int) -> pd.DataFrame:
    """Project one SOE forward under a deterministic shock scenario.
    base_row: a row from the ingested data (post compute_zem_components),
    for a single SOE-year — the starting point for the projection.
    params: dict matching config.DEFAULT_SHOCK_PARAMS keys.
    Returns a DataFrame with one row per projection year (0 = base year,
    unshocked, through horizon_years), including recomputed Z-EM.
    """
    duration = params["shock_duration_years"]
    fpath = _fuel_path(params)  # per-year fuel price path, or None for the step profile
    cash0 = _num(base_row.get("Cash and Equivalents"), float("nan"))

    # Mutable state carried year to year
    state = {
        "EBIT": base_row["Operating Profits (EBIT)"],
        "Interest": base_row["Interest Expense"],
        "Tax": base_row["Tax Expense"],
        "RetainedEarnings": base_row["Retained Earnings"],
        "Equity": base_row["Equity"],
        "TotalLiabilities": base_row["Total Liabilities"],
        "TotalAssets": base_row["Total Assets"],
        "CurrentAssets": base_row["Current Assets"],
        "CurrentLiabilities": base_row["Current Liabilities"],
        "Depreciation": base_row["Depreciation"],
        "Revenue": base_row["Revenues"],
        "OpEx": base_row["Operating Expense"],
        # stocks created by the shock
        "Receivable": 0.0, "TrappedVAT": 0.0, "ShortTermDebt": 0.0, "SupplierArrears": 0.0, "LongTermDebt": 0.0,
        # illiquid items already in base-year current assets, where reported (held flat)
        "IlliquidOpen": _num(base_row.get("Government Arrears Owed"), 0.0) + _num(base_row.get("VAT Credits"), 0.0),
        # opening cash (0 when the data do not report it) and the drawdown not yet rebuilt
        "Cash": cash0 if np.isfinite(cash0) else 0.0, "CashDrawn": 0.0,
    }

    rows = []
    # Year 0: unshocked baseline
    rows.append(_snapshot(base_row["Entity"], base_row.get("Sector", ""), int(base_row["Year"]), 0, state,
                          {"ni": base_row["Net Income"]}))

    subsidy_share = params.get("fuel_subsidy_share", 0.0) or 0.0
    passthrough = params.get("tariff_passthrough", 0.0) or 0.0
    tariff_up = params.get("tariff_increase_pct", 0.0) or 0.0
    paid_share = _num(params.get("comp_paid_share"), 1.0)
    collect_share = _num(params.get("comp_backlog_collected"), 1.0)
    provision_share = _num(params.get("comp_provision_share"), 0.0)
    st_share = _num(params.get("cash_gap_short_term_share"), 0.0)
    ap_share = _num(params.get("cash_gap_payables_share"), 0.0)
    rate = _num(params.get("new_debt_interest_rate"), 0.0)
    vat_trap = _num(params.get("vat_rate"), 0.0) * _num(params.get("vat_trapped_share"), 0.0)
    k_int = 1 - st_share * ap_share  # share of new funding that bears interest (supplier arrears do not)
    eps = _num(params.get("fuel_oil_linkage"), 1.0)                 # share of the fuel bill that moves with the oil price
    ex_grants = params.get("tariff_revenue_base") == "revenue_ex_grants"
    grants = _num(base_row.get("Government Grants"), 0.0)           # compensation already booked in revenue
    buf = min(1.0, max(0.0, _num(params.get("cash_buffer_share"), 1.0)))
    floor = _num(params.get("cash_floor_opex_share"), 0.0)
    cash_live = bool(np.isfinite(cash0)) and buf > 0 and not params.get("legacy_loss_assets")

    for t in range(1, horizon_years + 1):
        active = t <= duration
        if fpath is None:                                                 # step: full magnitude while the shock is on
            p_fuel, fuel_active = params["fuel_shock_pct"], active
        else:                                                             # per-year path, zero beyond its end
            p_fuel = fpath[t - 1] if t <= len(fpath) else 0.0
            fuel_active = p_fuel != 0

        fuel_cost_increase = tariff_revenue = customer_share = compensation = trapped_vat = d_ebit_fuel = 0.0
        if fuel_active:
            fuel_cost_increase = params["fuel_cost_share"] * state["OpEx"] * eps * p_fuel
            tariff_base = max(0.0, state["Revenue"] - grants) if ex_grants else state["Revenue"]
            tariff_revenue = tariff_up * tariff_base                      # Option B: end-user tariff increase
            remaining = fuel_cost_increase - tariff_revenue               # left after the tariff increase
            if tariff_revenue > 0 and remaining < 0:
                d_ebit_fuel = -remaining                                  # tariff more than covers it: SOE keeps the excess
            else:
                customer_share = remaining * passthrough                 # Case B
                compensation = remaining * subsidy_share                 # Case C: State compensation recognised
                d_ebit_fuel = -remaining * max(0.0, 1 - passthrough - subsidy_share)  # Case A
            trapped_vat = max(0.0, fuel_cost_increase) * vat_trap
        if active:
            d_ebit_fx = -(params["fx_cost_share"] * state["OpEx"] - params["fx_revenue_share"] * state["Revenue"]) * params["fx_shock_pct"]
            d_ebit_revenue = params["revenue_elasticity"] * params.get("revenue_shock_pct", 0.0) * state["Revenue"]
            d_interest_rate = params["floating_debt_share"] * state["TotalLiabilities"] * (params["rate_shock_bps"] / 10000.0)
            d_interest_refi = params.get("near_term_maturity_share", 0.0) * state["TotalLiabilities"] * (params.get("refinancing_spread_bps", 0.0) / 10000.0)
            d_interest = d_interest_rate + d_interest_refi
            d_equity_fx_reval = -params["fx_debt_share"] * state["TotalLiabilities"] * params["fx_shock_pct"]
            d_current_assets_arrears = -params["arrears_pct_of_revenue"] * state["Revenue"]
        else:
            d_ebit_fx = d_ebit_revenue = 0.0
            d_interest = d_equity_fx_reval = d_current_assets_arrears = 0.0

        # State compensation: recognised vs. paid in cash
        paid_now = compensation * paid_share if compensation > 0 else compensation  # a saving is settled at once
        unpaid = compensation - paid_now
        provision = unpaid * provision_share                     # unpaid amount written off as a loss
        collected = state["Receivable"] * collect_share          # earlier years' unpaid compensation arriving now
        d_receivable = unpaid - provision - collected

        ebit_t = base_row["Operating Profits (EBIT)"] + d_ebit_fuel + d_ebit_fx + d_ebit_revenue
        # NI carries forward the SOE's ACTUAL reported Net Income, plus only
        # the shock's incremental effect — not a recomputation from
        # EBIT-Interest-Tax, which ignores other income/expense/tax-timing
        # items real statements have and drifted under zero shock as a
        # result. Under true zero shock (all deltas 0), NI_t = actual base
        # Net Income exactly, every year.
        d_ebit_total = d_ebit_fuel + d_ebit_fx + d_ebit_revenue
        interest_open = rate * (state["ShortTermDebt"] + state["LongTermDebt"])
        ni_before_new = base_row["Net Income"] + d_ebit_total - d_interest - provision - interest_open

        # cash the SOE has to find this year (negative = surplus)
        need = -ni_before_new + d_receivable + trapped_vat
        funding = interest_new = repaid = left_over = draw = rebuilt = 0.0
        if need > 0:
            if cash_live:                                        # cash first, down to the floor
                draw = min(need, max(0.0, state["Cash"] - floor * state["OpEx"])) * buf
            funding = (need - draw) / (1 - (k_int * rate) / 2)   # the rest borrowed, grossed up for half a year of interest
            interest_new = (rate * k_int * funding) / 2
        else:                                                    # surplus repays short-term debt first
            surplus = -need
            r_bank = min(surplus, state["ShortTermDebt"]); state["ShortTermDebt"] -= r_bank; surplus -= r_bank
            r_ap = min(surplus, state["SupplierArrears"]); state["SupplierArrears"] -= r_ap; surplus -= r_ap
            repaid = r_bank + r_ap
            left_over = surplus
            if cash_live:                                        # rebuilds the cash drawn in earlier years, no further
                rebuilt = min(left_over, state["CashDrawn"])
        net_income_t = ni_before_new - interest_new
        f_short = funding * st_share
        f_ap = f_short * ap_share
        f_bank = f_short - f_ap
        f_long = funding - f_short

        state["ShortTermDebt"] += f_bank
        state["SupplierArrears"] += f_ap
        state["LongTermDebt"] += f_long
        state["Receivable"] += d_receivable
        state["TrappedVAT"] += trapped_vat
        state["RetainedEarnings"] = state["RetainedEarnings"] + net_income_t
        state["Equity"] = state["Equity"] + net_income_t + d_equity_fx_reval
        state["CurrentLiabilities"] = state["CurrentLiabilities"] + (f_short - repaid)
        state["TotalLiabilities"] = state["TotalLiabilities"] + (funding - repaid - d_equity_fx_reval)
        state["CurrentAssets"] = state["CurrentAssets"] + (d_receivable + trapped_vat + d_current_assets_arrears)
        state["TotalAssets"] = state["TotalAssets"] + (d_receivable + trapped_vat + d_current_assets_arrears + left_over)
        if params.get("legacy_loss_assets") and need > 0:
            state["TotalAssets"] += min(0.0, net_income_t)       # original rule: a borrowed loss also cuts total assets
        if draw:                                                 # cash paid out leaves current and total assets
            state["Cash"] -= draw; state["CashDrawn"] += draw
            state["CurrentAssets"] -= draw; state["TotalAssets"] -= draw
        if rebuilt:                                              # part of the surplus (already in total assets) held as cash
            state["Cash"] += rebuilt; state["CashDrawn"] -= rebuilt
            state["CurrentAssets"] += rebuilt
        state["EBIT"] = ebit_t
        state["Interest"] = base_row["Interest Expense"] + d_interest + interest_open + interest_new

        flows = {"inc": fuel_cost_increase, "tariff": tariff_revenue, "cust": customer_share, "comp": compensation,
                 "paid": paid_now + collected, "provision": provision, "vat": trapped_vat, "fund": funding, "draw": draw,
                 "interest_new": interest_open + interest_new, "ni": net_income_t}
        rows.append(_snapshot(base_row["Entity"], base_row.get("Sector", ""), int(base_row["Year"]) + t, t, state, flows))

    return pd.DataFrame(rows)


def _num(v, default):
    """A finite number, or `default` (missing columns, NaN, None)."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return v if np.isfinite(v) else default


def _fuel_path(params):
    """The per-year fuel price path (list of floats, index 0 = projection year
    1), or None for the step profile: missing, empty, or a scalar (the
    zero-shock dicts put 0.0 in every magnitude)."""
    v = params.get("fuel_shock_path")
    if v is None or np.isscalar(v):
        return None
    v = [_num(x, 0.0) for x in v]
    return v or None


def _ratio(a, b):
    return a / b if b and np.isfinite(a) and np.isfinite(b) else float("nan")


def _snapshot(entity, sector, calendar_year, t, state, flows) -> dict:
    working_capital = state["CurrentAssets"] - state["CurrentLiabilities"]
    x1, x2, x3, x4, z, zone = classify_zem_from_values(
        working_capital=working_capital,
        total_assets=state["TotalAssets"],
        retained_earnings=state["RetainedEarnings"],
        ebit=state["EBIT"],
        equity=state["Equity"],
        total_liabilities=state["TotalLiabilities"],
    )
    illiquid = state["IlliquidOpen"] + state["Receivable"] + state["TrappedVAT"]
    f = lambda k: flows.get(k, 0.0)
    return {
        "Entity": entity,
        "Sector": sector,
        "Calendar Year": calendar_year,
        "Projection Year": t,
        "EBIT": state["EBIT"],
        "Interest Expense": state["Interest"],
        "Net Income": flows["ni"],
        "Retained Earnings": state["RetainedEarnings"],
        "Equity": state["Equity"],
        "Total Liabilities": state["TotalLiabilities"],
        "Total Assets": state["TotalAssets"],
        "Current Assets": state["CurrentAssets"],
        "Current Liabilities": state["CurrentLiabilities"],
        "X1": x1, "X2": x2, "X3": x3, "X4": x4,
        "Z_EM": z, "Zone": zone, "Rating": config.z_rating(z),
        # the government's recognised share of the fuel-cost change (Case C)
        "Direct Fuel Subsidy": f("comp"),
        # flows of the year
        "Fuel Cost Change": f("inc"),
        "Tariff Increase Revenue": f("tariff"),
        "Tariff Pass-through": f("cust"),
        "State Compensation Paid": f("paid"),          # cash from the budget this year
        "Compensation Provision": f("provision"),
        "Trapped VAT": f("vat"),
        "Cash Funding Gap": f("fund"),                 # borrowed, after any cash drawn
        "Cash Drawdown": f("draw"),                    # paid out of the opening cash buffer
        "Interest on New Debt": f("interest_new"),
        # stocks at year end
        "State Compensation Receivable": state["Receivable"],
        "Trapped VAT Credits": state["TrappedVAT"],
        "New Short-term Debt": state["ShortTermDebt"],
        "Supplier Arrears": state["SupplierArrears"],
        "New Long-term Debt": state["LongTermDebt"],
        "Cash": state["Cash"],
        # liquidity and solvency
        "Current Ratio": _ratio(state["CurrentAssets"], state["CurrentLiabilities"]),
        "Adjusted Current Ratio": _ratio(state["CurrentAssets"] - illiquid, state["CurrentLiabilities"]),
        "Debt to Assets": _ratio(state["TotalLiabilities"], state["TotalAssets"]),
    }


def kpi_impact_table(scenario_df: pd.DataFrame) -> pd.DataFrame:
    """Year-0 vs final-year comparison of Z-EM components, for the
    shock x KPI heatmap / tornado chart."""
    base = scenario_df.iloc[0]
    final = scenario_df.iloc[-1]
    rows = []
    for comp in config.ZEM_COEFFICIENTS:
        rows.append({
            "Component": config.ZEM_LABELS[comp],
            "Base value": base[comp],
            "Final value": final[comp],
            "Change": final[comp] - base[comp],
            "Weighted contribution to ΔZ": (final[comp] - base[comp]) * config.ZEM_COEFFICIENTS[comp],
        })
    return pd.DataFrame(rows)


def gdp_path(base_gdp: float, growth_rate: float, horizon_years: int) -> list:
    """Simple compounding GDP projection for the EFC/GDP path chart."""
    return [base_gdp * ((1 + growth_rate) ** t) for t in range(horizon_years + 1)]


MC_VARIABLES = ["fuel", "fx", "rate", "revenue"]


def mc_covariance(names, sds, correlations):
    """Covariance matrix for the drawn variables. correlations: dict keyed
    "a|b" (either order). Raises ValueError if the implied correlation
    matrix is not positive semi-definite."""
    k = len(names)
    corr = np.eye(k)
    for i in range(k):
        for j in range(i + 1, k):
            key1, key2 = f"{names[i]}|{names[j]}", f"{names[j]}|{names[i]}"
            corr[i, j] = corr[j, i] = correlations.get(key1, correlations.get(key2, 0.0))
    if np.linalg.eigvalsh(corr).min() < -1e-10:
        raise ValueError("The shock correlations are inconsistent (the correlation matrix is not positive semi-definite). Lower some of them.")
    sd = np.array([sds[n] for n in names])
    return corr * np.outer(sd, sd)


def run_monte_carlo(base_row: pd.Series, params: dict, n_sims: int, fuel_std: float,
                     fx_std: float, correlation: float, horizon_years: int,
                     lgd_pct: float, seed: int = 42, rate_std_bps: float = 0.0,
                     revenue_std_sd: float = 0.0, correlations: dict | None = None,
                     ead_share: float = 1.0) -> pd.DataFrame:
    """Draw correlated shock magnitudes and run the scenario for each draw.
    Fuel and FX are always drawn (centred on the slider values; with a fuel
    price path, fuel is centred on the path's peak and each draw rescales the
    whole path, keeping its shape). Interest-rate
    (bps) and revenue (standard deviations of own revenue growth) shocks are
    drawn too when their standard deviation is > 0; params["revenue_sigma"]
    converts revenue draws into a share of revenue. `correlations` holds the
    pairwise correlations keyed "a|b"; if omitted only fuel–FX = `correlation`.
    With only fuel and FX drawn, the draws are identical to the original
    two-variable version for the same seed.
    Returns a LONG-format DataFrame — one row per (simulation, year)."""
    rng = np.random.default_rng(seed)
    corrs = dict(correlations) if correlations else {}
    corrs.setdefault("fuel|fx", correlation)
    names = ["fuel", "fx"] + (["rate"] if rate_std_bps > 0 else []) + (["revenue"] if revenue_std_sd > 0 else [])
    fpath = _fuel_path(params)                   # with a path, fuel draws centre on its peak and rescale its shape
    peak = max(fpath, key=abs) if fpath else None
    means = {"fuel": params["fuel_shock_pct"] if fpath is None else peak, "fx": params["fx_shock_pct"],
             "rate": params.get("rate_shock_bps", 0.0), "revenue": params.get("revenue_shock_std_devs", 0.0)}
    sds = {"fuel": fuel_std, "fx": fx_std, "rate": rate_std_bps, "revenue": revenue_std_sd}
    if names == ["fuel", "fx"]:
        c = corrs["fuel|fx"]
        cov = [[fuel_std ** 2, c * fuel_std * fx_std], [c * fuel_std * fx_std, fx_std ** 2]]
        draws = rng.multivariate_normal([means["fuel"], means["fx"]], cov, size=n_sims)
    else:
        cov = mc_covariance(names, sds, corrs)
        draws = rng.multivariate_normal([means[n] for n in names], cov, size=n_sims)

    sigma = params.get("revenue_sigma")
    if sigma is None and params.get("revenue_shock_std_devs"):
        sigma = params.get("revenue_shock_pct", 0.0) / params["revenue_shock_std_devs"]
    all_rows = []
    for i in range(n_sims):
        sim_params = dict(params)
        drawn = dict(zip(names, draws[i]))
        sim_params["fuel_shock_pct"] = drawn["fuel"]
        if fpath is not None:
            sim_params["fuel_shock_path"] = [drawn["fuel"] * (v / peak) for v in fpath] if peak else list(fpath)
        sim_params["fx_shock_pct"] = drawn["fx"]
        if "rate" in drawn:
            sim_params["rate_shock_bps"] = drawn["rate"]
        if "revenue" in drawn:
            if sigma is None:
                raise ValueError("params['revenue_sigma'] is needed to draw revenue shocks")
            sim_params["revenue_shock_std_devs"] = drawn["revenue"]
            sim_params["revenue_shock_pct"] = drawn["revenue"] * sigma

        scenario = run_scenario(base_row, sim_params, horizon_years)
        scenario["sim"] = i
        for n in names:
            scenario[{"fuel": "fuel_shock_pct", "fx": "fx_shock_pct", "rate": "rate_shock_bps", "revenue": "revenue_shock_std_devs"}[n]] = drawn[n]
        scenario["PD"] = scenario["Rating"].apply(compute_pd_from_rating)
        scenario["EAD"] = scenario["Total Liabilities"] * ead_share
        scenario["LGD"] = lgd_pct / 100.0
        scenario["EFC"] = scenario["PD"] * scenario["EAD"] * scenario["LGD"]
        all_rows.append(scenario)

    return pd.concat(all_rows, ignore_index=True)


def mc_percentile_path(mc_long: pd.DataFrame, value_col: str,
                        percentiles=(0.05, 0.25, 0.50, 0.75, 0.95)) -> pd.DataFrame:
    """Collapse a long-format Monte Carlo DataFrame (from run_monte_carlo)
    into a per-year percentile path for the given value column."""
    grouped = mc_long.groupby("Projection Year")[value_col]
    out = grouped.quantile(list(percentiles)).unstack()
    out.columns = [f"p{int(p*100)}" for p in percentiles]
    out = out.reset_index()
    # attach calendar year for x-axis labeling
    cal_years = mc_long.groupby("Projection Year")["Calendar Year"].first()
    out["Calendar Year"] = out["Projection Year"].map(cal_years)
    return out


def describe_active_shocks(params: dict) -> str:
    """Compact, human-readable summary of only the non-zero shock
    magnitude channels in `params` — for annotating charts so a saved or
    downloaded chart is interpretable on its own, and so runs (fuel alone
    vs FX alone vs combined) are distinguishable when compared side by
    side. Exposure/structural parameters (fuel cost share, tariff
    pass-through, FX shares, etc.) are not shock magnitudes and are left
    out — only the channels that actually move something show up here."""
    parts = []
    fpath = _fuel_path(params)
    if fpath is not None:
        parts.append("Fuel path " + "/".join(f"{v*100:+.0f}" for v in fpath) + "%")
        fuel_on = any(v != 0 for v in fpath)
    else:
        fuel_on = params.get("fuel_shock_pct", 0) != 0
        if fuel_on:
            parts.append(f"Fuel {params['fuel_shock_pct']*100:+.0f}%")
    n_fuel = len(parts)
    if params.get("fx_shock_pct", 0) != 0:
        parts.append(f"FX {params['fx_shock_pct']*100:+.0f}%")
    if params.get("rate_shock_bps", 0) != 0:
        parts.append(f"Rate {params['rate_shock_bps']:+.0f}bps")
    if params.get("revenue_shock_pct", 0) != 0:
        std_devs = params.get("revenue_shock_std_devs")
        if std_devs is not None and std_devs != 0:
            parts.append(f"Revenue {std_devs:+.1f}\u03c3")
        else:
            parts.append(f"Revenue {params['revenue_shock_pct']*100:+.0f}%")
    if params.get("refinancing_spread_bps", 0) != 0 and params.get("near_term_maturity_share", 0) > 0:
        parts.append(f"Refi {params['refinancing_spread_bps']:+.0f}bps")
    if params.get("arrears_pct_of_revenue", 0) != 0:
        parts.append(f"Arrears {params['arrears_pct_of_revenue']*100:+.0f}%/yr")
    step_on = fpath is None or len(parts) > n_fuel        # a shock that runs for shock_duration_years
    if params.get("tariff_increase_pct", 0):
        parts.append(f"Tariff {params['tariff_increase_pct']*100:+.0f}%")
    if params.get("fuel_subsidy_share", 0) and fuel_on:
        parts.append(f"gov. absorbs {params['fuel_subsidy_share']*100:.0f}% of fuel cost change")
        paid = params.get("comp_paid_share")
        paid = 1.0 if paid is None else paid
        if paid < 1:
            parts.append(f"{paid*100:.0f}% paid in-year")

    if not parts:
        return "No shock applied (baseline)"

    duration = params.get("shock_duration_years")
    summary = ", ".join(parts)
    if duration and step_on:
        summary += f" — active {duration}yr"
    return summary
