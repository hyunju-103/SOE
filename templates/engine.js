/*
 * SOE Fiscal Risk Tool — calculation engine, JavaScript port.
 *
 * Mirrors, function for function, the Python modules the Streamlit app uses:
 *   calculations.py  (Z''-EM, KPIs, classify, PD/EFC, revenue volatility, notch change)
 *   shocks.py        (run_scenario, kpi_impact_table, gdp_path, Monte Carlo, percentile path)
 *   narrative.py     (single_soe_narrative, cross_soe_narrative)
 *   utils/summary.py (summarize_z_trend, summarize_zone_distribution)
 *   app_pages/strategic_soe.py (GRE support uplift)
 *   schema.py        (column matching: exact name, synonym, close spelling)
 * Every number it uses (coefficients, cutoffs, rating/PD table, sector tables,
 * shock defaults, GRE tables) comes from config.py via the CFG object that
 * report.py embeds, so recalibrating config.py needs no change here.
 * A change to a FORMULA in the Python modules must be copied here too;
 * tests/check_engine_parity.py compares the two implementations.
 */
(function (root) {
  "use strict";

  function create(CFG) {
    const INF = Infinity;
    const isNum = (v) => typeof v === "number" && Number.isFinite(v);
    const div = (a, b) => (isNum(a) && isNum(b) && b !== 0 ? a / b : NaN); // _safe_div: inf -> NaN
    const lo = (v) => (v === null || v === undefined ? -INF : v);
    const hi = (v) => (v === null || v === undefined ? INF : v);
    const ZCOMP = Object.keys(CFG.ZEM_COEFFICIENTS); // X1..X4 in config order
    const ZONES = CFG.ZONES.map(([n, a, b]) => [n, lo(a), hi(b)]);
    const RTABLE = CFG.Z_RATING_TABLE.map(([a, b, r, p]) => [lo(a), hi(b), r, p]);
    const PD_BY_RATING = Object.fromEntries(RTABLE.map((r) => [r[2], r[3]]));
    const K = {
      rev: "Revenues", texp: "Total Expense", opex: "Operating Expense", ebit: "Operating Profits (EBIT)",
      ni: "Net Income", ca: "Current Assets", ta: "Total Assets", cl: "Current Liabilities", tl: "Total Liabilities",
      eq: "Equity", re: "Retained Earnings", int: "Interest Expense", tax: "Tax Expense", ebitda: "EBITDA",
      grants: "Government Grants", dep: "Depreciation",
    };

    /* ---------------- calculations.py ---------------- */
    function classifyZone(z) {
      if (!isNum(z)) return "Unknown";
      for (const [name, a, b] of ZONES) if (a < z && z <= b) return name;
      return "Unknown";
    }
    function zRating(z) {
      if (!isNum(z)) return "—";
      for (const [a, b, r] of RTABLE) if ((a < z && z <= b) || (a === -INF && z <= b)) return r;
      return "—";
    }
    function zemFromValues(wc, ta, re, ebit, eq, tl) {
      const x1 = ta ? wc / ta : NaN, x2 = ta ? re / ta : NaN, x3 = ta ? ebit / ta : NaN, x4 = tl ? eq / tl : NaN;
      const c = CFG.ZEM_COEFFICIENTS;
      const z = c.X1 * x1 + c.X2 * x2 + c.X3 * x3 + c.X4 * x4 + CFG.ZEM_CONSTANT;
      return { X1: x1, X2: x2, X3: x3, X4: x4, Z_EM: z, Zone: classifyZone(z) };
    }
    /** compute_zem_components + compute_kpis on one row (returns a new object). */
    function enrichRow(r) {
      const o = Object.assign({}, r);
      o.X1 = div(r[K.ca] - r[K.cl], r[K.ta]);
      o.X2 = div(r[K.re], r[K.ta]);
      o.X3 = div(r[K.ebit], r[K.ta]);
      o.X4 = div(r[K.eq], r[K.tl]);
      let z = CFG.ZEM_CONSTANT;
      for (const c of ZCOMP) { o[c + "_contrib"] = o[c] * CFG.ZEM_COEFFICIENTS[c]; z += o[c + "_contrib"]; }
      o.Z_EM = z; o.Zone = classifyZone(z); o.Rating = zRating(z);
      const rev = r[K.rev], ebit = r[K.ebit], eq = r[K.eq], ebitda = r[K.ebitda];
      o.operating_margin = div(ebit, rev);
      o.net_margin = div(r[K.ni], rev);
      o.ebitda_margin = div(ebitda, rev);
      o.roa = div(r[K.ni], r[K.ta]);
      o.roe = eq > 0 ? div(r[K.ni], eq) : NaN;
      o.current_ratio = div(r[K.ca], r[K.cl]);
      o.working_capital_ratio = o.X1;
      o.debt_to_ebitda = ebitda > 0 ? div(r[K.tl], ebitda) : NaN;
      o.liabilities_to_assets = div(r[K.tl], r[K.ta]);
      o.interest_coverage = div(ebit, r[K.int]);
      o.debt_to_equity = eq > 0 ? div(r[K.tl], eq) : NaN;
      o.asset_turnover = div(rev, r[K.ta]);
      o.depreciation_to_ebitda = ebitda > 0 ? div(r[K.dep], ebitda) : NaN;
      o.grants_to_revenue = div(r[K.grants], rev);
      o.grants_to_expense = div(r[K.grants], r[K.texp]);
      o.effective_tax_rate = ebit > 0 ? div(r[K.tax], ebit) : NaN;
      o.negative_equity_flag = eq <= 0;
      o.negative_ebitda_flag = ebitda <= 0;
      return o;
    }
    const enrich = (rows) => rows.map(enrichRow);

    function availableKpis(rows, category) {
      const keys = category ? CFG.KPI_CATEGORIES[category] : Object.keys(CFG.KPI_THRESHOLDS);
      return keys.filter((k) => CFG.KPI_THRESHOLDS[k].requires.every((c) => rows.some((r) => isNum(r[c]))));
    }
    function classify(value, key) {
      if (!isNum(value)) return ["No data", "muted"];
      const s = CFG.KPI_THRESHOLDS[key];
      if (s.direction === "higher_is_better") {
        if (value < s.red_cut) return ["Red", "red"];
        if (value >= s.green_cut) return ["Green", "green"];
        return ["Amber", "amber"];
      }
      if (value > s.red_cut) return ["Red", "red"];
      if (value <= s.green_cut) return ["Green", "green"];
      return ["Amber", "amber"];
    }
    const pdByRating = (rating) => (rating in PD_BY_RATING ? PD_BY_RATING[rating] : NaN);
    function worstPdInZone(zone) {
      const z = ZONES.find((x) => x[0] === zone);
      if (!z) return NaN;
      const cands = RTABLE.filter(([a, b]) => b > z[1] && a < z[2]).map((r) => r[3]);
      return cands.length ? Math.max(...cands) : NaN;
    }
    const pctLabel = (v) => Math.round(v * 100) + "%";
    /** compute_efc for one row. basis "total_liabilities": EAD = share × total liabilities (proxy);
     *  "guaranteed_debt": observed Government Guaranteed Debt where reported, else the proxy. */
    function efcRow(r, lgdPct, eadShare = 1, basis = "total_liabilities") {
      const pd = pdByRating(r.Rating), lgd = lgdPct / 100, g = r["Government Guaranteed Debt"];
      let ead = r[K.tl] * eadShare, src = `Proxy: ${pctLabel(eadShare)} of total liabilities`;
      if (basis === "guaranteed_debt" && isNum(g)) { ead = g; src = "Observed: guaranteed debt"; }
      return { PD: pd, EAD: ead, LGD: lgd, EFC: pd * ead * lgd, EAD_source: src };
    }
    /** soe_exposures: bottom-up shock exposures for one SOE-year → {name: [value, source]} */
    function soeExposures(row) {
      const clip = (v) => Math.max(0, Math.min(1, v));
      const val = (c) => (c && isNum(row[c]) ? row[c] : null);
      const opex = val(K.opex), tl = val(K.tl), sector = row.Sector || "Other", out = {};
      const pick = (name, obs, amt, denom, lab) => {
        const v = obs ? val(obs) : null;
        if (v !== null) { out[name] = [clip(v), `Observed: ${obs}`]; return; }
        const a = amt ? val(amt) : null;
        if (a !== null && denom) { out[name] = [clip(a / denom), `Derived: ${lab}`]; return; }
        if (name === "fuel_cost_share") { out[name] = [CFG.SECTOR_FUEL_COST_SHARE[sector] ?? CFG.SECTOR_FUEL_COST_SHARE.Other, `Sector default (${sector})`]; return; }
        out[name] = [CFG.DEFAULT_EXPOSURES[name], "Default (placeholder)"];
      };
      pick("fuel_cost_share", "Fuel Cost Share", "Fuel Cost", opex, "Fuel Cost / Operating Expense");
      pick("fx_cost_share", "FX Cost Share");
      pick("fx_revenue_share", "FX Revenue Share");
      pick("fx_debt_share", "FX Debt Share", "FX Debt", tl, "FX Debt / Total Liabilities");
      pick("floating_debt_share", "Floating Rate Debt Share");
      pick("near_term_maturity_share", null, "Short Term Debt", tl, "Short Term Debt / Total Liabilities");
      for (const name of ["tariff_passthrough", "revenue_elasticity", "fuel_subsidy_share"]) out[name] = [CFG.DEFAULT_EXPOSURES[name], name === "fuel_subsidy_share" ? "User (off by default)" : "Default (placeholder)"];
      return out;
    }
    function recoveryScenarios(sector) {
      const d = CFG.SECTOR_RECOVERY_DATA[sector] || CFG.SECTOR_RECOVERY_DATA.Other;
      const r4 = (v) => Math.round(v * 1e4) / 1e4;
      return [["Low Backstop Intensity", r4(d.p10)], ["25th Percentile", r4(d.p25)], ["Average Backstop Intensity", r4(d.average)], ["High Backstop Intensity", r4(d.p90)]];
    }
    const byYear = (rows) => rows.slice().sort((a, b) => a.Year - b.Year);
    function std(a) { const n = a.length; if (n < 2) return NaN; const m = a.reduce((s, v) => s + v, 0) / n; return Math.sqrt(a.reduce((s, v) => s + (v - m) ** 2, 0) / (n - 1)); }
    function revenueVolatility(rows, entity) {
      const rev = byYear(rows.filter((r) => r.Entity === entity)).map((r) => r[K.rev]).filter((v) => v !== null && v !== undefined && !Number.isNaN(v));
      if (rev.length < 3) return NaN;
      const g = [];
      for (let i = 1; i < rev.length; i++) g.push(rev[i] / rev[i - 1] - 1);
      if (g.length < 2 || g.some((v) => !isNum(v))) return NaN;
      return std(g);
    }
    const ratingIndex = (r) => { const i = CFG.RATING_SCALE_ASC.indexOf(r); return i < 0 ? null : i; };
    function notchChange(rows, entity) {
      const d = byYear(rows.filter((r) => r.Entity === entity && r.Rating !== undefined && r.Rating !== null));
      if (d.length < 2) return [null, null, null];
      const f = d[0].Rating, l = d[d.length - 1].Rating, fi = ratingIndex(f), li = ratingIndex(l);
      if (fi === null || li === null) return [f, l, null];
      return [f, l, li - fi];
    }
    function latestPerEntity(rows) {
      const m = new Map();
      for (const r of byYear(rows)) m.set(r.Entity, r);
      return [...m.values()];
    }

    /* ---------------- shocks.py ---------------- */
    function runScenario(base, p, H) {
      const dur = p.shock_duration_years;
      const st = {
        EBIT: base[K.ebit], Interest: base[K.int], RE: base[K.re], Equity: base[K.eq], TL: base[K.tl], TA: base[K.ta],
        CA: base[K.ca], CL: base[K.cl], Revenue: base[K.rev], OpEx: base[K.opex],
      };
      st.FuelSubsidy = 0;
      const out = [snap(base, 0, st)];
      const sub = p.fuel_subsidy_share || 0;
      for (let t = 1; t <= H; t++) {
        const active = t <= dur;
        let dFuel = 0, dFx = 0, dRev = 0, dInt = 0, dReval = 0, dArr = 0, fuelSub = 0;
        if (active) {
          // fuel-cost change split: tariff pass-through (Case B), government subsidy (Case C), rest absorbed (Case A)
          const inc = p.fuel_cost_share * st.OpEx * p.fuel_shock_pct;
          dFuel = -inc * Math.max(0, 1 - p.tariff_passthrough - sub);
          fuelSub = inc * sub;
          dFx = -(p.fx_cost_share * st.OpEx - p.fx_revenue_share * st.Revenue) * p.fx_shock_pct;
          dRev = p.revenue_elasticity * (p.revenue_shock_pct || 0) * st.Revenue;
          const dRate = p.floating_debt_share * st.TL * (p.rate_shock_bps / 10000);
          const dRefi = (p.near_term_maturity_share || 0) * st.TL * ((p.refinancing_spread_bps || 0) / 10000);
          dInt = dRate + dRefi;
          dReval = -p.fx_debt_share * st.TL * p.fx_shock_pct;
          dArr = -p.arrears_pct_of_revenue * st.Revenue;
        }
        const ebit = base[K.ebit] + dFuel + dFx + dRev;
        const interest = base[K.int] + dInt;
        const ni = base[K.ni] + (dFuel + dFx + dRev) - dInt;
        const gap = Math.max(0, -ni);
        st.RE += ni;
        st.Equity += ni + dReval;
        st.TL += gap - dReval;
        st.CA += dArr;
        st.TA += ni + dArr;
        st.EBIT = ebit; st.Interest = interest; st.FuelSubsidy = fuelSub;
        out.push(snap(base, t, st));
      }
      return out;
    }
    function snap(base, t, st) {
      const z = zemFromValues(st.CA - st.CL, st.TA, st.RE, st.EBIT, st.Equity, st.TL);
      return {
        Entity: base.Entity, Sector: base.Sector, "Calendar Year": base.Year + t, "Projection Year": t,
        EBIT: st.EBIT, "Interest Expense": st.Interest, "Retained Earnings": st.RE, Equity: st.Equity,
        "Total Liabilities": st.TL, "Total Assets": st.TA, "Current Assets": st.CA, "Current Liabilities": st.CL,
        X1: z.X1, X2: z.X2, X3: z.X3, X4: z.X4, Z_EM: z.Z_EM, Zone: z.Zone, Rating: zRating(z.Z_EM),
        "Direct Fuel Subsidy": st.FuelSubsidy || 0,
      };
    }
    /** adds PD, EAD (share × total liabilities), LGD, EFC (and EFC/GDP when a GDP path is given) to a scenario path */
    function costPath(path, lgdPct, gdpSeries, eadShare = 1) {
      return path.map((r, i) => {
        const pd = pdByRating(r.Rating), ead = r["Total Liabilities"] * eadShare, efc = pd * ead * (lgdPct / 100);
        return Object.assign({}, r, { PD: pd, EAD: ead, LGD: lgdPct / 100, EFC: efc, GDP: gdpSeries ? gdpSeries[i] : NaN, EFC_GDP: gdpSeries ? efc / gdpSeries[i] : NaN });
      });
    }
    function kpiImpact(path) {
      const b = path[0], f = path[path.length - 1];
      return ZCOMP.map((c) => ({ Component: CFG.ZEM_LABELS[c], key: c, base: b[c], final: f[c], change: f[c] - b[c], weighted: (f[c] - b[c]) * CFG.ZEM_COEFFICIENTS[c] }));
    }
    const gdpPath = (g0, g, H) => Array.from({ length: H + 1 }, (_, t) => g0 * (1 + g) ** t);
    const pyPlus0 = (v) => { const r = Math.round(v); return (r >= 0 && !Object.is(r, -0) ? "+" : "") + String(r).replace("-0", "0"); };
    function describeShocks(p) {
      const parts = [];
      if (p.fuel_shock_pct) parts.push(`Fuel ${pyPlus0(p.fuel_shock_pct * 100)}%`);
      if (p.fx_shock_pct) parts.push(`FX ${pyPlus0(p.fx_shock_pct * 100)}%`);
      if (p.rate_shock_bps) parts.push(`Rate ${pyPlus0(p.rate_shock_bps)}bps`);
      if (p.revenue_shock_pct) {
        const s = p.revenue_shock_std_devs;
        parts.push(s ? `Revenue ${(s >= 0 ? "+" : "") + s.toFixed(1)}σ` : `Revenue ${pyPlus0(p.revenue_shock_pct * 100)}%`);
      }
      if (p.refinancing_spread_bps && (p.near_term_maturity_share || 0) > 0) parts.push(`Refi ${pyPlus0(p.refinancing_spread_bps)}bps`);
      if (p.arrears_pct_of_revenue) parts.push(`Arrears ${pyPlus0(p.arrears_pct_of_revenue * 100)}%/yr`);
      if (p.fuel_subsidy_share && p.fuel_shock_pct) parts.push(`gov. absorbs ${Math.round(p.fuel_subsidy_share * 100)}% of fuel cost change`);
      if (!parts.length) return "No shock applied (baseline)";
      return parts.join(", ") + (p.shock_duration_years ? ` — active ${p.shock_duration_years}yr` : "");
    }
    // Seeded generator (mulberry32) + Box–Muller, so identical settings reproduce identical draws.
    function rng(seed) {
      let a = seed >>> 0, spare = null;
      const u = () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
      return () => {
        if (spare !== null) { const s = spare; spare = null; return s; }
        let x = 0, y = 0;
        while (x === 0) x = u();
        y = u();
        const m = Math.sqrt(-2 * Math.log(x));
        spare = m * Math.sin(2 * Math.PI * y);
        return m * Math.cos(2 * Math.PI * y);
      };
    }
    /** Jacobi eigen-decomposition of a small symmetric matrix → {values, vectors (columns)} */
    function symEig(M0) {
      const n = M0.length, A = M0.map((r) => r.slice()), V = A.map((_, i) => A.map((__, j) => (i === j ? 1 : 0)));
      for (let sweep = 0; sweep < 100; sweep++) {
        let off = 0;
        for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) off += A[i][j] * A[i][j];
        if (off < 1e-24) break;
        for (let p = 0; p < n; p++) for (let q = p + 1; q < n; q++) {
          if (Math.abs(A[p][q]) < 1e-300) continue;
          const th = (A[q][q] - A[p][p]) / (2 * A[p][q]);
          const t = (th >= 0 ? 1 : -1) / (Math.abs(th) + Math.sqrt(th * th + 1)), c = 1 / Math.sqrt(t * t + 1), s = t * c;
          for (let k = 0; k < n; k++) { const a = A[k][p], b = A[k][q]; A[k][p] = c * a - s * b; A[k][q] = s * a + c * b; }
          for (let k = 0; k < n; k++) { const a = A[p][k], b = A[q][k]; A[p][k] = c * a - s * b; A[q][k] = s * a + c * b; }
          for (let k = 0; k < n; k++) { const a = V[k][p], b = V[k][q]; V[k][p] = c * a - s * b; V[k][q] = s * a + c * b; }
        }
      }
      return { values: A.map((r, i) => r[i]), vectors: V };
    }
    const MC_VARIABLES = ["fuel", "fx", "rate", "revenue"];
    const corrOf = (corrs, a, b) => (corrs[`${a}|${b}`] ?? corrs[`${b}|${a}`] ?? 0);
    /** mc_covariance's check + a factor F with F·Fᵀ = covariance (eigen-based, so a semi-definite matrix works).
     *  Throws when the correlations are inconsistent (matrix not positive semi-definite). */
    function mcFactor(names, sds, corrs) {
      const k = names.length, R = names.map((a, i) => names.map((b, j) => (i === j ? 1 : corrOf(corrs, a, b))));
      const { values, vectors } = symEig(R);
      if (Math.min(...values) < -1e-10) throw new Error("The shock correlations are inconsistent (the correlation matrix is not positive semi-definite). Lower some of them.");
      return names.map((a, i) => values.map((lam, j) => sds[a] * vectors[i][j] * Math.sqrt(Math.max(0, lam))));
    }
    /** run_monte_carlo. Fuel and FX are always drawn around the slider values; the interest-rate shock (bps) and
     *  the revenue shock (standard deviations of own revenue growth) are drawn too when their std. dev. is > 0.
     *  o: {n, fuelSd, fxSd, rho, rateSd, revSd, correlations, H, lgd, gdp, seed, eadShare}. With only fuel and FX
     *  drawn, the draws are the same as the original two-variable version for the same seed. */
    function monteCarlo(base, p, o) {
      const g = rng(o.seed ?? 42), sims = [], n = o.n, H = o.H;
      const corrs = Object.assign({}, o.correlations || {});
      if (!("fuel|fx" in corrs)) corrs["fuel|fx"] = o.rho ?? 0;
      const names = ["fuel", "fx"].concat((o.rateSd || 0) > 0 ? ["rate"] : [], (o.revSd || 0) > 0 ? ["revenue"] : []);
      const means = { fuel: p.fuel_shock_pct, fx: p.fx_shock_pct, rate: p.rate_shock_bps || 0, revenue: p.revenue_shock_std_devs || 0 };
      const sds = { fuel: o.fuelSd, fx: o.fxSd, rate: o.rateSd || 0, revenue: o.revSd || 0 };
      let draw;
      if (names.length === 2) {
        const rho = corrs["fuel|fx"], c = Math.sqrt(Math.max(0, 1 - rho * rho));
        draw = () => { const z1 = g(), z2 = g(); return [means.fuel + sds.fuel * z1, means.fx + sds.fx * (rho * z1 + c * z2)]; };
      } else {
        const F = mcFactor(names, sds, corrs);
        draw = () => { const z = names.map(() => g()); return names.map((nm, i) => means[nm] + F[i].reduce((s, f, j) => s + f * z[j], 0)); };
      }
      let sigma = p.revenue_sigma ?? null;
      if (sigma === null && p.revenue_shock_std_devs) sigma = (p.revenue_shock_pct || 0) / p.revenue_shock_std_devs;
      if (names.includes("revenue") && sigma === null) throw new Error("revenue_sigma is needed to draw revenue shocks");
      for (let i = 0; i < n; i++) {
        const d = Object.fromEntries(names.map((nm, k) => [nm, 0])), v = draw();
        names.forEach((nm, k) => { d[nm] = v[k]; });
        const sp = Object.assign({}, p, { fuel_shock_pct: d.fuel, fx_shock_pct: d.fx });
        if ("rate" in d) sp.rate_shock_bps = d.rate;
        if ("revenue" in d) { sp.revenue_shock_std_devs = d.revenue; sp.revenue_shock_pct = d.revenue * sigma; }
        sims.push({ fuel: d.fuel, fx: d.fx, draw: d, path: costPath(runScenario(base, sp, H), o.lgd, o.gdp || null, o.eadShare ?? 1) });
      }
      sims.names = names;
      return sims;
    }
    /** pandas/numpy default (linear) quantile */
    function quantile(values, q) {
      const a = values.filter(isNum).sort((x, y) => x - y);
      if (!a.length) return NaN;
      const pos = (a.length - 1) * q, i = Math.floor(pos), f = pos - i;
      return i + 1 < a.length ? a[i] + f * (a[i + 1] - a[i]) : a[i];
    }
    function percentilePath(sims, key, qs = [0.05, 0.25, 0.5, 0.75, 0.95]) {
      const H = sims[0].path.length;
      return Array.from({ length: H }, (_, t) => {
        const vals = sims.map((s) => s.path[t][key]);
        const o = { t, year: sims[0].path[t]["Calendar Year"] };
        qs.forEach((q) => { o["p" + Math.round(q * 100)] = quantile(vals, q); });
        return o;
      });
    }

    /* ---------------- narrative.py ---------------- */
    function bucket(comp, v) {
      if (!isNum(v)) return "weak_positive";
      if (v < 0) return "negative";
      return v >= CFG.ZEM_COMPONENT_STRONG_THRESHOLD[comp] ? "strong_positive" : "weak_positive";
    }
    const describe = (comp, v) => CFG.ZEM_DESCRIPTORS[comp][bucket(comp, v)];
    const capitalize = (s) => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
    const f2 = (v) => (isNum(v) ? v.toFixed(2) : "nan");
    function ranked(row) {
      return ZCOMP.map((c) => [c, row[c + "_contrib"]]).sort((a, b) => a[1] - b[1]);
    }
    function singleNarrative(row) {
      const entity = row.Entity || "This SOE", zone = row.Zone;
      const rk = ranked(row), totalAbs = rk.reduce((s, kv) => s + Math.abs(kv[1]), 0);
      const [negC, negV] = rk[0], [posC, posV] = rk[rk.length - 1];
      const out = [`**${entity} sits in the ${zone} zone (Z-EM = ${f2(row.Z_EM)}).**`];
      if (posV > 0) {
        const share = totalAbs ? Math.abs(posV) / totalAbs : 0, d = describe(posC, row[posC]);
        out.push(share >= CFG.SINGLE_DRIVER_SHARE_THRESHOLD
          ? `The classification is driven almost entirely by ${d} (${CFG.ZEM_LABELS[posC]} = ${f2(row[posC])}).`
          : `${capitalize(d)} (${CFG.ZEM_LABELS[posC]} = ${f2(row[posC])}) is the largest positive contributor.`);
      }
      if (negV < 0) out.push(`The main drag is ${describe(negC, row[negC])} (${CFG.ZEM_LABELS[negC]} = ${f2(row[negC])}).`);
      const nNeg = ZCOMP.filter((c) => row[c] < 0).length;
      if (nNeg >= 3 && zone !== "Distress") out.push(`Three or more components are negative even though the headline classification is ${zone} — worth flagging as a fragile score carried by a narrow base.`);
      else if (nNeg <= 1 && zone === "Distress") out.push("Most components are positive despite the Distress classification — the score is being pulled down by a concentrated weakness rather than broad-based deterioration.");
      else if (nNeg === 4) out.push("This is broad-based distress, not a single-metric problem.");
      return out.join(" ");
    }
    function crossNarrative(rows) {
      if (!rows.length) return { paragraph: "No data available for this selection.", table: [] };
      const table = rows.map((row) => {
        const rk = ranked(row), totalAbs = rk.reduce((s, kv) => s + Math.abs(kv[1]), 0);
        const [posC, posV] = rk[rk.length - 1];
        const share = totalAbs ? Math.abs(posV) / totalAbs : 0;
        let flag = "";
        if (share >= CFG.SINGLE_DRIVER_SHARE_THRESHOLD) {
          const nNeg = ZCOMP.filter((c) => row[c] < 0).length;
          flag = nNeg >= 2 ? `Single-driver classification — weak on ${nNeg} of 4 components` : "Single-driver classification";
        }
        return { Entity: row.Entity || "", Sector: row.Sector || "", Z_EM: row.Z_EM, Zone: row.Zone, "Primary driver": CFG.ZEM_LABELS[posC], Flag: flag };
      }).sort((a, b) => b.Z_EM - a.Z_EM);
      const cnt = (z) => table.filter((r) => r.Zone === z).length;
      const nSingle = table.filter((r) => r.Flag).length;
      const parts = [`Of ${table.length} SOEs assessed, ${cnt("Safe")} sit in Safe, ${cnt("Grey")} in Grey, and ${cnt("Distress")} in Distress.`];
      if (nSingle > 0) parts.push(`${nSingle} SOE${nSingle !== 1 ? "s" : ""} ${nSingle !== 1 ? "have" : "has"} a classification driven primarily by a single component rather than a broad financial position — worth monitoring for fragility.`);
      const sectors = [...new Set(table.map((r) => r.Sector))];
      if (sectors.length > 1) {
        const means = sectors.sort().map((s) => { const v = table.filter((r) => r.Sector === s).map((r) => r.Z_EM); return [s, v.reduce((a, b) => a + b, 0) / v.length]; }).sort((a, b) => a[1] - b[1]);
        const [w, wm] = means[0], [s, sm] = means[means.length - 1];
        if (wm < sm) parts.push(`${w} SOEs show systematically weaker Z-EM scores (mean ${f2(wm)}) than ${s} SOEs (mean ${f2(sm)}) in this sample — flagged as a sector-level pattern rather than a firm-specific one, though the sample size here is small.`);
      }
      return { paragraph: parts.join(" "), table };
    }

    /* ---------------- utils/summary.py ---------------- */
    function zTrendSummary(rows, name) {
      const d = byYear(rows.filter((r) => isNum(r.Z_EM)));
      if (d.length < 2) return `Not enough time points to describe a trend for ${name}.`;
      const a = d[0].Z_EM, b = d[d.length - 1].Z_EM, ch = b - a;
      const dir = ch > 0 ? "improved" : ch < 0 ? "declined" : "held steady";
      return `${name}'s Z-EM score ${dir} from ${f2(a)} in ${d[0].Year} to ${f2(b)} in ${d[d.length - 1].Year}, ending in the ${String(d[d.length - 1].Zone).toLowerCase()} zone.`;
    }
    function zoneSummary(rows) {
      if (!rows.length) return "No data available for this selection.";
      const n = rows.length, c = (z) => rows.filter((r) => r.Zone === z).length;
      const parts = [`${c("Distress")} of ${n} SOEs are in the distress zone (Z-EM ≤ ${CFG.Z_DISTRESS_CUTOFF})`];
      if (c("Grey")) parts.push(`${c("Grey")} in the grey zone`);
      if (c("Safe")) parts.push(`${c("Safe")} in the safe zone`);
      let s = parts.join(", ") + ".";
      if (c("Distress") > 0) {
        const m = new Map();
        rows.filter((r) => r.Zone === "Distress").forEach((r) => m.set(r.Sector, (m.get(r.Sector) || 0) + 1));
        const worst = [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 2).map((e) => e[0]);
        if (worst.length) s += ` Distress is concentrated in ${worst.join(", ")}.`;
      }
      return s;
    }

    /* ---------------- strategic_soe.py (GRE uplift) ---------------- */
    function gre(rows, entity, role, link, sovereign, outlook) {
      const d = byYear(rows.filter((r) => r.Entity === entity));
      const sacp = d[d.length - 1].Rating, sIdx = ratingIndex(sacp), vIdx = ratingIndex(sovereign);
      const tier = CFG.ROLE_LINK_TO_TIER[String((CFG.ROLE_SCORE[role] || 1) + (CFG.LINK_SCORE[link] || 1))] || "Low";
      const [fr, lr, nc] = notchChange(rows, entity);
      const triggers = [];
      if (nc !== null && nc <= -CFG.DYNAMIC_CAP_TRIGGER_NOTCHES) triggers.push(`rating fell ${Math.abs(nc)} notches (${fr} → ${lr})`);
      if (outlook === "Negative") triggers.push("sovereign outlook is Negative");
      const order = CFG.LIKELIHOOD_TIERS_ASC;
      const capped = triggers.length && order.indexOf(tier) > order.indexOf(CFG.DYNAMIC_CAP_TIER) ? CFG.DYNAMIC_CAP_TIER : tier;
      const spec = CFG.LIKELIHOOD_UPLIFT[capped], m = spec.max_notches, g = spec.min_gap_to_sovereign;
      let uIdx, ceiling = null;
      if (sIdx === null || vIdx === null || m === 0) uIdx = sIdx;
      else { ceiling = vIdx - (g || 0); const target = m !== null ? sIdx + m : ceiling; uIdx = Math.max(sIdx, Math.min(target, ceiling)); }
      const uplifted = uIdx !== null ? CFG.RATING_SCALE_ASC[uIdx] : sacp;
      return {
        entity, sacp, role, link, tier, capped, capApplied: triggers.length > 0, triggers, uplifted,
        notches: sIdx !== null && uIdx !== null ? uIdx - sIdx : 0,
        gap: vIdx !== null && uIdx !== null ? vIdx - uIdx : null, ceilingIdx: ceiling, sIdx, uIdx, vIdx,
      };
    }

    /* ---------------- schema.py (column matching) ---------------- */
    const SCH = CFG.SCHEMA || { variables: [], fuzzy_cutoff: 0.88 };
    const BY_COLUMN = Object.fromEntries(SCH.variables.map((v) => [v.column, v]));
    function normalizeLabel(label) {
      let s = String(label).trim().toLowerCase().replace(/&/g, " and ");
      s = s.replace(/[^a-z0-9]+/g, " ");
      return s.replace(/\s+/g, " ").trim();
    }
    const LOOKUP = new Map();
    for (const v of SCH.variables) {
      for (const [name, how] of [[v.key, "exact"], [v.column, "exact"], ...v.synonyms.map((x) => [x, "synonym"])]) {
        const n = normalizeLabel(name);
        if (n && !LOOKUP.has(n)) LOOKUP.set(n, [v.column, how]);
      }
    }
    /** difflib.SequenceMatcher(None, a, b).ratio() (no junk; labels are far below the 200-character autojunk size) */
    function seqRatio(a, b) {
      const la = a.length, lb = b.length;
      if (!la && !lb) return 1;
      const b2j = new Map();
      for (let j = 0; j < lb; j++) { if (!b2j.has(b[j])) b2j.set(b[j], []); b2j.get(b[j]).push(j); }
      const longest = (alo, ahi, blo, bhi) => {
        let bi = alo, bj = blo, bs = 0, j2len = new Map();
        for (let i = alo; i < ahi; i++) {
          const nj = new Map();
          for (const j of b2j.get(a[i]) || []) {
            if (j < blo) continue;
            if (j >= bhi) break;
            const k = (j2len.get(j - 1) || 0) + 1;
            nj.set(j, k);
            if (k > bs) { bi = i - k + 1; bj = j - k + 1; bs = k; }
          }
          j2len = nj;
        }
        while (bi > alo && bj > blo && a[bi - 1] === b[bj - 1]) { bi--; bj--; bs++; }
        while (bi + bs < ahi && bj + bs < bhi && a[bi + bs] === b[bj + bs]) bs++;
        return [bi, bj, bs];
      };
      let m = 0;
      const q = [[0, la, 0, lb]];
      while (q.length) {
        const [alo, ahi, blo, bhi] = q.pop(), [i, j, k] = longest(alo, ahi, blo, bhi);
        if (k) { m += k; if (alo < i && blo < j) q.push([alo, i, blo, j]); if (i + k < ahi && j + k < bhi) q.push([i + k, ahi, j + k, bhi]); }
      }
      return (2 * m) / (la + lb);
    }
    /** match_column → [column, "exact"|"synonym"|"spelling"|"unmatched", score] */
    function matchColumn(label) {
      const n = normalizeLabel(label);
      if (LOOKUP.has(n)) { const [col, how] = LOOKUP.get(n); return [col, how, 1]; }
      let best = null, bestScore = -1;
      for (const cand of LOOKUP.keys()) {
        const r = seqRatio(cand, n); // get_close_matches: seq1 = candidate, seq2 = word
        if (r >= SCH.fuzzy_cutoff && (r > bestScore || (r === bestScore && cand > best))) { best = cand; bestScore = r; }
      }
      if (best !== null) return [LOOKUP.get(best)[0], "spelling", Math.round(seqRatio(n, best) * 1000) / 1000];
      return [null, "unmatched", 0];
    }
    const CONFIDENCE = { exact: "HIGH", synonym: "MEDIUM", spelling: "LOW", unmatched: "—", duplicate: "—" };
    /** standardize_columns on a list of headers → {rename: {uploaded: internal}, report: [...]}.
     *  Exact matches claim their target first, then synonyms, then spelling matches; a header whose target
     *  is already taken keeps its name and is reported as a duplicate. */
    function standardizeColumns(headers) {
      const m = Object.fromEntries(headers.map((h) => [h, matchColumn(h)]));
      const pri = { exact: 0, synonym: 1, spelling: 2, unmatched: 3 };
      const taken = new Set(), fin = {};
      headers.slice().sort((a, b) => pri[m[a][1]] - pri[m[b][1]]).forEach((h) => {
        const [t, how, sc] = m[h];
        if (t === null) fin[h] = [null, "unmatched", 0];
        else if (taken.has(t)) fin[h] = [null, "duplicate", 0];
        else { taken.add(t); fin[h] = [t, how, sc]; }
      });
      const rename = {}, report = [];
      headers.forEach((h) => {
        const [t, how, sc] = fin[h];
        if (t && t !== h) rename[h] = t;
        report.push({ "Uploaded column": h, "Mapped to": t || "", "Schema key": t ? BY_COLUMN[t].key : "", Method: how === "spelling" ? `spelling (${sc.toFixed(2)})` : how, Confidence: CONFIDENCE[how] });
      });
      return { rename, report };
    }

    return {
      isNum, div, classifyZone, zRating, enrich, enrichRow, availableKpis, classify, pdByRating, worstPdInZone, efcRow,
      recoveryScenarios, revenueVolatility, ratingIndex, notchChange, latestPerEntity, runScenario, costPath, kpiImpact,
      gdpPath, describeShocks, monteCarlo, quantile, percentilePath, singleNarrative, crossNarrative, zTrendSummary,
      zoneSummary, gre, ZCOMP, K, soeExposures, symEig, mcFactor, MC_VARIABLES, normalizeLabel, seqRatio, matchColumn,
      standardizeColumns, BY_COLUMN,
    };
  }

  const api = { create };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SOEEngine = api;
})(typeof window !== "undefined" ? window : this);
