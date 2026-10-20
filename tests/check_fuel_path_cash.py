"""
Checks for the fuel price path, the oil linkage, the tariff revenue base and
cash-first financing in shocks.run_scenario.

    python tests/check_fuel_path_cash.py

1. Legacy reproduction: with legacy_loss_assets=True the engine still
   reproduces the original formula exactly, whether or not the SOE reports
   cash (the cash buffer is off in legacy mode).
2. Bit-exact against the engine before this change (git 064ac24, loaded with
   `git show`): (a) the shipped defaults on the demo portfolio (no cash
   column); (b) cash_buffer_share = 0 on a demo copy that reports cash;
   (c) the shipped defaults on that copy for every SOE that never borrows;
   (d) Monte Carlo without a path draws the same numbers.
3. A path [p]*D + [0]*(H-D) gives the same numbers as the step shock of
   magnitude p for D years, tariff increase included.
4. The oil linkage scales the fuel-cost change.
5. Tariff revenue base: revenue, revenue less grants, missing grants, grants
   above revenue.
6. Cash arithmetic on an illustrative utility: draw above the floor, the rest
   borrowed and grossed up for interest; half share; replenishment capped at
   the cumulative drawdown; TA = TL + Equity.
7. Monte Carlo with a path is centred on the path peak and keeps its shape.
8. The chart caption of the oil preset.
"""

import math
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import calculations  # noqa: E402
import config  # noqa: E402
import data_loader  # noqa: E402
import shocks  # noqa: E402
from check_cash_channel import COLS, LEGACY_OIL, original_run_scenario  # noqa: E402
from utils.portfolio import latest_per_entity  # noqa: E402

BASE_COMMIT = "064ac24"
CASH_SOES = {"SOE A", "SOE C", "SOE D", "SOE G", "SOE H"}  # B, E, F report no cash


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def same(a, b):
    """Bit-exact equality; NaN equals NaN."""
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    a, b = float(a), float(b)
    return a == b or (math.isnan(a) and math.isnan(b))


def head_engine():
    """shocks.py as of BASE_COMMIT, or None when git is unavailable."""
    try:
        src = subprocess.run(["git", "-C", str(ROOT), "show", f"{BASE_COMMIT}:shocks.py"],
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    mod = types.ModuleType("shocks_head")
    mod.__file__ = f"{BASE_COMMIT}:shocks.py"
    exec(compile(src, mod.__file__, "exec"), mod.__dict__)
    return mod


def panel(raw):
    return latest_per_entity(calculations.compute_kpis(calculations.compute_zem_components(data_loader.coerce_numeric(raw))))


def with_cash(raw):
    out = raw.copy()
    out["Cash and Equivalents"] = np.where(out["Entity"].isin(CASH_SOES), 0.25 * pd.to_numeric(out["Current Assets"]), np.nan)
    return out


def params_for(r, p0):
    p = {k: v for k, (v, _s) in calculations.soe_exposures(r).items()}  # incl. the default cash settings
    p.update(p0)
    p["revenue_shock_pct"] = p["revenue_shock_std_devs"] * 0.1
    return p


def identity_drift(path, r, p):
    """TA - TL - Equity against its base-year gap, net of the arrears write-down (no offsetting entry by design)."""
    gap0 = r["Total Assets"] - r["Total Liabilities"] - r["Equity"]
    out, arr = [], 0.0
    for t in range(1, len(path)):
        if t <= p["shock_duration_years"]:
            arr += -p["arrears_pct_of_revenue"] * r["Revenues"]
        out.append(path["Total Assets"].iloc[t] - path["Total Liabilities"].iloc[t] - path["Equity"].iloc[t] - gap0 - arr)
    return out


def main():
    fails, n = [], 0
    raw = data_loader.demo_portfolio()
    latest, latest_cash = panel(raw), panel(with_cash(raw))
    H = 5
    std = dict(config.DEFAULT_SHOCK_PARAMS)
    custom = dict(std, fuel_shock_pct=-0.2, fx_shock_pct=0.45, rate_shock_bps=-150, refinancing_spread_bps=600,
                  arrears_pct_of_revenue=-0.1, shock_duration_years=3, tariff_passthrough=0.2)
    subsidy = dict(custom, fuel_shock_pct=0.4, fuel_subsidy_share=0.3, tariff_passthrough=0.5)
    deep = dict(std, fuel_shock_pct=0.8, fx_shock_pct=0.6, rate_shock_bps=600)
    zero = dict(std, fuel_shock_pct=0.0, fx_shock_pct=0.0, rate_shock_bps=0.0, revenue_shock_std_devs=0.0,
                refinancing_spread_bps=0.0, arrears_pct_of_revenue=0.0)
    oil_old = {**std, **config.DEFAULT_CASH_SETTINGS, **LEGACY_OIL, "fx_shock_pct": 0.3, "comp_provision_share": 0.3,
               "cash_gap_payables_share": 0.4, "vat_trapped_share": 0.6, "tariff_increase_pct": 0.1}
    cases = {"zero": zero, "standard": std, "custom": custom, "subsidy": subsidy, "deep": deep, "oil_old": oil_old}

    # 1. legacy reproduction, with and without a cash column, buffer on or off
    for name, p0 in cases.items():
        if name == "oil_old":
            continue  # the original formula has no cash channel
        for lat in (latest, latest_cash):
            for _, r in lat.iterrows():
                p = params_for(r, p0)
                ref = original_run_scenario(r, p, H)
                for buf in (0.0, 1.0):
                    leg = shocks.run_scenario(r, dict(p, legacy_loss_assets=True, cash_buffer_share=buf), H)
                    for t in range(H + 1):
                        for i, c in enumerate(COLS):
                            n += 1
                            if not close(ref[t][i], leg[c].iloc[t]):
                                fails.append(f"1 legacy {name} {r['Entity']} buf={buf} t={t} {c}: original={ref[t][i]} new={leg[c].iloc[t]}")
                    n += 1
                    if leg["Cash Drawdown"].abs().sum() != 0:
                        fails.append(f"1 legacy {name} {r['Entity']}: cash drawn in legacy mode")

    # 2. bit-exact against the engine before this change
    old = head_engine()
    n_draw = 0
    if old is None:
        print("git not available — skipping the bit-exact comparison with", BASE_COMMIT)
    else:
        def compare(tag, a, b):
            nonlocal n
            for c in b.columns:
                for t in range(len(b)):
                    n += 1
                    if not same(a[c].iloc[t], b[c].iloc[t]):
                        fails.append(f"2{tag} t={t} {c}: new={a[c].iloc[t]} head={b[c].iloc[t]}")
                        return

        for name, p0 in cases.items():
            for _, r in latest.iterrows():                      # (a) shipped defaults, no cash column
                p = params_for(r, p0)
                compare(f"a {name} {r['Entity']}", shocks.run_scenario(r, p, H), old.run_scenario(r, p, H))
                for blank in ([], 0.0, None):                   # an empty / zero path is the step profile
                    compare(f"a {name} {r['Entity']} path={blank!r}", shocks.run_scenario(r, dict(p, fuel_shock_path=blank), H), old.run_scenario(r, p, H))
            for _, r in latest_cash.iterrows():
                p = params_for(r, p0)
                href = old.run_scenario(r, p, H)                # (b) buffer off on the cash copy
                compare(f"b {name} {r['Entity']}", shocks.run_scenario(r, dict(p, cash_buffer_share=0.0), H), href)
                new = shocks.run_scenario(r, p, H)              # (c) defaults: identical when nothing is ever borrowed
                if href["Cash Funding Gap"].abs().sum() == 0 or r["Entity"] not in CASH_SOES:
                    compare(f"c {name} {r['Entity']}", new, href)
                else:
                    n_draw += new["Cash Drawdown"].iloc[1:].gt(0).any()
                    n += 1
                    if not new["Cash Drawdown"].iloc[1:].gt(0).any():
                        fails.append(f"2c {name} {r['Entity']}: borrows under HEAD but draws no cash under the default")
                    for t, d in enumerate(identity_drift(new, r, p), 1):
                        n += 1
                        if abs(d) > 1e-6 * max(1.0, abs(r["Total Assets"])):
                            fails.append(f"2c identity {name} {r['Entity']} t={t}: drift {d:.4g}")
        n += 1
        if n_draw == 0:
            fails.append("2c no demo SOE drew cash — the cash-first check is vacuous")
        # (d) Monte Carlo without a path: same random stream, same numbers
        base = latest[latest["Entity"] == "SOE F"].iloc[0]
        p = params_for(base, std)
        a = shocks.run_monte_carlo(base, p, n_sims=200, fuel_std=0.10, fx_std=0.08, correlation=0.3, horizon_years=3, lgd_pct=70)
        b = old.run_monte_carlo(base, p, n_sims=200, fuel_std=0.10, fx_std=0.08, correlation=0.3, horizon_years=3, lgd_pct=70)
        for c in ["fuel_shock_pct", "fx_shock_pct", "Z_EM", "EFC"]:
            n += 1
            if not all(same(x, y) for x, y in zip(a[c], b[c])):
                fails.append(f"2d Monte Carlo {c} differs from {BASE_COMMIT}")

    # 3. path [p]*D + [0]*(H-D) == step of magnitude p for D years
    for name, p0 in cases.items():
        for pf in (0.4, -0.3):
            for tariff in (0.0, 0.1):
                for _, r in latest_cash.iterrows():
                    p = params_for(r, dict(p0, fuel_shock_pct=pf, tariff_increase_pct=tariff))
                    D = p["shock_duration_years"]
                    step = shocks.run_scenario(r, p, H)
                    path = shocks.run_scenario(r, dict(p, fuel_shock_pct=0.123, fuel_shock_path=[pf] * D + [0.0] * (H - D)), H)
                    for c in step.columns:
                        n += 1
                        if not all(same(x, y) for x, y in zip(step[c], path[c])):
                            fails.append(f"3 path vs step {name} p={pf} tariff={tariff} {r['Entity']} {c}")
                            break
    # a path shorter than the horizon is zero beyond its end; non-zero years make the tariff term active
    r = latest_cash.iloc[0]
    p = params_for(r, dict(zero, tariff_increase_pct=0.1, fuel_shock_path=[0.0, 0.5]))
    pth = shocks.run_scenario(r, p, H)
    n += 3
    if pth["Fuel Cost Change"].iloc[1] != 0 or pth["Tariff Increase Revenue"].iloc[1] != 0:
        fails.append("3 a zero path year must not shock fuel nor raise the tariff")
    if not pth["Fuel Cost Change"].iloc[2] > 0 or not pth["Tariff Increase Revenue"].iloc[2] > 0:
        fails.append("3 a non-zero path year must shock fuel and raise the tariff")
    if pth["Fuel Cost Change"].iloc[3:].abs().sum() != 0:
        fails.append("3 the path must be zero beyond its end")

    # 4. oil linkage scales the fuel-cost change
    for _, r in latest.iterrows():
        p = params_for(r, dict(zero, fuel_shock_pct=0.6, fuel_subsidy_share=0.5))
        one = shocks.run_scenario(r, p, H)
        half = shocks.run_scenario(r, dict(p, fuel_oil_linkage=0.5), H)
        half_shock = shocks.run_scenario(r, dict(p, fuel_shock_pct=0.3), H)
        for t in range(1, H + 1):
            n += 3
            if not close(half["Fuel Cost Change"].iloc[t], 0.5 * one["Fuel Cost Change"].iloc[t]):
                fails.append(f"4 linkage {r['Entity']} t={t}: {half['Fuel Cost Change'].iloc[t]} vs half of {one['Fuel Cost Change'].iloc[t]}")
            if not close(half["Z_EM"].iloc[t], half_shock["Z_EM"].iloc[t]):
                fails.append(f"4 linkage {r['Entity']} t={t}: ε 0.5 ≠ half the shock")
            if not close(half["Direct Fuel Subsidy"].iloc[t], half_shock["Direct Fuel Subsidy"].iloc[t]):
                fails.append(f"4 linkage {r['Entity']} t={t}: subsidy")

    # 5. tariff revenue base
    U = pd.Series({"Entity": "Utility", "Sector": "Power / Utilities", "Year": 2024, "Revenues": 1000.0, "Operating Expense": 900.0,
                   "Operating Profits (EBIT)": 60.0, "Net Income": 20.0, "Current Assets": 400.0, "Current Liabilities": 520.0,
                   "Total Assets": 3000.0, "Total Liabilities": 2200.0, "Equity": 800.0, "Retained Earnings": 50.0,
                   "Interest Expense": 40.0, "Tax Expense": 0.0, "Depreciation": 0.0, "Government Grants": 200.0})
    base = {**zero, **config.DEFAULT_CASH_SETTINGS, "fuel_cost_share": 0.5, "fuel_shock_pct": 0.6, "tariff_increase_pct": 0.15,
            "tariff_passthrough": 0.0}
    for label, row, setting, expect in [
        ("revenue", U, "revenue", 0.15 * 1000.0),
        ("ex grants", U, "revenue_ex_grants", 0.15 * 800.0),
        ("ex grants, grants missing", U.drop("Government Grants"), "revenue_ex_grants", 0.15 * 1000.0),
        ("ex grants, grants NaN", U.copy().pipe(lambda s: s.where(s.index != "Government Grants", np.nan)), "revenue_ex_grants", 0.15 * 1000.0),
        ("ex grants, grants above revenue", U.copy().pipe(lambda s: s.where(s.index != "Government Grants", 1500.0)), "revenue_ex_grants", 0.0),
    ]:
        got = shocks.run_scenario(row, dict(base, tariff_revenue_base=setting), 2)["Tariff Increase Revenue"].iloc[1]
        n += 1
        if not close(got, expect):
            fails.append(f"5 tariff base {label}: {got} vs {expect}")

    # 6. cash arithmetic (round numbers, not SOE data): Cash 150, floor 10% of OpEx 900 -> 60 above the floor
    L = U.copy()
    L["Net Income"] = -100.0
    L["Cash and Equivalents"] = 150.0
    cash = dict(base, fuel_shock_pct=0.0, tariff_increase_pct=0.0, cash_floor_opex_share=0.1,
                cash_gap_short_term_share=1.0, new_debt_interest_rate=0.08)
    pc = shocks.run_scenario(L, cash, 3)
    g1 = 40.0 / (1 - 0.08 / 2)
    for k, v in {"Cash Drawdown": 60.0, "Cash": 90.0, "Cash Funding Gap": g1, "New Short-term Debt": g1,
                 "Interest on New Debt": 0.04 * g1, "Net Income": -100.0 - 0.04 * g1,
                 "Current Assets": 400.0 - 60.0, "Total Assets": 3000.0 - 60.0, "Current Liabilities": 520.0 + g1}.items():
        n += 1
        if not close(pc[k].iloc[1], v):
            fails.append(f"6 year-1 {k}: {pc[k].iloc[1]} vs {v}")
    n += 3
    if pc["Cash Drawdown"].iloc[2] != 0 or pc["Cash"].iloc[2] != 90.0:
        fails.append("6 year 2: nothing left above the floor, so nothing is drawn")
    if pc["Cash"].iloc[0] != 150.0:
        fails.append("6 year 0 carries the opening cash")
    if not close(pc["Cash Funding Gap"].iloc[2], (100.0 + 0.08 * g1) / (1 - 0.04)):
        fails.append(f"6 year 2 borrows the whole gap incl. interest on last year's draw: {pc['Cash Funding Gap'].iloc[2]}")
    half = shocks.run_scenario(L, dict(cash, cash_buffer_share=0.5), 3)
    n += 2
    if not close(half["Cash Drawdown"].iloc[1], 30.0):
        fails.append(f"6 half share: draw {half['Cash Drawdown'].iloc[1]} vs 30")
    if not close(half["Cash Funding Gap"].iloc[1], 70.0 / (1 - 0.04)):
        fails.append(f"6 half share: borrowed {half['Cash Funding Gap'].iloc[1]}")
    nofloor = shocks.run_scenario(L, dict(cash, cash_floor_opex_share=0.0), 3)
    n += 2
    if not close(nofloor["Cash Drawdown"].iloc[1], 100.0) or nofloor["Cash Funding Gap"].iloc[1] != 0:
        fails.append("6 no floor: the whole gap comes out of cash")
    if not close(nofloor["Cash Drawdown"].iloc[2], 50.0):
        fails.append(f"6 no floor, year 2: draws the remaining 50 ({nofloor['Cash Drawdown'].iloc[2]})")
    # replenishment: a one-year fuel loss of 100 (profit 20 otherwise), funded long-term, no interest
    P = U.copy()
    P["Cash and Equivalents"] = 150.0
    rep = dict(base, fuel_shock_pct=0.0, tariff_increase_pct=0.0, fuel_cost_share=0.4, fuel_shock_path=[1 / 3],
               cash_floor_opex_share=0.1)
    pr = shocks.run_scenario(P, rep, 6)
    exp_cash = [150.0, 90.0, 110.0, 130.0, 150.0, 150.0, 150.0]
    for t, v in enumerate(exp_cash):
        n += 2
        if not close(pr["Cash"].iloc[t], v):
            fails.append(f"6 replenishment t={t}: cash {pr['Cash'].iloc[t]} vs {v}")
        if not close(pr["Total Assets"].iloc[t], 3000.0 + (0 if t == 0 else -60.0 + 20.0 * (t - 1))):
            fails.append(f"6 replenishment t={t}: total assets {pr['Total Assets'].iloc[t]}")
    n += 1
    if not close(pr["Current Assets"].iloc[6] - pr["Current Assets"].iloc[0], 0.0):
        fails.append("6 replenishment beyond the drawdown must not reach current assets")
    for tag, path, row, p in [("loss", pc, L, cash), ("half", half, L, dict(cash, cash_buffer_share=0.5)), ("replenish", pr, P, rep)]:
        for t, d in enumerate(identity_drift(path, row, p), 1):
            n += 1
            if abs(d) > 1e-6:
                fails.append(f"6 identity {tag} t={t}: drift {d:.4g}")
    # the cash column: 0 without a cash figure, flat when the buffer is off
    n += 2
    if shocks.run_scenario(U, cash, 2)["Cash"].abs().sum() != 0:
        fails.append("6 Cash must be 0 when the data report no cash")
    if not (shocks.run_scenario(L, dict(cash, cash_buffer_share=0.0), 2)["Cash"] == 150.0).all():
        fails.append("6 Cash must stay at its opening value when the buffer is off")

    # 7. Monte Carlo with a path: centred on the peak, shape kept
    fp = [0.0, 0.6, 0.3]
    mp = dict(base, fuel_shock_pct=0.25, tariff_increase_pct=0.0, fuel_subsidy_share=0.0, fuel_shock_path=fp)
    mc = shocks.run_monte_carlo(U, mp, n_sims=2000, fuel_std=0.10, fx_std=0.08, correlation=0.3, horizon_years=3, lgd_pct=70)
    draws = mc[mc["Projection Year"] == 1]["fuel_shock_pct"]
    n += 2
    if abs(draws.mean() - 0.6) > 4 * 0.10 / math.sqrt(2000):
        fails.append(f"7 Monte Carlo draws centred on {draws.mean():.4f}, not the path peak 0.6")
    shape_ok = True
    for _, g in mc.groupby("sim"):
        f = g.set_index("Projection Year")["Fuel Cost Change"]
        d = g["fuel_shock_pct"].iloc[0]
        if f.loc[1] != 0 or not close(f.loc[2], 0.5 * 900.0 * d) or not close(f.loc[3], 0.5 * 900.0 * d * 0.5):
            shape_ok = False
            break
    if not shape_ok:
        fails.append("7 Monte Carlo path does not keep the 0 / peak / half shape")
    neg = shocks.run_monte_carlo(U, dict(mp, fuel_shock_path=[-0.2, 0.1]), n_sims=50, fuel_std=0.05, fx_std=0.08, correlation=0.3, horizon_years=2, lgd_pct=70)
    n += 1
    g0 = neg[neg["sim"] == 0].set_index("Projection Year")
    if not close(g0["Fuel Cost Change"].loc[2], -0.5 * g0["Fuel Cost Change"].loc[1]):
        fails.append("7 Monte Carlo: the peak is the largest absolute value (here negative)")

    # 8. chart caption of the oil preset
    desc = shocks.describe_active_shocks({**zero, **config.DEFAULT_CASH_SETTINGS, **config.OIL_SHOCK_PRESET})
    expect = "Fuel path +0/+60/+30/+0/+0%, gov. absorbs 100% of fuel cost change, 60% paid in-year"
    n += 2
    if desc != expect:
        fails.append(f"8 describe: {desc!r} vs {expect!r}")
    desc2 = shocks.describe_active_shocks(dict(std, fuel_shock_path=[0.0, 0.6]))
    if not desc2.startswith("Fuel path +0/+60%, FX +30%") or not desc2.endswith("— active 2yr"):
        fails.append(f"8 describe with other step shocks: {desc2!r}")

    if fails:
        print(f"{len(fails)} failures:")
        print("\n".join(fails[:40]))
        return 1
    print(f"OK — fuel path, oil linkage, tariff base, cash-first: {n} checks passed ({n_draw} SOE-scenarios draw cash).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
