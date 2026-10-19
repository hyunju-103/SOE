  /*
   * Optional fiscal-support panels (always visible; data-dependent content).
   * Existing demo data, nine tabs, GRE rating methodology, stress calculations,
   * thresholds and original charts are not changed. The HTML is self-contained.
   */
  const SUPPORT_FLOWS = [
    ["tariff_pso_compensation", "Tariff / PSO compensation", "#0071bc"],
    ["operating_subsidy", "Operating subsidy", "#0a9e91"],
    ["investment_grant", "Investment grant received", "#8568af"],
    ["equity_injection", "Equity injection", "#d99a3c"]
  ];
  // All uploaded headers are standardized to schema COLUMN names, not the
  // snake_case schema keys. Keep one explicit lookup for both main-sheet
  // values and Grants_detail codes to avoid displaying empty charts.
  const SUPPORT_COLS = Object.freeze({
    tariff_pso_compensation: "Tariff / PSO Compensation",
    operating_subsidy: "Operating Subsidy (Flow)",
    investment_grant: "Investment Grant (Flow)",
    equity_injection: "Equity Injection (Flow)"
  });
  const flowValue = (row, code) => row[SUPPORT_COLS[code]];
  const SUPPORT_STOCKS = new Set(["concessional_loan", "guarantee", "tax_support"]);
  const numOrNull = (v) => {
    const n = E.parseNumber(v);
    return Number.isFinite(n) ? n : null;
  };

  // Reads extra worksheets from the user's selected file ONLY (nothing is bundled).
  function extractSupportSheets(wb) {
    const sheetNames = ["Grants_detail", "Source_lines", "Validation", "Checks", "Definitions"];
    const result = { sheets: [], grants: [], sourceLines: [], validation: [], checks: [], definitions: [] };
    const dest = { Grants_detail: "grants", Source_lines: "sourceLines", Validation: "validation", Checks: "checks", Definitions: "definitions" };
    sheetNames.forEach((name) => {
      const sh = wb.SheetNames.find((s) => s.toLowerCase() === name.toLowerCase());
      if (!sh) return;
      result.sheets.push(sh);
      result[dest[name]] = window.XLSX.utils.sheet_to_json(wb.Sheets[sh], { defval: null, raw: true }).slice(0, 25000);
    });
    return result;
  }

  // Existing primary-sheet values take precedence. The grants sheet can have
  // no Entity column ONLY for single-SOE workbooks. Units are respected:
  // Grants_detail "Value (FCFA, Ones)" is an absolute XOF amount, whereas
  // the primary statement may declare Millions / Thousands / Billions.
  function mergeSupportUpload(rows, extra) {
    const meta = Object.assign({ sheets: [], grants: [], sourceLines: [], validation: [], checks: [], definitions: [] }, extra || {});
    meta.conflicts = []; meta.warnings = []; meta.merged = 0;
    const entities = uniq(rows.map((r) => String(r.Entity || "").trim()).filter(Boolean));
    const flowFields = new Set(SUPPORT_FLOWS.map((x) => x[0]));
    const byKey = new Map(rows.map((r) => [`${String(r.Entity || "").trim()}|${E.parseYear(r.Year)}`, r]));
    const present = (v) => v !== null && v !== undefined && String(v).trim() !== "";
    const grants = meta.grants || [];
    for (const item of grants) {
      const code = String(item.Code || "").trim().toLowerCase();
      const year = E.parseYear(item.Year);
      const basis = String(item.Basis || "").toLowerCase();
      if (!Number.isFinite(year) || !flowFields.has(code)) continue;
      if (!basis.startsWith("flow")) {
        meta.warnings.push(`${code} ${year}: not joined (basis is not an annual flow).`); continue;
      }
      const itemEntity = String(item.Entity || item.SOE || "").trim();
      if (!itemEntity && entities.length !== 1) {
        meta.warnings.push(`${code} ${year}: multi-SOE file needs an Entity in Grants_detail; skipped.`); continue;
      }
      const row = byKey.get(`${itemEntity || entities[0]}|${year}`);
      if (!row) continue;
      const unit = unitScale(row.Units);
      const currency = String(row.Currency || "").toUpperCase();
      const valueCol = Object.keys(item).find((k) => /^value\b/i.test(k));
      const val = numOrNull(valueCol ? item[valueCol] : null);
      if (val === null) continue;
      // The field name is an explicit unit and currency declaration, not a universal convention.
      const isFcfaOnes = valueCol && /fcfa|xof/i.test(valueCol) && /ones/i.test(valueCol);
      if (isFcfaOnes && !["XOF", "FCFA"].includes(currency)) {
        meta.warnings.push(`${code} ${year}: FCFA grant unit does not match primary currency ${currency}; skipped.`);
        continue;
      }
      const adjusted = isFcfaOnes ? val / unit : val;
      if (present(row[SUPPORT_COLS[code]])) {
        const reported = numOrNull(row[SUPPORT_COLS[code]]);
        if (reported !== null && Math.abs(reported - adjusted) > Math.max(1, Math.abs(reported), Math.abs(adjusted)) * 1e-6) {
          meta.conflicts.push(`${code} ${year}: primary ${reported}, Grants_detail ${adjusted}. Primary retained.`);
        }
      } else {
        row[SUPPORT_COLS[code]] = adjusted;
        meta.merged++;
      }
    }
    return { rows, meta };
  }

  function supportRows(entity) {
    return S.rows.filter((r) => r.Entity === entity).slice().sort((a, b) => a.Year - b.Year);
  }
  function hasSupportFlows() {
    return S.rows.some((r) => SUPPORT_FLOWS.some(([key]) => ok(flowValue(r, key))));
  }
  const supportMoney = (v) => (ok(v) ? money(v, true) : "not reported");
  function supportCard(title, sub) {
    const c = card(title, sub, null, "top");
    c.root.classList.add("upload-support-card");
    c.root.style.marginTop = "16px";
    return c;
  }
  function showSupportHome() {
    const m = S.uploadExtras;
    if (!hasSupportFlows() && !(m && m.sheets.length)) return;
    const c = supportCard("Uploaded government-support data", "Government-support disclosures from the uploaded workbook.");
    const n = S.rows.filter((r) => ok(flowValue(r, "tariff_pso_compensation"))).length;
    const check = m && m.validation.length ? `${m.validation.length} source-file validation rows` : "No Validation sheet";
    c.body.append(el("p", { class: "note", style: "margin-top:0" },
      `${n} SOE-year record(s) have tariff / PSO compensation. ${check}. See the supplemental charts in KPI Dashboard and Government Support, plus the audit details in Assumptions.`));
    if (m && m.conflicts.length) c.body.append(el("p", { class: "alert-box warn", style: "margin-top:10px" }, `${m.conflicts.length} primary/detail amount mismatch(es) need review; primary values were kept.`));
    document.getElementById("home").append(c.root);
  }
  function showSupportKPI() {
    if (S.kpi.view !== "trend") return;
    const entity = S.kpi.soe;
    const years = supportRows(entity).filter((r) => r.Year >= S.kpi.from && r.Year <= S.kpi.to);
    const eligible = years.filter((r) => ok(r.Revenues) && r.Revenues > 0 && ok(r["Operating Profits (EBIT)"]) && ok(flowValue(r, "tariff_pso_compensation")));
    const c = supportCard("Reported vs tariff-compensation-adjusted EBIT margin", "Selected SOE · the effect of removing tariff/PSO compensation already included in reported revenue.");
    if (!eligible.length) {
      c.body.append(el("p", { class: "kpi-desc" }, "Data unavailable — requires reported revenue, EBIT and separately disclosed tariff / PSO compensation. No adjusted values are inferred from other grants."));
      document.getElementById("kpi").append(c.root);
      return;
    }
    const chart = el("div", { class: "chart" });
    const reported = years.map((r) => ok(r["Operating Profits (EBIT)"]) && r.Revenues > 0 ? r["Operating Profits (EBIT)"] / r.Revenues : NaN);
    const adjusted = years.map((r) => {
      const rev = r.Revenues - flowValue(r, "tariff_pso_compensation");
      return ok(flowValue(r, "tariff_pso_compensation")) && rev > 0 && ok(r["Operating Profits (EBIT)"]) ? (r["Operating Profits (EBIT)"] - flowValue(r, "tariff_pso_compensation")) / rev : NaN;
    });
    c.body.append(chart,
      el("div", { class: "legend-row" }, el("span", {}, "● Reported EBIT margin"), el("span", {}, "◆ Mechanical ex-tariff-compensation margin")),
      el("p", { class: "note" }, "Sensitivity only: subtract the same tariff/PSO compensation from EBIT and reported revenue, assuming the amount was booked within revenue and holding costs fixed. Not an audited restatement, not a policy counterfactual. Compensation is not added to revenue again."),
      dataButtons(() => toCSV(["SOE", "Year", "Reported EBIT margin", "Mechanical ex-compensation EBIT margin", "Compensation amount"], years.map((r, i) => [entity, r.Year, ok(reported[i]) ? reported[i] : "", ok(adjusted[i]) ? adjusted[i] : "", ok(flowValue(r, "tariff_pso_compensation")) ? flowValue(r, "tariff_pso_compensation") : ""])), "reported_vs_compensation_adjusted_margin.csv"));
    document.getElementById("kpi").append(c.root);
    lines(chart, years.map((r) => r.Year), [
      { vals: reported, cls: "ln-base", dot: "prev", label: "Reported EBIT margin" },
      { vals: adjusted, cls: "ln-str", dot: "now", label: "Mechanical ex-compensation margin" }
    ], { h: 235, zeroFloor: true, L: 65, R: 60,
      yFmt: (v) => pct(v, 0), tip: (i) => [[pct(reported[i], 2), "Reported EBIT margin"], [pct(adjusted[i], 2), "Mechanical ex-compensation"], [supportMoney(flowValue(years[i], "tariff_pso_compensation")), "Compensation already in revenue"]] });
  }
  function drawSupportFlows(box, years) {
    const W = Math.max(620, Math.round(widthOf(box))), H = 285, L = 74, R = 22, T = 17, B = 39;
    const max = Math.max(1, ...years.flatMap((r) => SUPPORT_FLOWS.map(([key]) => ok(flowValue(r, key)) ? Math.max(0, flowValue(r, key)) : 0)));
    const scale = Math.pow(10, Math.floor(Math.log10(max)));
    const top = Math.ceil(max / scale * 1.15 * 2) / 2 * scale;
    const sy = (v) => H - B - v / top * (H - B - T);
    const g = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Annual fiscal-support flows by category and year" });
    for (let i = 0; i <= 4; i++) {
      const v = top * i / 4, y = sy(v);
      svgEl("line", { x1: L, x2: W - R, y1: y, y2: y, class: "grid-l" }, g);
      txt(g, L - 8, y, money(v), "t-muted num", "end", 11);
    }
    const spacing = (W - L - R) / Math.max(1, years.length);
    const bw = Math.min(27, spacing / 6);
    years.forEach((r, i) => {
      const center = L + spacing * (i + 0.5);
      txt(g, center, H - 16, String(r.Year), "t-muted num", "middle", 11);
      SUPPORT_FLOWS.forEach(([key, label, color], j) => {
        if (!ok(flowValue(r, key))) return;
        const v = Math.max(0, flowValue(r, key));
        const x = center + (j - 1.5) * (bw + 3) - bw / 2;
        const rect = svgEl("rect", { x, y: sy(v), width: bw, height: Math.max(1.5, sy(0) - sy(v)), fill: color, rx: 2 }, g);
        const title = svgEl("title", {}, rect); title.textContent = `${r.Year} ${label}: ${supportMoney(flowValue(r, key))}`;
      });
    });
    box.replaceChildren(g);
  }
  function showSupportGRE() {
    const entity = S.gre.sel && S.names.includes(S.gre.sel) ? S.gre.sel : S.names[0];
    const rows = supportRows(entity);
    const c = supportCard("Historical fiscal-support flows", `${entity} · Annual flow amounts by type; the rating-uplift assessment is unchanged.`);
    if (!rows.some((r) => SUPPORT_FLOWS.some(([key]) => ok(flowValue(r, key))))) {
      c.body.append(el("p", { class: "kpi-desc" }, "Data unavailable — no separately disclosed tariff / PSO compensation, operating subsidy, investment grant or equity injection for this SOE. Missing categories are not assumed to be zero."));
      document.getElementById("gre").append(c.root);
      return;
    }
    const chart = el("div", { class: "chart" });
    const legend = el("div", { class: "legend-row" }, SUPPORT_FLOWS.map(([, lab, color]) => el("span", {}, el("i", { style: `display:inline-block;width:11px;height:11px;background:${color};margin-right:5px;border-radius:2px` }), lab)));
    const detail = rows.map((r) => [r.Year, ...SUPPORT_FLOWS.map(([key]) => supportMoney(flowValue(r, key))), ok(flowValue(r, "tariff_pso_compensation")) && ok(r.Revenues) && r.Revenues > 0 ? pct(flowValue(r, "tariff_pso_compensation") / r.Revenues, 1) : "—"]);
    c.body.append(legend, chart, simpleTable(["Year", "Tariff/PSO in revenue", "Operating subsidy", "Investment grant", "Equity injection", "Tariff/PSO / revenue"], detail, { right: (i) => i > 0 }),
      el("p", { class: "note" }, "Categories are displayed separately, not automatically summed: Government Grants may already represent tariff compensation, operating subsidies may overlap with other reported grants, and investment grants/equity injections are different accounting channels. Missing values are not zero. Grants_detail entries with stock or contingent basis are excluded from this annual-flow chart."),
      dataButtons(() => toCSV(["SOE", "Year", ...SUPPORT_FLOWS.map((x) => x[0])], rows.map((r) => [entity, r.Year, ...SUPPORT_FLOWS.map(([key]) => ok(flowValue(r, key)) ? flowValue(r, key) : "")])), "government_support_flows.csv"));
    document.getElementById("gre").append(c.root);
    drawSupportFlows(chart, rows);
  }
  function showSupportAssumptions() {
    const m = S.uploadExtras;
    const c = supportCard("Workbook evidence and validation", "Source references and consistency checks, when supplied with the workbook.");
    if (!m || !m.sheets.length) {
      c.body.append(el("p", { class: "kpi-desc" }, "Data unavailable — no supplemental workbook evidence has been loaded. Upload a workbook with Grants_detail, Source_lines or Validation sheets to populate this panel."));
      document.getElementById("assumptions").append(c.root);
      return;
    }
    const stats = new Map();
    m.validation.forEach((r) => { const k = String(r.Status || "(blank)"); stats.set(k, (stats.get(k) || 0) + 1); });
    const nerr = [...stats.entries()].filter(([k]) => !/^ok$/i.test(k)).reduce((s, [, v]) => s + v, 0);
    c.body.append(el("div", { class: "grid4 sm" },
        tile("Sheets linked", "ok", "Workbook", String(m.sheets.length), "", m.sheets.join(", ")),
        tile("Grant-detail records", null, null, String(m.grants.length), "", "Flows & stocks kept distinct"),
        tile("Validation rows", nerr ? "watch" : "ok", nerr ? "Review" : "Workbook OK", String(m.validation.length), "", [...stats].map(([k, v]) => `${k}: ${v}`).join(" · ") || "No validation rows"),
        tile("Matching discrepancies", m.conflicts.length ? "watch" : "ok", m.conflicts.length ? "Review" : "No conflicts", String(m.conflicts.length), "", `${m.merged} additional flow cells joined`)));
    if (m.conflicts.length || m.warnings.length) {
      c.body.append(el("details", { class: "plain" }, el("summary", {}, `${m.conflicts.length} conflicts · ${m.warnings.length} join warnings`),
        el("ul", { class: "caveats" }, [...m.conflicts, ...m.warnings].slice(0, 80).map((msg) => el("li", {}, msg)))));
    }
    if (m.grants.length) {
      const stock = m.grants.filter((r) => SUPPORT_STOCKS.has(String(r.Code || "").toLowerCase()) && numOrNull(Object.values(r)[2]) !== null);
      c.body.append(el("p", { class: "note" }, `Grants_detail: ${m.grants.length} records; ${stock.length} observations under loan/guarantee/tax-support codes with a recorded value. These are NOT treated as additional annual cash flows.`));
      c.body.append(simpleTable(["Code", "Year", "Value / disclosure", "Basis", "Source"], m.grants.slice(0, 60).map((r) => [r.Code || "", r.Year || "", Object.entries(r).find(([k]) => /^Value\b/i.test(k))?.[1] ?? "not reported", r.Basis || "", r.Source || ""]), { tall: true }));
    }
    if (m.validation.length) {
      c.body.append(el("details", { class: "plain" }, el("summary", {}, `Validation checks (${m.validation.length} rows, supplied in uploaded workbook)`),
        simpleTable(["Check", "Year", "Item", "Difference", "Status"], m.validation.slice(0, 300).map((r) => [r.Check || "", r.Year || "", r.Item || "", r.Difference ?? "", r.Status || ""]), { tall: true })));
    }
    if (m.sourceLines.length) {
      c.body.append(el("details", { class: "plain" }, el("summary", {}, `Source-line evidence (${m.sourceLines.length} records)`),
        simpleTable(["Code", "Statement label", ...S.years.map(String)], m.sourceLines.slice(0, 130).map((r) => [r.Code ?? "", r["SYSCOHADA line"] ?? "", ...S.years.map((y) => r[String(y)] ?? "")]), { tall: true })));
    }
    c.body.append(el("p", { class: "note" }, "This audit-trail panel does not establish that the uploaded financial reports were audited; review source and scope of the original Validation sheet. The model's assumed fuel / FX / floating-rate exposures are distinct from observed statement lines."));
    document.getElementById("assumptions").append(c.root);
  }
  function showSupportShock() {
    const latest = latestOf(S.rows), absent = latest.filter((r) => !["Fuel Cost Share", "FX Debt Share", "Floating Rate Debt Share"].some((k) => ok(r[k])));
    const c = supportCard("Exposure-data availability", "Observed input coverage for the existing shock scenarios.");
    c.body.append(el("p", { class: "note", style: "margin-top:0" },
      `${absent.length} of ${latest.length} SOE(s) have no observed fuel, FX-debt or floating-rate exposure-share columns. When a relevant exposure is unavailable, the existing shock engine uses its documented sector/generic defaults. Historical tariff compensation should not be equated mechanically with incremental fuel subsidies under the stress scenario.`));
    document.getElementById("shock").append(c.root);
  }
  // Wrap original render methods rather than replacing the existing dashboards.
  // A change in SOE/period or the GRE selection updates only the add-on card.
  [ ["home", showSupportHome], ["kpi", showSupportKPI], ["gre", showSupportGRE],
    ["assumptions", showSupportAssumptions], ["shock", showSupportShock] ].forEach(([tab, extra]) => {
    const original = pages[tab].render;
    pages[tab].render = function (...args) {
      const result = original.apply(this, args);
      const root = document.getElementById(tab);
      root.querySelectorAll(":scope > .upload-support-card").forEach((e) => e.remove());
      extra();
      return result;
    };
  });
