"""
Checks for the oil-shock cash channel in shocks.run_scenario (delayed State
compensation, short-term funding of the cash gap, interest on new debt,
end-user tariff increase, trapped VAT).

    python tests/check_cash_channel.py

1. With the default cash settings and legacy_loss_assets=True, the engine
   reproduces the original formula exactly (reference copy below).
2. With the defaults as shipped (legacy_loss_assets=False), it matches the
   original formula until the first year with a loss.
3. The balance sheet balances (TA = TL + Equity, apart from the arrears
   write-down channel, which has no offsetting entry by design).
4. The cash arithmetic: unpaid compensation, funding gap with half-year
   interest, repayment from surpluses.
5. Direction checks on an illustrative utility: a tariff increase lowers the
   State's bill and the funding gap; delayed payment raises the reported
   current ratio when it starts below 1 while the adjusted ratio falls.
"""

import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import calculations  # noqa: E402
import config  # noqa: E402
import data_loader  # noqa: E402
import shocks  # noqa: E402
from utils.portfolio import latest_per_entity  # noqa: E402


def original_run_scenario(b, p, H):
    """The engine before the cash channel (Z-EM inputs only)."""
    s = dict(RE=b["Retained Earnings"], Eq=b["Equity"], TL=b["Total Liabilities"], TA=b["Total Assets"],
             CA=b["Current Assets"], CL=b["Current Liabilities"], Rev=b["Revenues"], OpEx=b["Operating Expense"])
    out = [(b["Operating Profits (EBIT)"], s["RE"], s["Eq"], s["TL"], s["TA"], s["CA"], s["CL"])]
    sub = p.get("fuel_subsidy_share", 0.0)
    for t in range(1, H + 1):
        if t <= p["shock_duration_years"]:
            inc = p["fuel_cost_share"] * s["OpEx"] * p["fuel_shock_pct"]
            d_fuel = -inc * max(0.0, 1 - p["tariff_passthrough"] - sub)
            d_fx = -(p["fx_cost_share"] * s["OpEx"] - p["fx_revenue_share"] * s["Rev"]) * p["fx_shock_pct"]
            d_rev = p["revenue_elasticity"] * p.get("revenue_shock_pct", 0.0) * s["Rev"]
            d_int = p["floating_debt_share"] * s["TL"] * p["rate_shock_bps"] / 1e4 + p.get("near_term_maturity_share", 0.0) * s["TL"] * p.get("refinancing_spread_bps", 0.0) / 1e4
            d_rv = -p["fx_debt_share"] * s["TL"] * p["fx_shock_pct"]
            d_arr = -p["arrears_pct_of_revenue"] * s["Rev"]
        else:
            d_fuel = d_fx = d_rev = d_int = d_rv = d_arr = 0.0
        ebit = b["Operating Profits (EBIT)"] + d_fuel + d_fx + d_rev
        ni = b["Net Income"] + (d_fuel + d_fx + d_rev) - d_int
        gap = max(0.0, -ni)
        s["RE"] += ni; s["Eq"] += ni + d_rv; s["TL"] += gap - d_rv; s["CA"] += d_arr; s["TA"] += ni + d_arr
        out.append((ebit, s["RE"], s["Eq"], s["TL"], s["TA"], s["CA"], s["CL"]))
    return out


# The oil preset as it stood when the cash channel was added (fuel shock in year 1, 30% paid in-year, 8%):
# tests 4 and 5 check the arithmetic on these round numbers, independently of later preset recalibrations.
LEGACY_OIL = {
    "fuel_shock_pct": 0.60, "fuel_cost_share": 0.70, "tariff_passthrough": 0.0, "fuel_subsidy_share": 1.0,
    "comp_paid_share": 0.30, "comp_backlog_collected": 1.0, "comp_provision_share": 0.0,
    "cash_gap_short_term_share": 1.0, "cash_gap_payables_share": 0.0, "new_debt_interest_rate": 0.08,
}

COLS = ["EBIT", "Retained Earnings", "Equity", "Total Liabilities", "Total Assets", "Current Assets", "Current Liabilities"]


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def main():
    fails = []
    df = calculations.compute_kpis(calculations.compute_zem_components(data_loader.coerce_numeric(data_loader.demo_portfolio())))
    latest = latest_per_entity(df)
    H = 5
    std = dict(config.DEFAULT_SHOCK_PARAMS)
    custom = dict(std, fuel_shock_pct=-0.2, fx_shock_pct=0.45, rate_shock_bps=-150, refinancing_spread_bps=600,
                  arrears_pct_of_revenue=-0.1, shock_duration_years=3, tariff_passthrough=0.2)
    subsidy = dict(custom, fuel_shock_pct=0.4, fuel_subsidy_share=0.3, tariff_passthrough=0.5)
    deep = dict(std, fuel_shock_pct=0.8, fx_shock_pct=0.6, rate_shock_bps=600)
    zero = dict(std, fuel_shock_pct=0.0, fx_shock_pct=0.0, rate_shock_bps=0.0, revenue_shock_std_devs=0.0,
                refinancing_spread_bps=0.0, arrears_pct_of_revenue=0.0)
    cases = {"zero": zero, "standard": std, "custom": custom, "subsidy": subsidy, "deep": deep}

    n = 0
    for name, p0 in cases.items():
        for _, r in latest.iterrows():
            p = {k: v for k, (v, _s) in calculations.soe_exposures(r).items()}  # incl. the default cash settings
            p.update(p0)
            p["revenue_shock_pct"] = p["revenue_shock_std_devs"] * 0.1
            ref = original_run_scenario(r, p, H)
            leg = shocks.run_scenario(r, dict(p, legacy_loss_assets=True), H)
            new = shocks.run_scenario(r, p, H)
            first_loss = next((t for t in range(1, H + 1) if new["Net Income"].iloc[t] < 0), H + 1)
            for t in range(H + 1):
                for i, c in enumerate(COLS):
                    n += 2
                    if not close(ref[t][i], leg[c].iloc[t]):
                        fails.append(f"1 legacy {name} {r['Entity']} t={t} {c}: original={ref[t][i]} new={leg[c].iloc[t]}")
                    if t < first_loss and not close(ref[t][i], new[c].iloc[t]):
                        fails.append(f"2 default {name} {r['Entity']} t={t} {c}: original={ref[t][i]} new={new[c].iloc[t]}")

    # 3. identity, including the cash channel
    oil = dict(std, **config.DEFAULT_CASH_SETTINGS)
    oil.update(config.OIL_SHOCK_PRESET)
    oil.update(fx_shock_pct=0.3, arrears_pct_of_revenue=0.05)
    policy = dict(oil, tariff_increase_pct=0.1, comp_provision_share=0.3, cash_gap_payables_share=0.4, vat_trapped_share=0.6,
                  comp_backlog_collected=0.5, cash_gap_short_term_share=0.8)
    for name, p0 in {"standard": std, "deep": deep, "oil": oil, "oil_policy": policy}.items():
        for _, r in latest.iterrows():
            p = dict(p0); p.setdefault("fuel_cost_share", 0.3); p["revenue_shock_pct"] = p["revenue_shock_std_devs"] * 0.1
            path = shocks.run_scenario(r, p, H)
            gap0 = r["Total Assets"] - r["Total Liabilities"] - r["Equity"]
            arr = 0.0
            for t in range(1, H + 1):
                if t <= p["shock_duration_years"]:
                    arr += -p["arrears_pct_of_revenue"] * r["Revenues"]
                drift = path["Total Assets"].iloc[t] - path["Total Liabilities"].iloc[t] - path["Equity"].iloc[t] - gap0 - arr
                n += 1
                if abs(drift) > 1e-6 * max(1.0, abs(r["Total Assets"])):
                    fails.append(f"3 identity {name} {r['Entity']} t={t}: drift {drift:.4g}")

    # 4. cash arithmetic on an illustrative utility (round numbers, FCFA bn; not SOE data)
    U = pd.Series({"Entity": "Utility", "Sector": "Power / Utilities", "Year": 2024, "Revenues": 1000.0, "Operating Expense": 900.0,
                   "Operating Profits (EBIT)": 60.0, "Net Income": 20.0, "Current Assets": 400.0, "Current Liabilities": 520.0,
                   "Total Assets": 3000.0, "Total Liabilities": 2200.0, "Equity": 800.0, "Retained Earnings": 50.0,
                   "Interest Expense": 40.0, "Tax Expense": 0.0, "Depreciation": 0.0})
    base = dict(zero, **config.DEFAULT_CASH_SETTINGS)
    a = dict(base, **LEGACY_OIL)                                                 # Option A, 30% paid in-year
    pa = shocks.run_scenario(U, a, 3)
    inc = 0.70 * 900 * 0.60
    exp = {"Fuel Cost Change": inc, "Direct Fuel Subsidy": inc, "State Compensation Receivable": inc * 0.7}
    gap1 = (-20.0 + inc * 0.7) / (1 - 0.08 / 2)
    exp.update({"Cash Funding Gap": gap1, "Interest on New Debt": 0.04 * gap1, "Net Income": 20.0 - 0.04 * gap1,
                "New Short-term Debt": gap1, "Current Liabilities": 520.0 + gap1})
    for k, v in exp.items():
        n += 1
        if not close(pa[k].iloc[1], v):
            fails.append(f"4 year-1 {k}: {pa[k].iloc[1]} vs {v}")
    # year 3: shock over, last year's receivable is collected and repays short-term debt
    n += 2
    if not close(pa["State Compensation Receivable"].iloc[3], 0.0):
        fails.append("4 receivable not collected after the shock")
    if not pa["New Short-term Debt"].iloc[3] < pa["New Short-term Debt"].iloc[2]:
        fails.append("4 short-term debt not repaid from the collection")

    # 5. directions
    b10 = shocks.run_scenario(U, dict(a, tariff_increase_pct=0.10), 3)
    paid_all = shocks.run_scenario(U, dict(a, comp_paid_share=1.0), 3)
    loss = shocks.run_scenario(U, dict(a, comp_provision_share=1.0), 3)
    checks = [
        ("Option B lowers the State's bill", b10["Direct Fuel Subsidy"].iloc[1] < pa["Direct Fuel Subsidy"].iloc[1]),
        ("Option B lowers the funding gap", b10["Cash Funding Gap"].iloc[1] < pa["Cash Funding Gap"].iloc[1]),
        ("Delayed payment raises the reported current ratio (it starts below 1)", pa["Current Ratio"].iloc[1] > paid_all["Current Ratio"].iloc[1]),
        ("…while the adjusted current ratio falls", pa["Adjusted Current Ratio"].iloc[1] < paid_all["Adjusted Current Ratio"].iloc[1]),
        ("Paid in full: no gap, no receivable", paid_all["Cash Funding Gap"].iloc[1] == 0 and paid_all["State Compensation Receivable"].iloc[1] == 0),
        ("Writing off unpaid compensation cuts net income and Z-EM", loss["Net Income"].iloc[1] < pa["Net Income"].iloc[1] and loss["Z_EM"].iloc[1] < pa["Z_EM"].iloc[1]),
    ]
    for label, ok in checks:
        n += 1
        if not ok:
            fails.append(f"5 {label}")

    if fails:
        print(f"{len(fails)} failures:")
        print("\n".join(fails[:40]))
        return 1
    print(f"OK — cash channel: {n} checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
