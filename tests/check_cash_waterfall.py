"""
Checks for the cash waterfall reform, the borrowing cap (emergency government
support) and the RMA coverage ratio in shocks.run_scenario.

    python tests/check_cash_waterfall.py

1. Off by default: with waterfall_on = 0 and borrowing_cap_debt_to_assets = 0
   the engine gives exactly the same numbers as with the new settings left out
   of the parameters altogether, and the other waterfall settings are inert
   (demo portfolio with a partial cash column, several scenarios, bit-exact).
2. Refinancing arithmetic on an illustrative utility (round numbers, not SOE
   data): reported short-term debt is refinanced in year 1, capped at current
   liabilities; current liabilities fall and total liabilities do not; the
   interest saving lifts net income and lowers interest every year. Without a
   "Short Term Debt" column the near-term maturity share is the proxy.
3. Under the waterfall no supplier arrears build up (the short-term part of a
   cash gap is bank debt, at the rate on new borrowing), and the refinanced debt
   leaves the base of the refinancing shock.
4. Borrowing cap: borrowing stops at the debt-to-assets cap and the State
   injects the rest (equity, not retained earnings); TA = TL + Equity still
   holds; a cap that does not bind changes nothing.
5. RMA coverage = (revenue - grants + tariff increase + pass-through) /
   (revenue + fuel-cost change); NaN when grants are not reported.
6. Legacy mode ignores the waterfall; the chart caption names the policies.
7. Z-EM rises under the waterfall for the illustrative utility (X1 up).
"""

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import config  # noqa: E402
import data_loader  # noqa: E402
import shocks  # noqa: E402
from check_fuel_path_cash import panel, params_for, with_cash  # noqa: E402

NEW_KEYS = ["waterfall_on", "waterfall_refinance_share", "short_term_debt_rate", "waterfall_long_term_rate",
            "borrowing_cap_debt_to_assets"]


def close(a, b, tol=1e-9):
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def same(a, b):
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    a, b = float(a), float(b)
    return a == b or (math.isnan(a) and math.isnan(b))


def main():
    fails, n = [], 0
    zero_mags = {k: 0.0 for k in ["fuel_shock_pct", "fx_shock_pct", "rate_shock_bps", "revenue_shock_std_devs",
                                  "refinancing_spread_bps", "arrears_pct_of_revenue", "tariff_increase_pct"]}

    # 1. off by default: bit-exact with the settings absent, and the other waterfall settings inert
    oil = {**config.DEFAULT_SHOCK_PARAMS, **config.OIL_SHOCK_PRESET}
    scen = {"defaults": dict(config.DEFAULT_SHOCK_PARAMS), "oil": oil,
            "oil policy": dict(oil, tariff_increase_pct=0.1, comp_provision_share=0.3, cash_gap_payables_share=0.4,
                               vat_trapped_share=0.5, refinancing_spread_bps=300, arrears_pct_of_revenue=0.1)}
    for _, r in panel(with_cash(data_loader.demo_portfolio())).iterrows():
        for name, p0 in scen.items():
            p = params_for(r, p0)
            ref = shocks.run_scenario(r, {k: v for k, v in p.items() if k not in NEW_KEYS}, 5)
            for tag, q in [("defaults", p), ("inert", dict(p, waterfall_refinance_share=0.4, short_term_debt_rate=0.2,
                                                            waterfall_long_term_rate=0.01))]:
                got = shocks.run_scenario(r, q, 5)
                for c in got.columns:
                    for t in range(len(got)):
                        n += 1
                        if not same(got[c].iloc[t], ref[c].iloc[t]):
                            fails.append(f"1 {tag} {name} {r['Entity']} t={t} {c}: {got[c].iloc[t]} vs {ref[c].iloc[t]}")

    # 2. refinancing arithmetic on an illustrative utility (round numbers, FCFA bn; not SOE data)
    U = pd.Series({"Entity": "Utility", "Sector": "Power / Utilities", "Year": 2024, "Revenues": 1000.0, "Operating Expense": 900.0,
                   "Operating Profits (EBIT)": 60.0, "Net Income": 20.0, "Current Assets": 400.0, "Current Liabilities": 520.0,
                   "Total Assets": 3000.0, "Total Liabilities": 2200.0, "Equity": 800.0, "Retained Earnings": 50.0,
                   "Interest Expense": 40.0, "Tax Expense": 0.0, "Depreciation": 0.0, "Government Grants": 200.0,
                   "Short Term Debt": 150.0})
    zero = {**config.DEFAULT_SHOCK_PARAMS, **zero_mags, **config.DEFAULT_CASH_SETTINGS, "fuel_cost_share": 0.5,
            "tariff_passthrough": 0.0, "near_term_maturity_share": 0.2, "revenue_shock_pct": 0.0, "fuel_shock_path": []}
    wf = dict(zero, waterfall_on=1.0, short_term_debt_rate=0.08, waterfall_long_term_rate=0.05)
    pw = shocks.run_scenario(U, wf, 3)
    sav = 150.0 * 0.03
    exp = {0: {"Current Liabilities": 520.0, "Refinanced Debt": 0.0, "Total Liabilities": 2200.0, "Interest Expense": 40.0},
           1: {"Current Liabilities": 370.0, "Refinanced Debt": 150.0, "Total Liabilities": 2200.0, "Interest Expense": 40.0 - sav,
               "Interest Saved": sav, "Net Income": 20.0 + sav, "Total Assets": 3000.0 + 20.0 + sav, "Equity": 820.0 + sav,
               "Retained Earnings": 70.0 + sav},
           2: {"Current Liabilities": 370.0, "Interest Saved": sav, "Net Income": 20.0 + sav, "Total Assets": 3000.0 + 2 * (20.0 + sav)}}
    for t, d in exp.items():
        for k, v in d.items():
            n += 1
            if not close(pw[k].iloc[t], v):
                fails.append(f"2 t={t} {k}: {pw[k].iloc[t]} vs {v}")
    for label, row, p, refi in [("capped at current liabilities", U.copy().pipe(lambda s: s.where(s.index != "Short Term Debt", 600.0)), wf, 520.0),
                                ("proxy: near-term maturity share", U.drop("Short Term Debt"), wf, 0.2 * 2200.0),
                                ("half refinanced", U, dict(wf, waterfall_refinance_share=0.5), 75.0)]:
        got = shocks.run_scenario(row, p, 2)
        n += 2
        if not close(got["Refinanced Debt"].iloc[1], refi):
            fails.append(f"2 {label}: refinanced {got['Refinanced Debt'].iloc[1]} vs {refi}")
        if not close(got["Interest Saved"].iloc[1], refi * 0.03):
            fails.append(f"2 {label}: saving {got['Interest Saved'].iloc[1]} vs {refi * 0.03}")

    # 3. no supplier arrears or short-term debt, long-term rate on new borrowing, smaller refinancing-shock base
    L = U.copy()
    L["Net Income"] = -100.0
    gap = dict(zero, cash_gap_short_term_share=1.0, cash_gap_payables_share=0.5, new_debt_interest_rate=0.10)
    off, on = shocks.run_scenario(L, gap, 2), shocks.run_scenario(L, dict(gap, waterfall_on=1.0), 2)
    f_on = (100.0 - sav) / (1 - 0.10 / 2)
    f_off = 100.0 / (1 - 0.5 * 0.10 / 2)
    for tag, path, k, v in [("on", on, "Cash Funding Gap", f_on), ("on", on, "New Short-term Debt", f_on), ("on", on, "Supplier Arrears", 0.0),
                            ("on", on, "New Long-term Debt", 0.0), ("on", on, "Interest on New Debt", 0.05 * f_on),
                            ("on", on, "Current Liabilities", 370.0 + f_on), ("on", on, "Total Liabilities", 2200.0 + f_on),
                            ("off", off, "Cash Funding Gap", f_off), ("off", off, "Supplier Arrears", 0.5 * f_off),
                            ("off", off, "New Short-term Debt", 0.5 * f_off), ("off", off, "Current Liabilities", 520.0 + f_off)]:
        n += 1
        if not close(path[k].iloc[1], v):
            fails.append(f"3 waterfall {tag} {k}: {path[k].iloc[1]} vs {v}")
    refi_shock = dict(zero, refinancing_spread_bps=200, shock_duration_years=2)
    i_off = shocks.run_scenario(U, refi_shock, 2)["Interest Expense"].iloc[1]
    i_on = shocks.run_scenario(U, dict(refi_shock, waterfall_on=1.0, short_term_debt_rate=0.08, waterfall_long_term_rate=0.05), 2)["Interest Expense"].iloc[1]
    n += 2
    if not close(i_off, 40.0 + 0.2 * 2200.0 * 0.02):
        fails.append(f"3 refinancing shock without the waterfall: {i_off}")
    if not close(i_on, 40.0 + (0.2 * 2200.0 - 150.0) * 0.02 - sav):
        fails.append(f"3 refinancing shock with the waterfall: {i_on}")

    # 4. borrowing cap: TL/TA 0.733 at the start, cap 0.75 -> 50 of borrowing room in year 1
    capp = dict(zero, new_debt_interest_rate=0.10, borrowing_cap_debt_to_assets=0.75)
    pc = shocks.run_scenario(L.drop("Short Term Debt"), capp, 3)
    s1 = 100.0 - 50.0 * (1 - 0.05)
    for t, k, v in [(1, "Cash Funding Gap", 50.0), (1, "Emergency Support", s1), (1, "Interest on New Debt", 2.5),
                    (1, "Net Income", -102.5), (1, "Equity", 750.0), (1, "Retained Earnings", -52.5), (1, "Total Liabilities", 2250.0),
                    (1, "Debt to Assets", 0.75), (2, "Cash Funding Gap", 0.0), (2, "Emergency Support", 105.0),
                    (2, "Cumulative Emergency Support", s1 + 105.0), (2, "Debt to Assets", 0.75)]:
        n += 1
        if not close(pc[k].iloc[t], v):
            fails.append(f"4 cap t={t} {k}: {pc[k].iloc[t]} vs {v}")
    for t in range(len(pc)):
        n += 1
        if not close(pc["Total Assets"].iloc[t], pc["Total Liabilities"].iloc[t] + pc["Equity"].iloc[t]):
            fails.append(f"4 cap t={t}: TA ≠ TL + Equity")
    loose = shocks.run_scenario(L.drop("Short Term Debt"), dict(capp, borrowing_cap_debt_to_assets=0.95), 3)
    nocap = shocks.run_scenario(L.drop("Short Term Debt"), dict(capp, borrowing_cap_debt_to_assets=0.0), 3)
    for c in nocap.columns:
        for t in range(len(nocap)):
            n += 1
            if not same(loose[c].iloc[t], nocap[c].iloc[t]):
                fails.append(f"4 a cap that does not bind changes {c} at t={t}")

    # 5. RMA coverage
    fuel = dict(zero, fuel_shock_pct=0.6, shock_duration_years=1, fuel_subsidy_share=1.0)
    inc = 0.5 * 900.0 * 0.6
    for label, row, p, t, v in [("base year", U, fuel, 0, 0.8), ("Option A", U, fuel, 1, 800.0 / (1000.0 + inc)),
                                ("Option B +15% on revenue less grants", U, dict(fuel, tariff_increase_pct=0.15, tariff_revenue_base="revenue_ex_grants"), 1,
                                 (800.0 + 120.0) / (1000.0 + inc)),
                                ("pass-through 50%", U, dict(fuel, tariff_passthrough=0.5, fuel_subsidy_share=0.5), 1, (800.0 + 0.5 * inc) / (1000.0 + inc)),
                                ("after the shock", U, fuel, 2, 0.8),
                                ("grants missing", U.drop("Government Grants"), fuel, 1, float("nan")),
                                ("grants missing, base year", U.drop("Government Grants"), fuel, 0, float("nan"))]:
        got = float(shocks.run_scenario(row, p, 2)["Tariff Share of RMA"].iloc[t])
        n += 1
        if not close(got, v):
            fails.append(f"5 RMA coverage {label}: {got} vs {v}")

    # 6. legacy mode ignores the waterfall; caption
    leg = dict(gap, legacy_loss_assets=True)
    a, b = shocks.run_scenario(L, leg, 3), shocks.run_scenario(L, dict(leg, waterfall_on=1.0), 3)
    for c in a.columns:
        for t in range(len(a)):
            n += 1
            if not same(a[c].iloc[t], b[c].iloc[t]):
                fails.append(f"6 legacy: the waterfall changed {c} at t={t}")
    for p, want in [(zero, "No shock applied (baseline)"), (wf, "No shock applied (baseline) · cash waterfall"),
                    (dict(wf, borrowing_cap_debt_to_assets=0.8), "No shock applied (baseline) · cash waterfall, borrowing cap 0.80 debt/assets"),
                    (dict(fuel, waterfall_on=1.0), "Fuel +60%, gov. absorbs 100% of fuel cost change — active 1yr · cash waterfall")]:
        n += 1
        if shocks.describe_active_shocks(p) != want:
            fails.append(f"6 caption: {shocks.describe_active_shocks(p)!r} vs {want!r}")

    # 7. Z-EM rises: 150 moves out of current liabilities, X1 = (400 - 370) / 3024.5 instead of (400 - 520) / 3020
    z_off, z_on = shocks.run_scenario(U, zero, 1)["Z_EM"].iloc[1], pw["Z_EM"].iloc[1]
    n += 1
    if not z_on > z_off + 0.3:
        fails.append(f"7 Z-EM with the waterfall {z_on:.3f} vs without {z_off:.3f}")

    if fails:
        print(f"FAIL — {len(fails)} of {n} checks:")
        for f in fails[:40]:
            print("  " + f)
        return 1
    print(f"OK — cash waterfall, borrowing cap, RMA coverage: {n} checks passed "
          f"(Z-EM year 1 {z_off:.2f} without the waterfall, {z_on:.2f} with it).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
