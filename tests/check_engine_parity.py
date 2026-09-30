"""
Checks that the in-browser engine (templates/engine.js) gives the same
numbers as the Python modules the Streamlit app uses. Needs Node.js on PATH.

    python tests/check_engine_parity.py

Run it after changing a formula in calculations.py, shocks.py or
narrative.py (config.py values flow into the engine automatically).
"""

import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import calculations  # noqa: E402
import config  # noqa: E402
import data_loader  # noqa: E402
import narrative  # noqa: E402
import report  # noqa: E402
import shocks  # noqa: E402
from utils import summary  # noqa: E402
from utils.portfolio import latest_per_entity  # noqa: E402

NODE_RUNNER = r"""
const fs = require("fs");
const inp = JSON.parse(fs.readFileSync(0, "utf8"));
const E = require(inp.engine).create(inp.config);
const NUM = new Set(inp.config.ALL_NUMERIC_COLUMNS);
const rows = inp.rows.map(r => { const o = {}; for (const k in r) o[k] = NUM.has(k) ? (r[k] === null ? NaN : r[k]) : r[k]; return o; });
const en = E.enrich(rows);
const latest = E.latestPerEntity(en).sort((a, b) => b.Z_EM - a.Z_EM);
const out = { rows: en.map(r => { const o = {}; for (const k of inp.keys) o[k] = r[k]; return o; }) };
out.narr = Object.fromEntries(latest.map(r => [r.Entity, E.singleNarrative(r)]));
out.cross = E.crossNarrative(latest).paragraph;
out.zones = E.zoneSummary(latest);
out.trend = Object.fromEntries(latest.map(r => [r.Entity, E.zTrendSummary(en.filter(x => x.Entity === r.Entity), r.Entity)]));
out.vol = Object.fromEntries(latest.map(r => [r.Entity, E.revenueVolatility(en, r.Entity)]));
out.notch = Object.fromEntries(latest.map(r => [r.Entity, E.notchChange(en, r.Entity)]));
out.paths = {};
for (const [name, p] of Object.entries(inp.scenarios)) {
  out.paths[name] = {};
  for (const r of latest) {
    const pp = Object.assign({}, p, { fuel_cost_share: inp.config.SECTOR_FUEL_COST_SHARE[r.Sector] ?? inp.config.SECTOR_FUEL_COST_SHARE.Other });
    const v = E.revenueVolatility(en, r.Entity);
    pp.revenue_shock_pct = pp.revenue_shock_std_devs * (Number.isFinite(v) ? v : (inp.config.SECTOR_REVENUE_VOLATILITY[r.Sector] ?? 0.15));
    const path = E.costPath(E.runScenario(r, pp, inp.H), 70, null, pp.ead_share ?? 1);
    out.paths[name][r.Entity] = { z: path.map(x => x.Z_EM), efc: path.map(x => x.EFC), rating: path.map(x => x.Rating), sub: path.map(x => x["Direct Fuel Subsidy"]), desc: E.describeShocks(pp) };
  }
}
out.gre = inp.gre.map(([ent, role, link, sov, outl]) => { const g = E.gre(en, ent, role, link, sov, outl); return [g.capped, g.uplifted, g.notches, g.gap]; });
const base = latest.find(r => r.Entity === inp.mc.entity);
const pp = Object.assign({}, inp.scenarios.combined, { fuel_cost_share: 0.25, revenue_shock_pct: 0 });
const mcStats = (sims) => { const fin = sims.map(s => s.path[s.path.length - 1]); return { p50: E.quantile(fin.map(x => x.EFC), 0.5), p95: E.quantile(fin.map(x => x.EFC), 0.95), zp50: E.quantile(fin.map(x => x.Z_EM), 0.5), distress: fin.filter(x => x.Zone === "Distress").length / fin.length }; };
out.mc = mcStats(E.monteCarlo(base, pp, { n: inp.mc.n, fuelSd: 0.10, fxSd: 0.08, rho: 0.30, H: inp.H, lgd: 70, gdp: null }));
const pp4 = Object.assign({}, pp, { revenue_shock_std_devs: -1.0, revenue_sigma: 0.12, revenue_shock_pct: -0.12 });
const sims4 = E.monteCarlo(base, pp4, { n: inp.mc.n, fuelSd: 0.10, fxSd: 0.08, rho: 0.30, rateSd: 150, revSd: 0.8, correlations: inp.mc.corr, H: inp.H, lgd: 70, gdp: null, eadShare: 0.8 });
out.mc4 = mcStats(sims4);
{ // sample moments of the drawn shocks
  const nm = sims4.names, X = nm.map(k => sims4.map(s => s.draw[k]));
  const mu = X.map(a => a.reduce((s, v) => s + v, 0) / a.length);
  const sd = X.map((a, i) => Math.sqrt(a.reduce((s, v) => s + (v - mu[i]) ** 2, 0) / (a.length - 1)));
  const cor = {};
  nm.forEach((a, i) => nm.forEach((b, j) => { if (j > i) cor[a + "|" + b] = X[i].reduce((s, v, k) => s + (v - mu[i]) * (X[j][k] - mu[j]), 0) / (X[i].length - 1) / sd[i] / sd[j]; }));
  out.mom = { names: nm, mu, sd, cor };
}
out.psd = inp.psd.map(c => { try { E.mcFactor(["fuel", "fx", "rate"], { fuel: 0.1, fx: 0.1, rate: 100 }, c); return true; } catch (e) { return false; } });
out.expo = Object.fromEntries(en.map(r => [r.Entity + "|" + r.Year, E.soeExposures(r)]));
out.efcRows = en.map(r => { const a = E.efcRow(r, 65, 0.8, "guaranteed_debt"), b = E.efcRow(r, 65, 0.6); return [a.EAD, a.EFC, a.EAD_source, b.EAD, b.EFC, b.EAD_source]; });
out.match = inp.labels.map(l => E.matchColumn(l));
out.std = E.standardizeColumns(inp.headers).report;
out.q = inp.qtest.map(q => E.quantile(inp.qvals, q));
process.stdout.write(JSON.stringify(out, (k, v) => (typeof v === "number" && !Number.isFinite(v) ? null : v)));
"""


def close(a, b, tol=1e-6):
    if a is None or b is None or (isinstance(a, float) and math.isnan(a)) or (isinstance(b, float) and math.isnan(b)):
        na = a is None or (isinstance(a, float) and math.isnan(a))
        nb = b is None or (isinstance(b, float) and math.isnan(b))
        return na and nb
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def main():
    node = shutil.which("node")
    if not node:
        print("Node.js not found — skipping the engine parity check.")
        return 0
    raw = data_loader.demo_portfolio()
    H = 3
    zero = dict(config.DEFAULT_SHOCK_PARAMS, **{k: 0.0 for k in ["fuel_shock_pct", "fx_shock_pct", "rate_shock_bps", "revenue_shock_std_devs", "refinancing_spread_bps", "arrears_pct_of_revenue"]})
    custom = dict(config.DEFAULT_SHOCK_PARAMS, fuel_shock_pct=-0.2, fx_shock_pct=0.45, rate_shock_bps=-150, revenue_shock_std_devs=1.5,
                  refinancing_spread_bps=600, arrears_pct_of_revenue=-0.1, shock_duration_years=3, tariff_passthrough=0.2)
    subsidy = dict(custom, fuel_shock_pct=0.4, fuel_subsidy_share=0.3, tariff_passthrough=0.5, ead_share=0.6)
    overfull = dict(custom, fuel_shock_pct=0.3, fuel_subsidy_share=0.8, tariff_passthrough=0.5)
    scenarios = {"zero": zero, "combined": dict(config.DEFAULT_SHOCK_PARAMS), "custom": custom, "subsidy": subsidy, "overfull": overfull}
    mc_corr = {"fuel|fx": 0.3, "fuel|rate": 0.2, "fx|rate": 0.4, "fuel|revenue": -0.3, "fx|revenue": -0.2, "rate|revenue": 0.0}
    psd_cases = [{"fuel|fx": 0.3}, {"fuel|fx": 0.9, "fuel|rate": 0.9, "fx|rate": -0.9}, {"fuel|fx": 1.0, "fuel|rate": 1.0, "fx|rate": 1.0},
                 {"fuel|fx": 0.5, "fuel|rate": -0.5, "fx|rate": 0.5}, {"fuel|fx": -0.8, "fuel|rate": -0.8, "fx|rate": -0.8}]
    labels = ["Entity", "entity_name", "Company", "Operating Costs", "Operating Profit", "Finance costs", "Total Liabilites", "Retaind Earnings",
              "Net income (loss)", "Revenue & other income", "EBITDA", "ebit", "Year", "fiscal year", "Govt grants", "Cash & cash equivalents",
              "Guaranteed debt", "Fuel costs", "Short-term borrowings", "fx_debt", "source_file", "audit_status", "Data quality flag",
              "Something else entirely", "Totl Assets", "Curent Liabilities", "Deprecation", "Sector ", "  UNITS", "Profit after tax", "NPAT"]
    headers = ["Entity", "Year", "Sector", "Revenue", "Revenues", "Net Income", "NPAT", "Profit after tax", "Totl Assets", "Total Assets", "Mystery"]
    keys = ["Entity", "Year", "X1", "X2", "X3", "X4", "Z_EM", "Zone", "Rating"] + list(config.KPI_THRESHOLDS)
    gre_cases = [(e, r, l, s, o) for e in ["SOE A", "SOE C", "SOE F", "SOE H"] for r, l in [("Critical", "Integral"), ("Important", "Strong"), ("Limited Importance", "Limited")]
                 for s, o in [("BB", "Stable"), ("BBB", "Negative"), ("B", "Positive")]]
    qvals = [3.1, -2.0, 7.5, 0.4, 0.4, 9.9, -5.5]
    qtest = [0.05, 0.25, 0.5, 0.75, 0.95]
    payload = {
        "engine": str(ROOT / "templates" / "engine.js"), "config": report.config_payload(), "rows": report.rows_payload(raw),
        "keys": keys, "scenarios": scenarios, "H": H, "gre": gre_cases, "mc": {"entity": "SOE F", "n": 5000, "corr": mc_corr},
        "qvals": qvals, "qtest": qtest, "psd": psd_cases, "labels": labels, "headers": headers,
    }
    res = subprocess.run([node, "-e", NODE_RUNNER], input=json.dumps(payload), capture_output=True, text=True, check=True)
    js = json.loads(res.stdout)

    fails = []
    # Python reference
    df = calculations.compute_kpis(calculations.compute_zem_components(data_loader.coerce_numeric(raw)))
    n_extra = 0
    for i, (_, r) in enumerate(df.iterrows()):
        for k in keys:
            a, b = r[k], js["rows"][i][k]
            a = None if (isinstance(a, float) and math.isnan(a)) else (int(a) if k == "Year" else a)
            if not close(a, b, 1e-9):
                fails.append(f"row {i} {r['Entity']} {r['Year']} {k}: py={a} js={b}")
    latest = latest_per_entity(df).sort_values("Z_EM", ascending=False)
    for _, r in latest.iterrows():
        e = r["Entity"]
        if narrative.single_soe_narrative(r) != js["narr"][e]:
            fails.append(f"narrative {e}:\n  py={narrative.single_soe_narrative(r)}\n  js={js['narr'][e]}")
        t = summary.summarize_z_trend(df[df["Entity"] == e], e)
        if t != js["trend"][e]:
            fails.append(f"trend {e}: py={t} js={js['trend'][e]}")
        if not close(calculations.historical_revenue_volatility(df, e), js["vol"][e], 1e-9):
            fails.append(f"vol {e}")
        if list(calculations.rating_notch_change(df, e)) != js["notch"][e]:
            fails.append(f"notch {e}: {calculations.rating_notch_change(df, e)} vs {js['notch'][e]}")
    if narrative.cross_soe_narrative(latest)["paragraph"] != js["cross"]:
        fails.append(f"cross narrative:\n  py={narrative.cross_soe_narrative(latest)['paragraph']}\n  js={js['cross']}")
    if summary.summarize_zone_distribution(latest) != js["zones"]:
        fails.append(f"zone summary: py={summary.summarize_zone_distribution(latest)} js={js['zones']}")
    for name, p in scenarios.items():
        for _, r in latest.iterrows():
            pp = dict(p, fuel_cost_share=config.SECTOR_FUEL_COST_SHARE.get(r["Sector"], config.SECTOR_FUEL_COST_SHARE["Other"]))
            v = calculations.historical_revenue_volatility(df, r["Entity"])
            v = v if v == v else config.SECTOR_REVENUE_VOLATILITY.get(r["Sector"], 0.15)
            pp["revenue_shock_pct"] = pp["revenue_shock_std_devs"] * v
            path = shocks.run_scenario(r, pp, H)
            path["PD"] = path["Rating"].apply(calculations.compute_pd_from_rating)
            path["EFC"] = path["PD"] * (path["Total Liabilities"] * pp.get("ead_share", 1.0)) * 0.7
            j = js["paths"][name][r["Entity"]]
            for t in range(H + 1):
                if not close(path["Z_EM"].iloc[t], j["z"][t], 1e-9) or not close(path["EFC"].iloc[t], j["efc"][t], 1e-9) or path["Rating"].iloc[t] != j["rating"][t]:
                    fails.append(f"path {name} {r['Entity']} t={t}: py={path['Z_EM'].iloc[t]:.6f}/{path['Rating'].iloc[t]} js={j['z'][t]}/{j['rating'][t]}")
                if not close(path["Direct Fuel Subsidy"].iloc[t], j["sub"][t], 1e-9):
                    fails.append(f"fuel subsidy {name} {r['Entity']} t={t}: py={path['Direct Fuel Subsidy'].iloc[t]} js={j['sub'][t]}")
            if shocks.describe_active_shocks(pp) != j["desc"]:
                fails.append(f"describe {name}: py={shocks.describe_active_shocks(pp)} js={j['desc']}")
    # GRE — replicate strategic_soe.py logic in Python for the same cases
    for (e, role, link, sov, outl), (jt, ju, jn, jg) in zip(gre_cases, js["gre"]):
        d = df[df["Entity"] == e].sort_values("Year")
        sacp = d.iloc[-1]["Rating"]; si = config.rating_index(sacp); vi = config.rating_index(sov)
        tier = config.role_link_to_likelihood(role, link)
        fr, lr, nc = calculations.rating_notch_change(df, e)
        trig = (nc is not None and nc <= -config.DYNAMIC_CAP_TRIGGER_NOTCHES) or outl == "Negative"
        order = config.LIKELIHOOD_TIERS_ASC
        capped = config.DYNAMIC_CAP_TIER if trig and order.index(tier) > order.index(config.DYNAMIC_CAP_TIER) else tier
        spec = config.LIKELIHOOD_UPLIFT[capped]; m, g = spec["max_notches"], spec["min_gap_to_sovereign"]
        if si is None or vi is None or m == 0:
            ui = si
        else:
            ceil = vi - (g or 0); target = si + m if m is not None else ceil; ui = max(si, min(target, ceil))
        exp = [capped, config.RATING_SCALE_ASC[ui], ui - si, vi - ui]
        if exp != [jt, ju, jn, jg]:
            fails.append(f"GRE {e} {role}/{link} {sov} {outl}: py={exp} js={[jt, ju, jn, jg]}")
    # quantile definition
    for q, jv in zip(qtest, js["q"]):
        if not close(float(np.quantile(qvals, q)), jv, 1e-12):
            fails.append(f"quantile {q}")
    # Monte Carlo: different random generators, so compare distributions (5,000 draws)
    base = latest[latest["Entity"] == "SOE F"].iloc[0]
    pp = dict(config.DEFAULT_SHOCK_PARAMS, fuel_cost_share=0.25, revenue_shock_pct=0.0)
    mc = shocks.run_monte_carlo(base, pp, n_sims=5000, fuel_std=0.10, fx_std=0.08, correlation=0.30, horizon_years=H, lgd_pct=70)
    fin = mc[mc["Projection Year"] == H]
    py_mc = {"p50": fin["EFC"].quantile(0.5), "p95": fin["EFC"].quantile(0.95), "zp50": fin["Z_EM"].quantile(0.5), "distress": (fin["Zone"] == "Distress").mean()}
    for k, v in py_mc.items():
        rel = abs(v - js["mc"][k]) / max(abs(v), 1e-9)
        tol = 0.03 if k != "distress" else 0.05
        if rel > tol and abs(v - js["mc"][k]) > 0.01:
            fails.append(f"MC {k}: py={v:.6g} js={js['mc'][k]:.6g} (rel {rel:.3f})")
    print("Monte Carlo (5,000 draws, SOE F, standard stress):", {k: (round(v, 4), round(js["mc"][k], 4)) for k, v in py_mc.items()})
    # four-variable Monte Carlo (rate and revenue drawn, full correlation matrix, EAD 80%)
    pp4 = dict(pp, revenue_shock_std_devs=-1.0, revenue_sigma=0.12, revenue_shock_pct=-0.12)
    mc4 = shocks.run_monte_carlo(base, pp4, n_sims=5000, fuel_std=0.10, fx_std=0.08, correlation=0.30, horizon_years=H, lgd_pct=70,
                                 rate_std_bps=150, revenue_std_sd=0.8, correlations=mc_corr, ead_share=0.8)
    fin4 = mc4[mc4["Projection Year"] == H]
    py4 = {"p50": fin4["EFC"].quantile(0.5), "p95": fin4["EFC"].quantile(0.95), "zp50": fin4["Z_EM"].quantile(0.5), "distress": (fin4["Zone"] == "Distress").mean()}
    for k, v in py4.items():
        rel = abs(v - js["mc4"][k]) / max(abs(v), 1e-9)
        # the 95th percentile of EFC jumps between rating bands, so it is the noisiest statistic
        if rel > {"p50": 0.03, "p95": 0.06, "zp50": 0.03, "distress": 0.08}[k] and abs(v - js["mc4"][k]) > 0.01:
            fails.append(f"MC4 {k}: py={v:.6g} js={js['mc4'][k]:.6g} (rel {rel:.3f})")
    print("Monte Carlo, 4 variables:", {k: (round(v, 4), round(js["mc4"][k], 4)) for k, v in py4.items()})
    mom = js["mom"]
    target_mu = {"fuel": pp4["fuel_shock_pct"], "fx": pp4["fx_shock_pct"], "rate": pp4["rate_shock_bps"], "revenue": pp4["revenue_shock_std_devs"]}
    target_sd = {"fuel": 0.10, "fx": 0.08, "rate": 150, "revenue": 0.8}
    for i, nm in enumerate(mom["names"]):
        if abs(mom["mu"][i] - target_mu[nm]) > 4 * target_sd[nm] / math.sqrt(5000) or abs(mom["sd"][i] / target_sd[nm] - 1) > 0.05:
            fails.append(f"MC4 draws {nm}: mean {mom['mu'][i]:.4g} (target {target_mu[nm]}), sd {mom['sd'][i]:.4g} (target {target_sd[nm]})")
    for pair, c in mom["cor"].items():
        a, b = pair.split("|")
        if abs(c - mc_corr.get(pair, mc_corr.get(f"{b}|{a}", 0.0))) > 0.05:
            fails.append(f"MC4 draw correlation {pair}: {c:.3f} vs target {mc_corr.get(pair)}")
    # correlation matrix consistency check
    for c, jok in zip(psd_cases, js["psd"]):
        try:
            shocks.mc_covariance(["fuel", "fx", "rate"], {"fuel": 0.1, "fx": 0.1, "rate": 100}, c); pok = True
        except ValueError:
            pok = False
        if pok != jok:
            fails.append(f"PSD check {c}: py={pok} js={jok}")
    # bottom-up exposures and EFC with EAD options
    for _, r in df.iterrows():
        pe = calculations.soe_exposures(r); je = js["expo"][f"{r['Entity']}|{int(r['Year'])}"]
        for k, (v, src) in pe.items():
            if not close(v, je[k][0], 1e-12) or src != je[k][1]:
                fails.append(f"exposure {r['Entity']} {int(r['Year'])} {k}: py={(v, src)} js={je[k]}")
        n_extra += len(pe)
    ga = calculations.compute_efc(df, 65, ead_share=0.8, ead_basis="guaranteed_debt")
    gb = calculations.compute_efc(df, 65, ead_share=0.6)
    for i in range(len(df)):
        exp = [ga["EAD"].iloc[i], ga["EFC"].iloc[i], ga["EAD_source"].iloc[i], gb["EAD"].iloc[i], gb["EFC"].iloc[i], gb["EAD_source"].iloc[i]]
        for a, b in zip(exp, js["efcRows"][i]):
            if not close(a if isinstance(a, str) else float(a), b, 1e-12):
                fails.append(f"EFC/EAD row {i}: py={exp} js={js['efcRows'][i]}"); break
        n_extra += 6
    # column matching (schema.py)
    import pandas as pd
    import schema
    for lab, jm in zip(labels, js["match"]):
        pm = list(schema.match_column(lab))
        if pm[0] != jm[0] or pm[1] != jm[1] or not close(pm[2], jm[2], 1e-9):
            fails.append(f"match {lab!r}: py={pm} js={jm}")
    _, rep_df = schema.standardize_columns(pd.DataFrame(columns=headers))
    if rep_df.to_dict("records") != js["std"]:
        fails.append(f"standardize_columns:\n  py={rep_df.to_dict('records')}\n  js={js['std']}")
    n_extra += len(labels) + 1 + len(psd_cases) + 4

    n_checks = len(js["rows"]) * len(keys) + len(latest) * (5 + len(scenarios) * (2 * H + 3)) + len(gre_cases) + len(qtest) + 6 + n_extra
    if fails:
        print(f"{len(fails)} mismatches:")
        print("\n".join(fails[:40]))
        return 1
    print(f"OK — JS engine matches Python on {n_checks} checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
