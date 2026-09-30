(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  let CFG = null, DATA = null;
  try { CFG = JSON.parse($("#app-config").textContent); DATA = JSON.parse($("#app-data").textContent); } catch (e) { /* handled below */ }
  if (!CFG || !CFG.ZEM_COEFFICIENTS || !DATA || !DATA.meta || typeof SOEEngine === "undefined") {
    const p = document.createElement("p"); p.className = "load-error";
    p.textContent = "No tool data found. Generate this page with report.py or the Report page of the SOE Fiscal Risk Tool.";
    $("#wrap").prepend(p); return;
  }
  const E = SOEEngine.create(CFG);
  const M = DATA.meta;
  const NUMCOLS = new Set(CFG.ALL_NUMERIC_COLUMNS || CFG.NUMERIC_COLUMNS);
  let framed = true;
  try { framed = window.self !== window.top; } catch (e) { framed = true; }
  const canDownload = !framed || !!M.allow_download;

  /* =====================================================================
     helpers
     ===================================================================== */
  function el(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    if (attrs) for (const k in attrs) {
      const v = attrs[k];
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? "" : v);
    }
    for (const c of kids.flat(3)) if (c !== null && c !== undefined && c !== false) e.appendChild(typeof c === "object" ? c : document.createTextNode(String(c)));
    return e;
  }
  /** replaceChildren without empty slots (the DOM would turn null into the text "null") */
  const put = (node, ...kids) => node.replaceChildren(...kids.flat().filter((k) => k !== null && k !== undefined && k !== false));
  const NS = "http://www.w3.org/2000/svg";
  const svgEl = (tag, attrs = {}, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };
  const txt = (parent, x, y, s, cls, anchor = "start", size = 12, weight) => {
    const t = svgEl("text", { x, y, class: cls, "text-anchor": anchor, "font-size": size, "dominant-baseline": "middle" }, parent);
    if (weight) t.setAttribute("font-weight", weight);
    t.textContent = s; return t;
  };
  const ok = E.isNum;
  const fmt = (v, d = 1) => (!ok(v) ? "—" : (Math.round(v * 10 ** d) / 10 ** d).toFixed(d).replace("-", "−"));
  const sgn = (v, d = 2) => (!ok(v) ? "—" : (v > 0 ? "+" : "") + fmt(v, d));
  const pct = (v, d = 1) => (!ok(v) ? "—" : fmt(v * 100, d) + "%");
  const pctAuto = (v) => (!ok(v) ? "—" : pct(v, Math.abs(v) >= 1 ? 0 : Math.abs(v) >= 0.1 ? 1 : 2));
  const pctS = (v) => (!ok(v) ? "—" : v !== 0 && Math.abs(v) < 0.00005 ? (v < 0 ? "> −0.01%" : "< 0.01%") : pct(v, 2));
  const pl = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  const clip = (s, n) => (String(s).length > n ? String(s).slice(0, n - 1) + "…" : String(s));
  const slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-");
  const uniq = (a) => [...new Set(a)];
  const sum = (a) => a.reduce((s, v) => s + (ok(v) ? v : 0), 0);
  const mean = (a) => { const v = a.filter(ok); return v.length ? v.reduce((s, x) => s + x, 0) / v.length : NaN; };
  const last = (a) => a[a.length - 1];
  let SC = 1, CUR = "";
  function money(v, withCur = false) {
    if (!ok(v)) return "—";
    const x = v * SC, a = Math.abs(x);
    let s;
    if (a >= 1e12) s = fmt(x / 1e12, 2) + " tn"; else if (a >= 1e9) s = fmt(x / 1e9, 1) + " bn"; else if (a >= 1e6) s = fmt(x / 1e6, 1) + " m";
    else s = Math.round(x).toLocaleString("en-US").replace("-", "−");
    return withCur && CUR ? s + " " + CUR : s;
  }
  function moneyTick(t, step) {
    const a = Math.abs(step * SC), x = t * SC;
    const u = a >= 1e12 ? [1e12, " tn"] : a >= 1e9 ? [1e9, " bn"] : a >= 1e6 ? [1e6, " m"] : [1, ""];
    const d = Number.isInteger(+((step * SC) / u[0]).toFixed(6)) ? 0 : 1;
    return t === 0 ? "0" : fmt(x / u[0], d) + u[1];
  }
  const GLYPH = { ok: "●", watch: "▲", alert: "■" };
  const STLABEL = { ok: "Good", watch: "Watch", alert: "Alert" };
  const ZLABEL = { ok: "Safe", watch: "Grey zone", alert: "Distress" };
  const ZK = { Distress: "alert", Grey: "watch", Safe: "ok" };
  const RAG = { Red: "alert", Amber: "watch", Green: "ok" };
  const zk = (zone) => ZK[zone] || "none";
  const ZORDER = ["Distress", "Grey", "Safe"];
  function stChip(k, label) {
    return el("span", { class: "st " + k }, GLYPH[k] ? el("i", { "aria-hidden": "true" }, GLYPH[k]) : null, label || STLABEL[k] || "—");
  }
  const zoneChip = (zone) => stChip(zk(zone), ZLABEL[zk(zone)] || zone);
  const lin = (d0, d1, r0, r1) => (v) => r0 + ((v - d0) / (d1 - d0 || 1)) * (r1 - r0);
  function nice(lo, hi, n = 5) {
    if (!ok(lo) || !ok(hi)) { lo = 0; hi = 1; }
    if (hi - lo < 1e-12) { hi = lo + (Math.abs(lo) || 1) * 0.5; lo = lo - (Math.abs(lo) || 1) * 0.5; }
    n = Math.max(2, n);
    const raw = (hi - lo) / n, mag = 10 ** Math.floor(Math.log10(raw));
    let step = mag * 10;
    for (const m of [1, 2, 2.5, 5, 10, 20]) { const s0 = m * mag; if (Math.ceil(hi / s0 - 1e-9) - Math.floor(lo / s0 + 1e-9) <= n + 1) { step = s0; break; } }
    const a = Math.floor(lo / step + 1e-9) * step, b = Math.ceil(hi / step - 1e-9) * step;
    const ticks = [];
    for (let t = a; t <= b + step / 2; t += step) ticks.push(Math.abs(t) < step / 1e6 ? 0 : +t.toFixed(10));
    return { lo: a, hi: b, ticks, step };
  }
  const tickLab = (t, step) => (step >= 1 ? fmt(t, 0) : fmt(t, step >= 0.1 ? 1 : 2));
  function barPath(x0, x1, y, h, r = 3) {
    const w = Math.abs(x1 - x0); r = Math.min(r, w, h / 2);
    if (x1 >= x0) return `M${x0},${y}H${x1 - r}Q${x1},${y} ${x1},${y + r}V${y + h - r}Q${x1},${y + h} ${x1 - r},${y + h}H${x0}Z`;
    return `M${x0},${y}H${x1 + r}Q${x1},${y} ${x1},${y + r}V${y + h - r}Q${x1},${y + h} ${x1 + r},${y + h}H${x0}Z`;
  }
  function vbar(x, y0, y1, w, r = 3) {
    const h = Math.abs(y0 - y1); r = Math.min(r, h, w / 2);
    if (y1 <= y0) return `M${x},${y0}V${y1 + r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 + r}V${y0}Z`;
    return `M${x},${y0}V${y1 - r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 - r}V${y0}Z`;
  }
  function boldText(parent, text) {
    String(text).split("**").forEach((part, i) => { if (part) parent.appendChild(i % 2 ? el("b", {}, part) : document.createTextNode(part)); });
    return parent;
  }
  function toCSV(head, rows) {
    const q = (v) => { const s = v === null || v === undefined || (typeof v === "number" && !Number.isFinite(v)) ? "" : String(v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
    return [head.map(q).join(","), ...rows.map((r) => r.map(q).join(","))].join("\n") + "\n";
  }
  function download(name, text, type = "text/csv") {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const a = el("a", { href: url, download: name }); document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }
  /** "Copy data" (+ "Download CSV" when the page runs on its own, outside a viewer frame) */
  function dataButtons(getCSV, name, what = "data") {
    const box = el("div", { class: "btn-row" });
    const cl = what === "data" ? "Copy data" : "Copy " + what;
    const copy = el("button", { class: "btn-ghost", type: "button" }, cl);
    copy.addEventListener("click", async () => {
      const text = getCSV();
      try { await navigator.clipboard.writeText(text); copy.textContent = "Copied"; setTimeout(() => (copy.textContent = cl), 1500); }
      catch (e) {
        const ta = el("textarea", { rows: "6", style: "width:100%;font:12px monospace", "aria-label": "Data as CSV" }); ta.value = text;
        box.appendChild(ta); ta.focus(); ta.select(); copy.textContent = "Select and copy";
      }
    });
    box.appendChild(copy);
    if (canDownload) box.appendChild(el("button", { class: "btn-ghost", type: "button", onclick: () => download(name, getCSV()) }, what === "data" ? "⬇ Download CSV" : `⬇ ${what[0].toUpperCase() + what.slice(1)} (CSV)`));
    return box;
  }

  /* ---------- tooltip ---------- */
  const tip = $("#tip");
  function showTip(evt, title, rows) {
    tip.replaceChildren(el("div", { class: "tip-title" }, title));
    for (const [val, lab] of rows || []) tip.appendChild(el("div", { class: "tip-row" }, val ? el("strong", {}, val) : null, lab ? el("span", {}, lab) : null));
    tip.hidden = false;
    let x, y;
    if (evt && evt.clientX != null && evt.type !== "focus") { x = evt.clientX; y = evt.clientY; } else { const b = evt.target.getBoundingClientRect(); x = b.left + b.width / 2; y = b.top; }
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let left = x + 14, top = y - th - 10;
    if (left + tw > window.innerWidth - 8) left = x - tw - 14;
    if (left < 8) left = 8;
    if (top < 8) top = y + 16;
    tip.style.left = left + "px"; tip.style.top = top + "px";
  }
  const hideTip = () => { tip.hidden = true; };
  function bindTip(node, title, rows) {
    const r = () => (typeof rows === "function" ? rows() : rows);
    node.addEventListener("pointermove", (e) => showTip(e, title, r()));
    node.addEventListener("pointerleave", hideTip);
    node.addEventListener("focus", (e) => showTip(e, title, r()));
    node.addEventListener("blur", hideTip);
  }
  function info(text) { const i = el("i", { class: "info", tabindex: "0", role: "img", "aria-label": text }, "i"); bindTip(i, text, []); return i; }

  /* ---------- controls ---------- */
  let uid = 0;
  const nid = (p) => `${p}-${++uid}`;
  function fSelect(label, options, value, onChange, opt = {}) {
    const id = opt.id || nid("sel");
    const s = el("select", { id });
    options.forEach((o) => { const [v, l] = Array.isArray(o) ? o : [o, o]; const op = el("option", { value: String(v) }, l); if (String(v) === String(value)) op.selected = true; s.appendChild(op); });
    s.addEventListener("change", () => onChange(opt.num ? Number(s.value) : s.value));
    return el("div", { class: "fld" }, label ? el("label", { for: id }, el("span", {}, label, opt.info ? info(opt.info) : null)) : null, s);
  }
  function fSlider(label, o, onInput) {
    const id = o.id || nid("rng");
    const out = el("output", { for: id }, o.fmt(o.value));
    const r = el("input", { type: "range", id, min: o.min, max: o.max, step: o.step, value: o.value });
    r.addEventListener("input", () => { const v = Number(r.value); out.textContent = o.fmt(v); onInput(v); });
    return el("div", { class: "fld" }, el("label", { for: id }, el("span", {}, label, o.info ? info(o.info) : null), out), r, o.help ? el("small", {}, o.help) : null);
  }
  function seg(options, value, onChange, label) {
    const box = el("div", { class: "seg", role: "group", "aria-label": label || "View" });
    options.forEach(([v, l]) => {
      const b = el("button", { type: "button", "aria-pressed": String(v === value) }, l);
      b.addEventListener("click", () => { box.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); onChange(v); });
      box.appendChild(b);
    });
    return box;
  }
  function chipsMulti(options, set, onChange, label) {
    const box = el("div", { class: "chips", role: "group", "aria-label": label || "" });
    if (label) box.appendChild(el("span", { class: "chips-label" }, label));
    options.forEach(([v, l]) => {
      const b = el("button", { class: "chip", type: "button", "aria-pressed": String(set.has(v)) }, l);
      b.addEventListener("click", () => {
        if (set.has(v)) { if (set.size > 1) set.delete(v); } else set.add(v);
        box.querySelectorAll(".chip").forEach((x, i) => x.setAttribute("aria-pressed", String(set.has(options[i][0]))));
        onChange();
      });
      box.appendChild(b);
    });
    return box;
  }
  /** From–to year selects (replace the one-chip-per-year control, which does not scale to 20 years) */
  function yearRangeCtl(years, from, to, onChange, label = "Years") {
    const mk = (val, which) => {
      const s = el("select", { "aria-label": `${label}: ${which}` });
      years.forEach((y) => s.appendChild(el("option", { value: String(y), selected: y === val ? true : null }, String(y))));
      return s;
    };
    const a = mk(from, "from"), b = mk(to, "to");
    const fire = (src) => {
      let f = Number(a.value), t = Number(b.value);
      if (f > t) { if (src === a) t = f; else f = t; a.value = String(f); b.value = String(t); }
      onChange(f, t);
    };
    a.addEventListener("change", () => fire(a)); b.addEventListener("change", () => fire(b));
    return el("div", { class: "fld" }, el("span", { class: "lbl" }, label), el("div", { class: "range-sel" }, a, el("span", { class: "muted" }, "to"), b));
  }
  /** long lists show the first LIMIT rows (the weakest or largest) until the reader asks for all */
  const LIMIT = 12;
  const LINE_CHART_MIN_YEARS = 11;
  function moreToggle(n, expanded, onToggle, less = `Show the ${LIMIT} weakest only`, what = "SOEs") {
    if (n <= LIMIT) return null;
    return el("button", { class: "btn-ghost more", type: "button", "aria-expanded": String(expanded), onclick: () => onToggle(!expanded) }, expanded ? less : `Show all ${n} ${what}`);
  }
  const clipRows = (rows, expanded) => (expanded ? rows : rows.slice(0, LIMIT));
  function card(title, sub, tools, cls = "") {
    const body = el("div");
    const head = title ? el("div", { class: "card-head" }, el("div", {}, el("h3", {}, title), sub ? el("p", { class: "sub" }, sub) : null), tools ? el("div", { class: "card-tools" }, tools) : null) : null;
    const root = el("div", { class: "card " + cls }, head, body);
    return { root, body, head };
  }
  function pageHead(eyebrow, title, text, tools) {
    return el("div", { class: "page-head" }, el("div", {}, el("div", { class: "eyebrow" }, eyebrow), el("h2", {}, title), el("p", {}, text)), tools || null);
  }
  function tile(label, status, statusLabel, value, small, sub) {
    return el("div", { class: "card tile" },
      el("div", { class: "tile-top" }, el("span", { class: "tile-label" }, label), status ? stChip(status, statusLabel) : null),
      el("div", { class: "tile-value" }, value, small ? el("small", {}, small) : null),
      el("div", { class: "tile-sub" }, sub || ""));
  }
  function nameCell(name, sector) { return el("td", { class: "name" }, el("span", { class: "nm" }, name), el("span", { class: "sec" }, sector)); }
  function statusCell(k, value, sub, cls = "") {
    return el("td", { class: (k || "na") + " " + cls }, el("span", { class: "cell" }, el("span", { class: "v" }, GLYPH[k] ? el("i", { "aria-hidden": "true" }, GLYPH[k]) : null, value), sub ? el("span", { class: "d" }, sub) : null));
  }
  function simpleTable(head, rows, opt = {}) {
    const t = el("table", { class: opt.cls || "" });
    t.appendChild(el("thead", {}, el("tr", {}, head.map((h, i) => el("th", { class: opt.right && opt.right(i) ? "r" : "" }, h)))));
    t.appendChild(el("tbody", {}, rows.map((r) => el("tr", {}, r.map((c, i) => (c instanceof Node && c.tagName === "TD" ? c : el("td", { class: opt.right && opt.right(i) ? "r" : "" }, c)))))));
    if (opt.foot) t.appendChild(el("tfoot", {}, el("tr", {}, opt.foot.map((c, i) => el("td", { class: opt.right && opt.right(i) ? "r" : "" }, c)))));
    return el("div", { class: "tbl-wrap" + (opt.tall ? " tall" : "") }, t);
  }
  function zoneBar(counts, n) {
    const bar = el("div", { class: "zonebar", role: "img", "aria-label": `Safe ${counts.Safe}, grey zone ${counts.Grey}, distress ${counts.Distress}` });
    [["Safe", "var(--good)"], ["Grey", "var(--warn)"], ["Distress", "var(--crit)"]].forEach(([z, col]) => { if (counts[z]) bar.appendChild(el("div", { style: `width:${(counts[z] / n) * 100}%;background:${col}` })); });
    const lg = el("div", { class: "zonelegend" });
    [["ok", "Safe"], ["watch", "Grey"], ["alert", "Distress"]].forEach(([k, z]) => lg.appendChild(el("span", {}, stChip(k, ZLABEL[k]), el("b", { class: "num" }, String(counts[z])), ` (${n ? Math.round((counts[z] / n) * 100) : 0}%)`)));
    return [bar, lg];
  }
  function zoneCounts(rows) { const c = { Distress: 0, Grey: 0, Safe: 0 }; rows.forEach((r) => { if (r.Zone in c) c[r.Zone]++; }); return c; }
  function tracks(labels, values) {
    const box = el("div", { class: "contrib" });
    const m = Math.max(0.25, ...values.filter(ok).map(Math.abs));
    values.forEach((v, i) => {
      const tr = el("div", { class: "track" });
      if (ok(v)) tr.appendChild(el("span", { class: v >= 0 ? "pos" : "neg", style: `width:${(Math.abs(v) / m) * 50}%` }));
      box.appendChild(el("div", { class: "contrib-row" }, el("span", { class: "lbl" }, labels[i]), tr, el("span", { class: "val" }, sgn(v, 2))));
    });
    return box;
  }
  function summaryBox(text, tag = "Automated summary — generated from the data on screen, not written by a person") {
    return boldText(el("div", { class: "summary" }, el("span", { class: "tag" }, tag)), text);
  }
  function legendItem(svg, label) { const s = el("span"); s.innerHTML = svg; s.appendChild(document.createTextNode(label)); return s; }
  const LG = {
    base: '<svg width="22" height="10" aria-hidden="true"><line x1="1" y1="5" x2="21" y2="5" class="ln-base"/></svg>',
    str: '<svg width="22" height="10" aria-hidden="true"><line x1="1" y1="5" x2="21" y2="5" class="ln-str"/></svg>',
    act: '<svg width="14" height="12" aria-hidden="true"><rect x="0" y="4" width="14" height="5" class="act-band"/></svg>',
    grey: '<svg width="12" height="12" aria-hidden="true"><rect width="12" height="12" class="z-warn"/></svg>',
    dist: '<svg width="12" height="12" aria-hidden="true"><rect width="12" height="12" class="z-crit"/></svg>',
    thrC: '<svg width="20" height="10" aria-hidden="true"><line x1="1" y1="5" x2="19" y2="5" class="thr-crit"/></svg>',
    thrW: '<svg width="20" height="10" aria-hidden="true"><line x1="1" y1="5" x2="19" y2="5" class="thr-warn"/></svg>',
    ref: '<svg width="20" height="10" aria-hidden="true"><line x1="1" y1="5" x2="19" y2="5" class="ref-l"/></svg>',
    bar: '<svg width="12" height="12" aria-hidden="true"><rect x="1" y="1" width="10" height="10" rx="2" style="fill:var(--accent)"/></svg>',
    barHl: '<svg width="12" height="12" aria-hidden="true"><rect x="1" y="1" width="10" height="10" rx="2" style="fill:var(--heading)"/></svg>',
    max: '<svg width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="5" class="dot-max"/></svg>',
    prev: '<svg width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="4.5" class="dot-prev"/></svg>',
    now: '<svg width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="5" class="dot-now"/></svg>',
    outer: '<svg width="14" height="12" aria-hidden="true"><rect width="14" height="12" class="band-outer"/></svg>',
    inner: '<svg width="14" height="12" aria-hidden="true"><rect width="14" height="12" class="band-inner"/></svg>',
    med: '<svg width="22" height="10" aria-hidden="true"><line x1="1" y1="5" x2="21" y2="5" class="ln-med"/></svg>',
  };
  const legendRow = (items, cls = "top") => el("div", { class: "legend-row " + cls }, items);

  /* =====================================================================
     charts
     ===================================================================== */
  const widthOf = (box) => Math.max(260, Math.round(box.clientWidth || box.getBoundingClientRect().width || 600));
  function shadeZones(svg, sc, xy, horizontal, x0, x1) {
    const c0 = Math.max(sc.lo, Math.min(sc.hi, CFG.Z_DISTRESS_CUTOFF)), c1 = Math.max(sc.lo, Math.min(sc.hi, CFG.Z_SAFE_CUTOFF));
    if (horizontal) {
      if (c0 > sc.lo) svgEl("rect", { x: xy(sc.lo), y: x0, width: xy(c0) - xy(sc.lo), height: x1 - x0, class: "z-crit" }, svg);
      if (c1 > c0) svgEl("rect", { x: xy(c0), y: x0, width: xy(c1) - xy(c0), height: x1 - x0, class: "z-warn" }, svg);
    } else {
      if (c0 > sc.lo) svgEl("rect", { x: x0, y: xy(c0), width: x1 - x0, height: xy(sc.lo) - xy(c0), class: "z-crit" }, svg);
      if (c1 > c0) svgEl("rect", { x: x0, y: xy(c1), width: x1 - x0, height: xy(c0) - xy(c1), class: "z-warn" }, svg);
    }
    return [c0, c1];
  }
  /** horizontal bars: rows {label, sub, s, v, lab, cls, tipTitle, tip} */
  function hbars(box, rows, opt = {}) {
    const W = widthOf(box), narrow = W < 520;
    // narrow cards: size the label column to the longest name (up to ~40% of the width) instead of a fixed 76px
    const maxLen = Math.max(4, ...rows.map((r) => String(r.label).length));
    const L = narrow ? Math.max(64, Math.min(Math.round(W * 0.42), Math.round(maxLen * 7.4) + 8)) : opt.L || 164, R = narrow ? 72 : opt.R || 104, T = opt.shade ? 20 : 6, B = 28, rowH = opt.rowH || 38, bh = 14;
    const nName = narrow ? Math.max(6, Math.floor((L - 8) / 7.4)) : 24, nSub = narrow ? Math.max(6, Math.floor((L - 6) / 6.2)) : 26;
    const vals = rows.map((r) => r.v).filter(ok);
    const sc = nice(Math.min(0, opt.min ?? 0, ...vals), Math.max(0, opt.max ?? 0, ...vals), Math.min(opt.nTicks || 6, Math.max(2, Math.floor((W - L - R) / 62))));
    const x = lin(sc.lo, sc.hi, L, W - R);
    const H = T + rows.length * rowH + B, pb = T + rows.length * rowH;
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
    if (opt.shade) {
      const [c0, c1] = shadeZones(svg, sc, x, true, T, pb);
      if (c0 > sc.lo && x(c0) - x(sc.lo) > 50) txt(svg, x(sc.lo) + 4, T - 10, "Distress", "t-muted z-lab");
      if (x(c1) - x(c0) > 44) txt(svg, (x(c0) + x(c1)) / 2, T - 10, "Grey", "t-muted z-lab", "middle");
      if (sc.hi > c1 && x(sc.hi) - x(c1) > 80) txt(svg, x(sc.hi), T - 10, "Safe →", "t-muted z-lab", "end");
    }
    for (const t of sc.ticks) {
      if (t !== 0) svgEl("line", { x1: x(t), x2: x(t), y1: T, y2: pb, class: "grid-l" }, svg);
      txt(svg, x(t), pb + 16, opt.tick ? opt.tick(t, sc.step) : tickLab(t, sc.step), "t-muted num", "middle", 11);
    }
    rows.forEach((d, i) => {
      const y = T + i * rowH, cy = y + rowH / 2;
      const g = svgEl("g", { class: "row" }, svg);
      if (d.s) g.setAttribute("data-s", d.s);
      if (d.sub) { txt(g, 0, cy - 7, clip(d.label, narrow ? nName : 22), "t-head", "start", 12.5, 700); txt(g, 0, cy + 9, clip(d.sub, nSub), "t-muted", "start", 11); }
      else txt(g, 0, cy, clip(d.label, nName), "t-head", "start", 12.5, 700);
      if (ok(d.v)) {
        svgEl("path", { d: barPath(x(0), x(d.v), cy - bh / 2, bh), class: d.cls || "bar" + (d.v < 0 ? " neg" : "") }, g);
        const room = x(d.v) - L;
        if (d.v >= 0) txt(g, x(d.v) + 6, cy, d.lab, "t-ink num", "start", 12, 600);
        else if (room > 7.5 * d.lab.length) txt(g, x(d.v) - 6, cy, d.lab, "t-ink num", "end", 12, 600);
        else txt(g, x(0) + 6, cy, d.lab, "t-ink num", "start", 12, 600);
      } else txt(g, x(0) + 6, cy, "no data", "t-muted", "start", 11.5);
      const hit = svgEl("rect", { x: 0, y, width: W, height: rowH, class: "hit", tabindex: 0, "aria-label": `${d.label} ${d.lab || ""}` }, g);
      bindTip(hit, d.tipTitle || d.label, d.tip || [[d.lab, ""]]);
    });
    svgEl("line", { x1: x(0), x2: x(0), y1: T, y2: pb, class: "zero-l" }, svg);
    box.replaceChildren(svg);
  }
  /** vertical columns by category (years); hl = highlighted index */
  function cols(box, cats, vals, opt = {}) {
    const W = widthOf(box), L = 46, R = 8, T = 20, B = 26, H = opt.h || 200;
    const v = vals.filter(ok);
    const sc = nice(Math.min(0, ...v), Math.max(0, ...v), 4);
    const y = lin(sc.lo, sc.hi, H - B, T);
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
    for (const t of sc.ticks) { svgEl("line", { x1: L, x2: W - R, y1: y(t), y2: y(t), class: t === 0 ? "zero-l" : "grid-l" }, svg); txt(svg, L - 6, y(t), opt.tick ? opt.tick(t, sc.step) : tickLab(t, sc.step), "t-muted num", "end", 10.5); }
    const n = cats.length, band = (W - L - R) / n, bw = Math.min(26, band * 0.62);
    const lstep = Math.max(1, Math.ceil(n / Math.max(2, Math.floor((W - L - R) / 40))));
    cats.forEach((c, i) => {
      const x0 = L + band * i + (band - bw) / 2, val = vals[i];
      const g = svgEl("g", { class: "row" }, svg);
      if (ok(val)) {
        svgEl("path", { d: vbar(x0, y(0), y(val), bw), class: i === opt.hl ? "bar" : "bar hl" }, g);
        if (i === opt.hl) txt(g, x0 + bw / 2, val >= 0 ? y(val) - 9 : y(val) + 10, opt.fmt(val), "t-ink num", "middle", 11, 700);
      }
      if (i % lstep === 0 || i === n - 1) txt(g, x0 + bw / 2, H - B + 14, String(c), "t-muted num", "middle", 10.5);
      const hit = svgEl("rect", { x: L + band * i, y: T, width: band, height: H - B - T, class: "hit", tabindex: 0, "aria-label": `${c}: ${opt.fmt(val)}` }, g);
      bindTip(hit, `${opt.title || ""} · ${c}`, [[opt.fmt(val), opt.unitLabel || ""]]);
    });
    box.replaceChildren(svg);
  }
  /** line chart over index positions; series {vals, cls, dot, label}; opt {zones, hlines, band, active, yFmt, h, xLab, tip, endLabel} */
  function lines(box, xs, series, opt = {}) {
    const W = widthOf(box), L = opt.L || 50, R = opt.R || 48, T = 12, B = 32, H = opt.h || Math.round(Math.min(300, Math.max(210, W * 0.46)));
    let vals = series.flatMap((s) => s.vals).filter(ok);
    (opt.band || []).forEach((b) => { vals = vals.concat(b.lo.filter(ok), b.hi.filter(ok)); });
    (opt.hlines || []).forEach((h) => { if (h.include) vals.push(h.y); });
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (opt.zones) { lo = Math.min(lo, CFG.Z_DISTRESS_CUTOFF - 0.3); hi = Math.max(hi, CFG.Z_SAFE_CUTOFF + 0.3); }
    if (opt.zeroFloor) lo = Math.min(0, lo);
    const pad = (hi - lo || 1) * 0.06; lo -= opt.zeroFloor && lo >= 0 ? 0 : pad; hi += pad;
    const sc = nice(lo, hi, Math.max(3, Math.min(6, Math.floor((H - T - B) / 34))));
    const n = xs.length;
    const x = n > 1 ? lin(0, n - 1, L + 10, W - R) : () => (L + W - R) / 2, y = lin(sc.lo, sc.hi, H - B, T);
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
    if (opt.zones) shadeZones(svg, sc, y, false, L, W - R);
    for (const t of sc.ticks) { svgEl("line", { x1: L, x2: W - R, y1: y(t), y2: y(t), class: t === 0 ? "zero-l" : "grid-l" }, svg); txt(svg, L - 6, y(t), opt.yFmt ? opt.yFmt(t, sc.step) : tickLab(t, sc.step), "t-muted num", "end", 11); }
    (opt.hlines || []).forEach((h) => { if (h.y >= sc.lo && h.y <= sc.hi) { svgEl("line", { x1: L, x2: W - R, y1: y(h.y), y2: y(h.y), class: h.cls }, svg); if (h.label) txt(svg, W - R + 4, y(h.y), h.label, "t-muted", "start", 10.5, 600); } });
    if (opt.active && n > 1) svgEl("rect", { x: x(opt.active[0] - 0.5), y: H - B + 1, width: x(Math.min(opt.active[1] + 0.5, n - 1)) - x(opt.active[0] - 0.5), height: 5, class: "act-band" }, svg);
    const step = Math.max(1, Math.ceil(n / Math.max(2, Math.floor((W - L - R) / 56))));
    xs.forEach((xv, i) => { if (i % step === 0 || i === n - 1) txt(svg, x(i), H - B + 20, opt.xLab ? opt.xLab(i) : String(xv), "t-muted num", "middle", 11); });
    (opt.band || []).forEach((b) => {
      const pts = b.hi.map((v, i) => `${x(i)},${y(v)}`).concat(b.lo.map((v, i) => [i, v]).reverse().map(([i, v]) => `${x(i)},${y(v)}`));
      svgEl("polygon", { points: pts.join(" "), class: b.cls }, svg);
    });
    const dense = n > (opt.maxDots || 15); // long series: dot the latest point only
    series.forEach((s) => {
      const d = s.vals.map((v, i) => [i, v]).filter(([, v]) => ok(v)).map(([i, v], k) => `${k ? "L" : "M"}${x(i)},${y(v)}`).join("");
      if (d) svgEl("path", { d, class: s.cls }, svg);
      if (s.dot) s.vals.forEach((v, i) => { if (ok(v) && !(s.skipFirstDot && i === 0) && (!dense || i === n - 1)) svgEl("circle", { cx: x(i), cy: y(v), r: s.dot === "prev" ? 4 : 4.5, class: "dot-" + s.dot }, svg); });
    });
    if (opt.endLabel) { const s = series[opt.endLabel.series], v = last(s.vals); if (ok(v)) txt(svg, x(n - 1) + 9, y(v), opt.endLabel.fmt(v), "t-ink num", "start", 12, 700); }
    const xh = svgEl("line", { x1: 0, x2: 0, y1: T, y2: H - B, class: "xhair", visibility: "hidden" }, svg);
    const bw = (W - R - L) / Math.max(1, n);
    xs.forEach((xv, i) => {
      const hit = svgEl("rect", { x: x(i) - bw / 2, y: T, width: bw, height: H - B - T, class: "hit", tabindex: 0, "aria-label": String(xv) }, svg);
      const rows = () => (opt.tip ? opt.tip(i) : series.map((s) => [opt.yFmt ? opt.yFmt(s.vals[i], 0.01) : fmt(s.vals[i], 2), s.label || ""]));
      const title = () => (opt.tipTitle ? opt.tipTitle(i) : String(xv));
      hit.addEventListener("pointermove", (ev) => { xh.setAttribute("x1", x(i)); xh.setAttribute("x2", x(i)); xh.setAttribute("visibility", "visible"); showTip(ev, title(), rows()); });
      hit.addEventListener("pointerleave", () => { xh.setAttribute("visibility", "hidden"); hideTip(); });
      hit.addEventListener("focus", (ev) => showTip(ev, title(), rows()));
      hit.addEventListener("blur", hideTip);
    });
    box.replaceChildren(svg);
  }
  function histogram(box, values, opt = {}) {
    const W = widthOf(box), L = 46, R = 14, T = 16, B = 30, H = opt.h || 230;
    const v = values.filter(ok);
    if (!v.length) { box.replaceChildren(el("p", { class: "note" }, "No finite values to plot.")); return; }
    let lo = Math.min(...v), hi = Math.max(...v);
    if (hi - lo < 1e-12) { lo -= 0.5 * (Math.abs(lo) || 1); hi += 0.5 * (Math.abs(hi) || 1); }
    const nb = opt.bins || 40, w = (hi - lo) / nb, counts = new Array(nb).fill(0);
    v.forEach((a) => { counts[Math.min(nb - 1, Math.floor((a - lo) / w))]++; });
    const xs = nice(lo, hi, Math.max(3, Math.min(6, Math.floor((W - L - R) / 80)))), x = lin(xs.lo, xs.hi, L, W - R);
    const ys = nice(0, Math.max(...counts), 4), y = lin(0, ys.hi, H - B, T);
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
    if (opt.zones) shadeZones(svg, xs, x, true, T, H - B);
    for (const t of ys.ticks) { svgEl("line", { x1: L, x2: W - R, y1: y(t), y2: y(t), class: t === 0 ? "axis-l" : "grid-l" }, svg); txt(svg, L - 6, y(t), fmt(t, 0), "t-muted num", "end", 11); }
    for (const t of xs.ticks) txt(svg, x(t), H - B + 16, opt.xFmt ? opt.xFmt(t, xs.step) : tickLab(t, xs.step), "t-muted num", "middle", 11);
    counts.forEach((c, i) => {
      const a = lo + i * w, b = a + w, x0 = x(a) + 1, x1 = x(b) - 1;
      const g = svgEl("g", { class: "row" }, svg);
      if (c) svgEl("path", { d: vbar(x0, y(0), y(c), Math.max(1, x1 - x0), 2), class: "bar" }, g);
      const hit = svgEl("rect", { x: x(a), y: T, width: Math.max(1, x(b) - x(a)), height: H - B - T, class: "hit" }, g);
      bindTip(hit, `${opt.xFmt ? opt.xFmt(a, w) : fmt(a, 2)} to ${opt.xFmt ? opt.xFmt(b, w) : fmt(b, 2)}`, [[String(c), "simulations"]]);
    });
    (opt.vlines || []).forEach((l) => { if (l.x >= xs.lo && l.x <= xs.hi) { svgEl("line", { x1: x(l.x), x2: x(l.x), y1: T, y2: H - B, class: l.cls }, svg); if (l.label) txt(svg, Math.min(W - R - 2, x(l.x) + 4), T + 2, l.label, "t-ink2", x(l.x) > W - 140 ? "end" : "start", 10.5, 600); } });
    box.replaceChildren(svg);
  }

  /* =====================================================================
     state + data
     ===================================================================== */
  const S = { tab: "home", sectorSel: new Set(), built: {} };
  const DATASETS = DATA.datasets || {};
  const coerceRows = (rows) => rows.map((r) => {
    const o = {};
    for (const k in r) {
      if (NUMCOLS.has(k)) { const v = r[k]; o[k] = v === null || v === undefined || String(v).trim() === "" ? NaN : Number(String(v).trim()); }
      else o[k] = r[k] === null || r[k] === undefined ? "" : String(r[k]);
    }
    return o;
  }).filter((r) => r.Entity && ok(r.Year)).map((r) => Object.assign(r, { Year: Math.trunc(r.Year), Sector: r.Sector || "Other" }));
  function unitScale(u) { u = String(u || "").toLowerCase(); return u.includes("billion") ? 1e9 : u.includes("million") ? 1e6 : u.includes("thousand") ? 1e3 : 1; }

  function loadDataset(rows, label, example, key) {
    S.rows = coerceRows(rows);
    S.en = E.enrich(S.rows);
    S.label = label; S.example = !!example; S.key = key;
    if (key !== "upload") { S.mapping = null; S.uploadNote = null; }
    CUR = (S.rows.find((r) => r.Currency) || {}).Currency || "";
    SC = unitScale((S.rows.find((r) => r.Units) || {}).Units);
    S.sectors = uniq(S.en.map((r) => r.Sector)).sort();
    S.sectorSel = new Set(S.sectors);
    S.years = uniq(S.en.map((r) => r.Year)).sort((a, b) => a - b);
    S.names = uniq(S.en.map((r) => r.Entity)).sort();
    S.gdp = key === "report" && M.gdp ? M.gdp : null;
    S.growth = M.gdp_growth ?? CFG.DEFAULT_GDP_GROWTH;
    S.volCache = {};
    initPageState();
    S.built = {};
    renderMeta(); renderFilterbar();
    showTab(S.tab, true);
  }
  const allRows = () => S.en;
  const F = () => S.en.filter((r) => S.sectorSel.has(r.Sector));
  const latestOf = (rows) => E.latestPerEntity(rows);
  function volFor(ent, sector) {
    if (!(ent in S.volCache)) S.volCache[ent] = E.revenueVolatility(S.en, ent);
    const v = S.volCache[ent];
    return ok(v) ? [v, false] : [CFG.SECTOR_REVENUE_VOLATILITY[sector] ?? CFG.SECTOR_REVENUE_VOLATILITY.Other, true];
  }
  const MAGS = ["fuel_shock_pct", "fx_shock_pct", "rate_shock_bps", "revenue_shock_std_devs", "refinancing_spread_bps", "arrears_pct_of_revenue"];
  const ZERO_MAG = Object.fromEntries(MAGS.map((k) => [k, 0]));
  const STD_MAG = Object.fromEntries(MAGS.map((k) => [k, CFG.DEFAULT_SHOCK_PARAMS[k]]));
  const fuelShare = (sector) => CFG.SECTOR_FUEL_COST_SHARE[sector] ?? CFG.SECTOR_FUEL_COST_SHARE.Other;
  /** bottom-up exposures of one SOE-year as plain values (calculations.soe_exposures) */
  const expoFor = (row) => Object.fromEntries(Object.entries(E.soeExposures(row)).map(([k, v]) => [k, v[0]]));
  /** full parameter set for one SOE, as the Shock Scenarios page builds it from its sliders */
  function paramsFor(row, mags, expo, D, H) {
    const p = Object.assign({}, CFG.DEFAULT_SHOCK_PARAMS, expo, mags);
    p.fuel_cost_share = expo.fuel_cost_share ?? fuelShare(row.Sector);
    p.revenue_sigma = volFor(row.Entity, row.Sector)[0];
    p.revenue_shock_pct = p.revenue_shock_std_devs * p.revenue_sigma;
    p.shock_duration_years = Math.min(D, H);
    return p;
  }
  /** every SOE's latest year under the same shock magnitudes; expoFn(row) gives each SOE's exposures */
  function stressAll(rows, mags, expoFn, D, H, lgd, gdp, growth, ead = 1) {
    const gs = gdp ? E.gdpPath(gdp, growth, H) : null;
    return latestOf(rows).map((r) => {
      const ex = expoFn(r);
      const base = E.costPath(E.runScenario(r, paramsFor(r, ZERO_MAG, ex, D, H), H), lgd, gs, ead);
      const pp = paramsFor(r, mags, ex, D, H);
      const str = E.costPath(E.runScenario(r, pp, H), lgd, gs, ead);
      const drop = str.slice(1).some((s, i) => ZORDER.indexOf(s.Zone) < ZORDER.indexOf(base[i + 1].Zone));
      return { row: r, base, str, drop, desc: E.describeShocks(pp), params: pp };
    });
  }
  /** the standard stress (DSA/DSF convention) with each SOE's own exposures — used by Home, Report and Early Warning */
  const standardStress = (rows, mags = STD_MAG) => stressAll(rows, mags, expoFor, CFG.DEFAULT_SHOCK_PARAMS.shock_duration_years, CFG.MC_HORIZON_YEARS, S.efc.lgd, S.gdp, S.growth, S.efc.ead);

  function initPageState() {
    const yrs = S.years, lastY = last(yrs);
    const firstName = S.names[0];
    const efcAll = latestOf(S.en).map((r) => [r.Entity, E.efcRow(r, M.lgd_pct).EFC]).sort((a, b) => (b[1] || 0) - (a[1] || 0));
    S.kpi = { view: "trend", from: yrs[0], to: lastY, soe: firstName, trend: {}, cmp: {}, period: "recent", year: lastY, avgFrom: yrs[0], avgTo: lastY, scCat: "headline", all: false };
    S.alt = { view: "components", soe: firstName, from: yrs[0], to: lastY, period: "recent", year: lastY, avgFrom: yrs[0], avgTo: lastY, all: false };
    S.efc = { year: lastY, mode: "single", lgd: M.lgd_pct ?? CFG.LGD_SLIDER_DEFAULT, per: {}, sens: efcAll.length ? efcAll[0][0] : firstName, basis: "total_liabilities", ead: CFG.EAD_SHARE_DEFAULT, all: false };
    const shockSoe = firstName;
    S.sh = {
      soe: shockSoe, year: null, mags: Object.assign({}, ZERO_MAG), expo: null, expoSrc: {}, expoFor: null,
      H: 3, D: 2, lgd: M.lgd_pct ?? CFG.LGD_SLIDER_DEFAULT, ead: CFG.EAD_SHARE_DEFAULT, view: "single", ptab: "fuel", allExpo: "own",
      mc: { n: CFG.MC_DEFAULT_SIMULATIONS, fsd: CFG.MC_DEFAULT_FUEL_STD, xsd: CFG.MC_DEFAULT_FX_STD, rsd: CFG.MC_DEFAULT_RATE_STD_BPS, vsd: CFG.MC_DEFAULT_REVENUE_STD_SD,
        corr: Object.assign({}, CFG.MC_DEFAULT_CORRELATIONS, { "fuel|fx": CFG.MC_DEFAULT_CORRELATION }) },
    };
    S.rep = { scen: "combined", soe: null, all: false };
    S.asm = { status: new Set(Object.keys(CFG.PARAMETER_STATUS_LABELS)), group: "all" };
    S.gre = { sov: "BB", outlook: "Stable", role: {}, link: {}, sel: firstName };
    S.ew = { tl: null };
  }

  /* ---------- band + filter bar ---------- */
  function renderMeta() {
    const box = $("#meta"); box.replaceChildren();
    const add = (a, b) => box.appendChild(el("span", {}, a + " ", el("b", {}, b)));
    add("Portfolio", `${pl(S.names.length, "SOE")} · ${pl(S.sectors.length, "sector")}`);
    add("Statements", S.years.length > 1 ? `${S.years[0]}–${last(S.years)}` : String(S.years[0] ?? "—"));
    if (CUR) add("Currency", CUR + (SC !== 1 ? ` (${(S.rows.find((r) => r.Units) || {}).Units})` : ""));
    if (S.example) box.appendChild(el("span", { class: "example-flag" }, "▲ " + S.label));
    $("#appTitle").textContent = M.title;
  }
  function renderFilterbar() {
    const box = $("#sectorChips"); box.replaceChildren();
    const all = el("button", { class: "chip", type: "button", "aria-pressed": String(S.sectorSel.size === S.sectors.length) }, "All");
    all.addEventListener("click", () => { S.sectorSel = new Set(S.sectors); sectorChanged(); });
    box.appendChild(all);
    S.sectors.forEach((s) => {
      const b = el("button", { class: "chip", type: "button", "aria-pressed": String(S.sectorSel.has(s) && S.sectorSel.size !== S.sectors.length) }, s);
      b.addEventListener("click", () => {
        if (S.sectorSel.size === S.sectors.length) S.sectorSel = new Set([s]);
        else if (S.sectorSel.has(s)) { S.sectorSel.delete(s); if (!S.sectorSel.size) S.sectorSel = new Set(S.sectors); }
        else S.sectorSel.add(s);
        sectorChanged();
      });
      box.appendChild(b);
    });
    const yrs = uniq(F().map((r) => r.Year)).sort((a, b) => a - b);
    $("#asof").replaceChildren("Data as of ", el("b", {}, yrs.length > 1 ? `${yrs[0]}–${last(yrs)}` : String(yrs[0] ?? "—")), ` · ${pl(uniq(F().map((r) => r.Entity)).length, "SOE")} shown`);
  }
  function sectorChanged() { renderFilterbar(); S.built = {}; showTab(S.tab, true); }

  /* ---------- tabs ---------- */
  const FILTER_TABS = new Set(["kpi", "altman", "efc", "warning"]);
  const pages = {};
  function showTab(id, force) {
    if (!pages[id]) id = "home";
    S.tab = id;
    document.querySelectorAll("#tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === id)));
    document.querySelectorAll("main .page").forEach((p) => { p.hidden = p.id !== id; });
    $("#filterbar").hidden = !FILTER_TABS.has(id);
    const root = document.getElementById(id);
    if (!S.built[id] || force) { pages[id].build(root); S.built[id] = true; }
    pages[id].render();
    // "#view-<tab>" deep-links a tab; the token matches no element id, so the browser never jumps the page to it
    try { history.replaceState(null, "", "#view-" + id); } catch (e) { /* hash is optional */ }
  }
  document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => { showTab(b.dataset.tab); window.scrollTo({ top: 0 }); }));
  function rebuild() { const root = document.getElementById(S.tab); pages[S.tab].build(root); pages[S.tab].render(); }

  /* =====================================================================
     HOME
     ===================================================================== */
  const MODULES = [
    ["Country Analysis", "This tool", "ok", "Upload a country's SOE statements: KPIs, Altman Z-EM, expected fiscal cost, shocks, government support, early warning and the report."],
    ["Global Monitoring", "Prototype", "watch", "Cross-country SOE benchmarking (Pacific monitor first). Needs the standardised multi-country repository."],
    ["Hidden Subsidies", "Planned", "none", "Financing advantage over comparable private firms × SOE base. Formula and variables still to be confirmed from the reference note."],
    ["PSO Analysis", "Planned", "none", "Public service obligations: separating PSO costs from inefficiency, building on the viability assessment here."],
    ["Energy Fiscal Risk", "Separate model", "none", "Tariffs, cost recovery and subsidies in the power sector (Ghana model, other team). The fuel shock here covers pass-through and subsidy cases."],
  ];
  /** hero + four headline tiles for the whole portfolio (Home and the Report's executive summary) */
  function overviewBlocks(hero, tiles, st) {
    const rows = latestOf(allRows()).sort((a, b) => b.Z_EM - a.Z_EM), n = rows.length;
    const zc = zoneCounts(rows);
    hero.replaceChildren(
      el("div", { class: "hero-label" }, "SOEs in distress or the grey zone"),
      el("div", { class: "hero-value" }, n ? Math.round(((zc.Distress + zc.Grey) / n) * 100) + "%" : "—", el("small", {}, `${zc.Distress + zc.Grey} of ${pl(n, "SOE")} · average Z″ ${fmt(mean(rows.map((r) => r.Z_EM)), 2)}`)),
      ...zoneBar(zc, n),
      el("p", { class: "note", style: "margin:0" }, E.zoneSummary(rows)));
    const lgd = S.efc.lgd, efc = rows.map((r) => ({ r, e: E.efcRow(r, lgd, S.efc.ead, S.efc.basis).EFC }));
    const total = sum(efc.map((x) => x.e));
    const top = efc.slice().sort((a, b) => (b.e || 0) - (a.e || 0))[0];
    const drops = st.filter((x) => x.drop).map((x) => x.row.Entity);
    const eB = sum(st.map((x) => last(x.base).EFC)), eS = sum(st.map((x) => last(x.str).EFC));
    const first = new Map();
    byYearAsc(allRows()).forEach((r) => { if (!first.has(r.Entity)) first.set(r.Entity, r); });
    const moved = rows.map((r) => ({ r, f: first.get(r.Entity), dz: r.Z_EM - first.get(r.Entity).Z_EM })).filter((m) => m.f.Year !== m.r.Year);
    const worst = moved.sort((a, b) => a.dz - b.dz)[0];
    let efcSt = null;
    if (S.gdp) { const g = total / S.gdp; efcSt = g >= CFG.REPORT_EFC_GDP_ALERT ? "alert" : g >= CFG.REPORT_EFC_GDP_WATCH ? "watch" : "ok"; }
    const eadTxt = S.efc.basis === "guaranteed_debt" ? "EAD guaranteed debt where reported" : `EAD ${pct0(S.efc.ead)} of liabilities`;
    const dropTxt = drops.length > 4 ? drops.slice(0, 4).join(", ") + ` and ${drops.length - 4} more` : drops.join(", ");
    tiles.replaceChildren(
      tile("Expected fiscal cost, portfolio", efcSt, efcSt ? STLABEL[efcSt] : null, money(total), CUR,
        S.gdp ? `${pctS(total / S.gdp)} of GDP · LGD ${fmt(lgd, 0)}% · ${eadTxt}` : `PD × EAD × LGD, latest year · LGD ${fmt(lgd, 0)}% · ${eadTxt} · add GDP on the Expected Fiscal Cost tab`),
      top ? tile("Largest single exposure", zk(top.r.Zone), ZLABEL[zk(top.r.Zone)], money(top.e), CUR, `${top.r.Entity} · ${total ? Math.round((top.e / total) * 100) : 0}% of portfolio EFC · rated ${top.r.Rating}, PD ${pctAuto(E.pdByRating(top.r.Rating))}`) : null,
      tile("Drop a zone under standard stress", drops.length ? "alert" : "ok", drops.length ? "Alert" : "Good", String(drops.length), `of ${pl(n, "SOE")}`,
        (drops.length ? dropTxt + " · " : "") + `portfolio EFC ${sgn(eB ? (eS / eB - 1) * 100 : NaN, 0)}% against no shock in year ${CFG.MC_HORIZON_YEARS} · each SOE's own exposures`),
      worst && worst.dz < 0
        ? tile("Fastest deterioration", zk(worst.r.Zone), ZLABEL[zk(worst.r.Zone)], sgn(worst.dz, 2), "Z″ points", `${worst.r.Entity}: ${fmt(worst.f.Z_EM, 2)} in ${worst.f.Year} to ${fmt(worst.r.Z_EM, 2)} in ${worst.r.Year} · ${worst.f.Rating} to ${worst.r.Rating}`)
        : tile("Fastest deterioration", "ok", "Good", "None", "", moved.length ? "No SOE's Z″ fell over the period" : "Needs at least two years per SOE"),
    );
    return { rows, zc, total, top, drops, eB, eS, worst };
  }
  const byYearAsc = (rows) => rows.slice().sort((a, b) => a.Year - b.Year);
  const pct0 = (v) => fmt(v * 100, 0) + "%";
  const go = (id, label) => el("a", { href: "#view-" + id, onclick: (e) => { e.preventDefault(); showTab(id); window.scrollTo({ top: 0 }); } }, label);
  /** snake_case template headers in statement order (schema.template_frame) and the variable dictionary */
  const SCHEMA_VARS = () => (CFG.SCHEMA ? CFG.SCHEMA.variables.slice().sort((a, b) => CFG.SCHEMA.statements.indexOf(a.statement) - CFG.SCHEMA.statements.indexOf(b.statement)) : []);
  const templateCSV = () => SCHEMA_VARS().map((v) => v.key).join(",") + "\n";
  const dictionaryCSV = () => toCSV(["key", "label", "statement", "kind", "required", "used by", "tool column", "also recognised as"],
    SCHEMA_VARS().map((v) => [v.key, v.label, v.statement, v.kind, v.required ? "yes" : "", v.used_by, v.column, v.synonyms.join("; ")]));
  function mappingDetails(mp) {
    const renamed = mp.report.filter((r) => r["Mapped to"] && r["Mapped to"] !== r["Uploaded column"]);
    const review = mp.report.filter((r) => r.Confidence === "LOW" || r.Method === "unmatched" || r.Method === "duplicate");
    const conf = (c, m) => (c === "HIGH" ? stChip("ok", "High") : c === "MEDIUM" ? stChip("none", "Medium") : c === "LOW" ? stChip("watch", "Low · check") : stChip("none", m === "duplicate" ? "Duplicate" : "Not used"));
    return el("details", { class: "plain", open: review.length ? true : null },
      el("summary", {}, `Column mapping — ${renamed.length} renamed to the standard schema, ${review.length} to review`),
      simpleTable(["Uploaded column", "Mapped to", "Schema key", "Method", "Confidence"], mp.report.map((r) => [r["Uploaded column"], r["Mapped to"] || "—", r["Schema key"] || "—", r.Method, el("td", {}, conf(r.Confidence, r.Method))]), { cls: "compact", tall: mp.report.length > 14 }),
      el("p", { class: "note" }, "High = exact name, Medium = known synonym, Low = close spelling (check it). Unmatched and duplicate columns are kept but not used."));
  }
  pages.home = {
    build(root) {
      const H = {};
      this.H = H;
      H.hero = el("div", { class: "card s5 hero" });
      H.tiles = el("div", { class: "s7 tiles" });
      H.data = card("Data", "One row per SOE-year, raw financial statement fields. Every ratio and score is computed from them.", null, "top");
      H.dq = card("Data quality and provenance", "Where the numbers come from, as far as the file says", null, "top");
      H.about = card("How it works", null, null);
      const mods = el("div", { class: "modules" }, MODULES.map(([name, status, k, text]) => el("div", { class: "module" + (k === "ok" ? " on" : "") },
        el("div", { class: "tile-top" }, el("span", { class: "module-name" }, name), stChip(k, status)), el("p", {}, text))));
      root.replaceChildren(
        pageHead("SOE FISCAL RISK TOOL", "SOE Fiscal Risk Dashboard",
          "A layered framework for state-owned enterprises: financial diagnostics (KPI Dashboard), distress signal (Altman Z-EM), fiscal exposure to the sovereign (Expected Fiscal Cost), dynamic shock simulation (Shock Scenarios), government support, trigger rules (Early Warning), and a five-section Report."),
        el("div", { class: "grid" }, H.hero, H.tiles),
        el("h3", { class: "sec-label" }, "Where this tool sits in the SOE fiscal-risk toolkit"), mods,
        el("div", { class: "grid", style: "margin-top:16px" }, el("div", { class: "s7" }, H.data.root), el("div", { class: "s5 stack" }, H.dq.root, H.about.root)),
      );
      this.buildData(H.data.body);
      this.buildQuality(H.dq.body);
      this.buildAbout(H.about.body);
    },
    buildData(body) {
      const status = el("div", { class: "alert-box hint" });
      status.appendChild(el("span", {}, el("b", {}, S.label || "Loaded data"), ` · ${pl(S.names.length, "SOE")}, ${S.rows.length} SOE-year rows, ${S.years[0]}–${last(S.years)}`));
      const btns = el("div", { class: "btn-row", style: "margin-top:12px" });
      if (DATASETS.report && S.key !== "report") btns.appendChild(el("button", { class: "btn", type: "button", onclick: () => loadDataset(DATASETS.report.rows, DATASETS.report.label, DATASETS.report.example, "report") }, "Back to: " + DATASETS.report.label));
      if (DATASETS.sample) btns.appendChild(el("button", { class: "btn", type: "button", onclick: () => loadDataset(DATASETS.sample.rows, DATASETS.sample.label, true, "sample") }, "Use example data (SOE A — Energy, SOE B — Transport)"));
      if (DATASETS.demo) btns.appendChild(el("button", { class: "btn", type: "button", onclick: () => loadDataset(DATASETS.demo.rows, DATASETS.demo.label, true, "demo") }, "Use demo portfolio (8 SOEs, 7 sectors)"));
      const msg = el("div");
      const input = el("input", { type: "file", id: "upload", accept: ".csv,.xlsx,.xls", style: "max-width:100%" });
      const dz = el("div", { class: "dropzone" }, el("label", { class: "lbl", for: "upload" }, "Upload your own data — CSV or Excel, one row per SOE-year"), input,
        el("small", { class: "muted" }, "Column names are matched to the standard schema (exact names, known synonyms, close spellings) and the mapping is shown for review. The file is read in this browser only; nothing is sent anywhere. Excel files need an internet connection the first time (the reader loads from cdnjs)."));
      const handle = (file) => readUpload(file, msg);
      input.addEventListener("change", () => { const f = input.files[0]; if (f) handle(f); input.value = ""; });
      dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("over"); });
      dz.addEventListener("dragleave", () => dz.classList.remove("over"));
      dz.addEventListener("drop", (e) => { e.preventDefault(); dz.classList.remove("over"); if (e.dataTransfer.files[0]) handle(e.dataTransfer.files[0]); });
      const tmpl = el("div", { class: "btn-row", style: "margin-top:10px" }, el("span", { class: "chips-label" }, "Standard template"),
        dataButtons(templateCSV, "soe_tool_template.csv", "template"), dataButtons(dictionaryCSV, "soe_variable_dictionary.csv", "dictionary"));
      const cols = el("details", { class: "plain" }, el("summary", {}, "Required and optional columns"),
        el("p", { class: "note" }, el("b", {}, "Required: "), CFG.REQUIRED_COLUMNS.join(", ") + "."),
        el("p", { class: "note" }, el("b", {}, "Optional, used when present: "), "Short Term Debt, FX Debt, Fuel Cost and the exposure shares (bottom-up shock exposures); Government Guaranteed Debt (observed EAD); Source File, Source Page, Audit Status, Extraction Method and Data Quality Flag (provenance). The full list with synonyms is on the ", go("assumptions", "Assumptions & sources"), " tab."));
      const prevCols = ["Entity", "Year", "Sector", "Revenues", "Operating Profits (EBIT)", "Net Income", "Total Assets", "Total Liabilities", "Equity", "Government Grants"];
      const preview = el("details", { class: "plain" }, el("summary", {}, `Data preview (${S.rows.length} rows)`),
        simpleTable(prevCols, S.rows.slice(0, 300).map((r) => prevCols.map((c) => (NUMCOLS.has(c) && c !== "Year" ? money(r[c]) : String(r[c] ?? "")))), { tall: true, right: (i) => i >= 3 }));
      const note = S.uploadNote ? el("div", { class: "alert-box ok", style: "margin-top:10px" }, S.uploadNote) : null;
      put(body, status, btns, el("hr", { class: "divider" }), dz, note, msg, S.mapping ? mappingDetails(S.mapping) : null, tmpl, cols, preview);
    },
    buildQuality(body) {
      const rows = S.rows, n = rows.length, latest = latestOf(S.en);
      const blocks = [];
      ["Data Quality Flag", "Audit Status", "Extraction Method"].forEach((c) => {
        if (!rows.some((r) => r[c])) return;
        const m = new Map();
        rows.forEach((r) => { const v = r[c] || "(blank)"; m.set(v, (m.get(v) || 0) + 1); });
        const items = [...m.entries()].sort((a, b) => b[1] - a[1]);
        blocks.push(el("div", { class: "dq-row" }, el("span", { class: "lbl" }, c),
          el("div", { class: "dq-bar", role: "img", "aria-label": items.map(([v, k]) => `${v} ${k}`).join(", ") }, items.map(([v, k], i) => el("span", { class: "q" + Math.min(i, 3), style: `width:${(k / n) * 100}%`, title: `${v}: ${k} rows` }))),
          el("div", { class: "dq-legend" }, items.map(([v, k], i) => el("span", {}, el("i", { class: "q" + Math.min(i, 3) }), `${v} `, el("b", { class: "num" }, String(k)))))));
      });
      const ex = latest.map((r) => Object.values(E.soeExposures(r)).filter(([, src]) => /^(Observed|Derived)/.test(src)).length);
      const withEx = ex.filter((k) => k > 0).length;
      const withG = uniq(S.en.filter((r) => ok(r["Government Guaranteed Debt"])).map((r) => r.Entity)).length;
      const facts = el("ul", { class: "facts" },
        el("li", {}, el("b", {}, `${withEx} of ${pl(latest.length, "SOE")}`), " carry at least one shock exposure in the data (fuel cost, FX or short-term debt, exposure shares); the rest use sector or generic defaults on the Shock Scenarios tab."),
        el("li", {}, el("b", {}, `${withG} of ${pl(latest.length, "SOE")}`), " report government-guaranteed debt, which the Expected Fiscal Cost tab can use as the exposure at default."),
        el("li", {}, "Parameters: ", el("b", {}, String(CFG.PARAMETER_REGISTER.filter((r) => r.status === "placeholder").length)), " of " + CFG.PARAMETER_REGISTER.length + " numbers the tool uses are still placeholders that need a source — see ", go("assumptions", "Assumptions & sources"), "."));
      body.replaceChildren(...(blocks.length ? blocks : [el("p", { class: "note", style: "margin-top:0" }, "This file carries no provenance columns. Add source_file, source_page, audit_status, extraction_method and data_quality_flag (they are in the standard template) to record where each number came from and whether it is audited, extracted or a proxy.")]), facts);
    },
    buildAbout(body) {
      body.replaceChildren(
        el("ol", { class: "steps" },
          el("li", {}, go("report", "Report"), " — the portfolio in five sections: executive summary, financial performance, distress and fiscal risk, stress tests, policy implications. Prints to PDF when the page is opened on its own."),
          el("li", {}, go("kpi", "KPI Dashboard"), " — profitability, liquidity, solvency and fiscal-dependency ratios against illustrative thresholds; trend per SOE (any number of years) and comparison across SOEs."),
          el("li", {}, go("altman", "Altman Z-EM"), " — the four components, the score, benchmarking, and the distress / grey / safe distribution with an indicative rating."),
          el("li", {}, go("efc", "Expected Fiscal Cost"), " — PD × EAD × LGD: PD from each SOE's rating band, EAD a share of total liabilities or reported guaranteed debt, LGD set by you."),
          el("li", {}, go("shock", "Shock Scenarios"), " — fuel, FX, interest-rate, revenue, refinancing and arrears shocks through each SOE's own exposures over a multi-year horizon, with a correlated Monte Carlo option."),
          el("li", {}, go("gre", "Government Support"), " — Role × Link support tier and bounded rating uplift, capped by the sovereign."),
          el("li", {}, go("warning", "Early Warning"), " — trigger rules and the signal each SOE sends."),
          el("li", {}, go("assumptions", "Assumptions & sources"), " — every coefficient and default with its source and status, and the standard data dictionary.")),
        el("p", { class: "note" }, "Every calculation runs in this page with the same formulas and config.py values as the Python tool."),
        el("details", { class: "plain" }, el("summary", {}, "Glossary — what the terms mean"),
          simpleTable(["Term", "Meaning"], Object.entries(CFG.GLOSSARY).map(([k, v]) => [k, v]), { cls: "glossary" })),
      );
    },
    render() {
      overviewBlocks(this.H.hero, this.H.tiles, standardStress(allRows()));
    },
  };
  function readUpload(file, msg) {
    const done = (raw) => {
      if (!raw.length) { msg.replaceChildren(el("div", { class: "alert-box warn", style: "margin-top:10px" }, "The file has no data rows.")); return; }
      const mp = E.standardizeColumns(Object.keys(raw[0]));
      const rows = raw.map((r) => { const o = {}; for (const k in r) o[mp.rename[k] || k] = r[k]; return o; });
      const cols = Object.keys(rows[0]);
      const missing = CFG.REQUIRED_COLUMNS.filter((c) => !cols.includes(c));
      if (missing.length) {
        msg.replaceChildren(el("div", { class: "alert-box warn", style: "margin-top:10px" }, `Missing required column(s): ${missing.join(", ")}. Check the column mapping below, rename or add these columns, and upload again.`), mappingDetails({ report: mp.report }));
        return;
      }
      const reqNum = CFG.NUMERIC_COLUMNS.filter((c) => CFG.REQUIRED_COLUMNS.includes(c));
      const co = coerceRows(rows);
      const bad = co.filter((r) => reqNum.some((c) => !ok(r[c]))).length;
      S.mapping = { report: mp.report };
      S.uploadNote = `✓ Loaded ${pl(uniq(co.map((r) => r.Entity)).length, "SOE")}, ${co.length} SOE-year rows from ${file.name}.` + (bad ? ` ${bad} row(s) have non-numeric or missing required values.` : "");
      loadDataset(rows, file.name, false, "upload");
      showTab("home", true);
    };
    const fail = (e) => msg.replaceChildren(el("div", { class: "alert-box warn", style: "margin-top:10px" }, `Couldn't read that file: ${e}`));
    const name = file.name.toLowerCase();
    if (name.endsWith(".csv")) {
      file.text().then((t) => done(parseCSV(t))).catch(fail);
    } else {
      // the standard template keeps the data on a sheet named "Data" (with Dictionary and Readme sheets beside it)
      const go2 = () => file.arrayBuffer().then((buf) => { const wb = window.XLSX.read(buf, { type: "array" }); const sh = wb.SheetNames.includes("Data") ? "Data" : wb.SheetNames[0]; done(window.XLSX.utils.sheet_to_json(wb.Sheets[sh], { defval: "" })); }).catch(fail);
      if (window.XLSX) go2();
      else {
        const sc = el("script", { src: "https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js" });
        sc.onload = go2; sc.onerror = () => fail("the Excel reader could not load (offline?). Save the sheet as CSV and upload that instead.");
        document.head.appendChild(sc);
      }
    }
  }
  function parseCSV(text) {
    const rows = []; let row = [], f = "", q = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (q) { if (c === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += c; }
      else if (c === '"') q = true;
      else if (c === ",") { row.push(f); f = ""; }
      else if (c === "\n" || c === "\r") { if (c === "\r" && text[i + 1] === "\n") i++; row.push(f); rows.push(row); row = []; f = ""; }
      else f += c;
    }
    if (f !== "" || row.length) { row.push(f); rows.push(row); }
    if (!rows.length) return [];
    const head = rows.shift().map((h) => h.trim().replace(/^﻿/, ""));
    return rows.filter((r) => r.some((v) => String(v).trim() !== "")).map((r) => Object.fromEntries(head.map((h, i) => [h, r[i] ?? ""])));
  }

  /* =====================================================================
     KPI DASHBOARD
     ===================================================================== */
  const SPEC = CFG.KPI_THRESHOLDS;
  function kpiFmt(key, v) {
    if (!ok(v)) return "n/a";
    if (SPEC[key].unit === "%") return fmt(v * 100, Math.abs(v) >= 1 ? 0 : 1) + "%";
    return fmt(v, Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2) + "×";
  }
  const kpiTitle = (k) => `${SPEC[k].label} (${SPEC[k].unit === "%" ? "%" : "x"})`;
  function kpiTick(key) { return SPEC[key].unit === "%" ? (t) => fmt(t * 100, 0) + "%" : (t, s) => tickLab(t, s) + "×"; }
  function cutText(key) {
    const sp = SPEC[key], f = (v) => (sp.unit === "%" ? fmt(v * 100, 0) + "%" : fmt(v, 1) + "×");
    return sp.direction === "higher_is_better" ? `alert < ${f(sp.red_cut)}, good ≥ ${f(sp.green_cut)}` : `alert > ${f(sp.red_cut)}, good ≤ ${f(sp.green_cut)}`;
  }
  const SUPPRESS = { roe: ["Equity", "negative equity"], debt_to_equity: ["Equity", "negative equity"], debt_to_ebitda: ["EBITDA", "negative EBITDA"], depreciation_to_ebitda: ["EBITDA", "negative EBITDA"], effective_tax_rate: ["Operating Profits (EBIT)", "negative EBIT"] };
  function kpiStatus(row, key) {
    const v = row[key], [lab] = E.classify(v, key);
    if (!ok(v) && SUPPRESS[key] && row[SUPPRESS[key][0]] <= 0) return { st: "alert", why: SUPPRESS[key][1] };
    return { st: RAG[lab] || null };
  }
  function periodRows(rows, st, keyCols) {
    // Most recent year per SOE | specific year | average across selected years (mean of each column)
    if (S.years.length < 2 || st.period === "recent") return latestOf(rows);
    if (st.period === "year") return rows.filter((r) => r.Year === st.year);
    const sel = rows.filter((r) => r.Year >= st.avgFrom && r.Year <= st.avgTo);
    return uniq(sel.map((r) => r.Entity)).map((e) => {
      const g = sel.filter((r) => r.Entity === e), o = { Entity: e, Sector: g[0].Sector, Year: null, _avg: true };
      keyCols.forEach((c) => { o[c] = mean(g.map((r) => r[c])); });
      return o;
    });
  }
  function periodControls(st, onChange) {
    const box = el("div", { class: "row-ctl" });
    if (S.years.length < 2) return box;
    box.appendChild(el("div", { class: "fld" }, el("span", { class: "lbl" }, "Period"), seg([["recent", "Most recent year"], ["year", "Specific year"], ["avg", "Average across years"]], st.period, (v) => { st.period = v; rebuild(); }, "Period")));
    if (st.period === "year") box.appendChild(fSelect("Year", S.years, st.year, (v) => { st.year = v; onChange(); }, { num: true }));
    if (st.period === "avg") box.appendChild(yearRangeCtl(S.years, st.avgFrom, st.avgTo, (f, t) => { st.avgFrom = f; st.avgTo = t; onChange(); }, "Years to average"));
    return box;
  }
  function periodLabel(st) { return S.years.length < 2 || st.period === "recent" ? "most recent year per SOE" : st.period === "year" ? String(st.year) : st.avgFrom === st.avgTo ? String(st.avgFrom) : `average of ${st.avgFrom}–${st.avgTo}`; }

  /** KPI scorecard table: latest year per SOE, most alerts first (KPI Dashboard and Report) */
  function scorecard(rowsK, avail, keys, expanded) {
    const latest = latestOf(rowsK);
    const scored = latest.map((r) => {
      const stt = Object.fromEntries(avail.map((k) => [k, kpiStatus(r, k)]));
      const prev = rowsK.filter((x) => x.Entity === r.Entity && x.Year < r.Year).sort((a, b) => b.Year - a.Year)[0];
      return { r, stt, prev, na: Object.values(stt).filter((s) => s.st === "alert").length, nw: Object.values(stt).filter((s) => s.st === "watch").length };
    }).sort((a, b) => b.na - a.na || a.r.Z_EM - b.r.Z_EM);
    const t = el("table");
    t.appendChild(el("thead", {}, el("tr", {}, el("th", {}, "SOE"), el("th", {}, "Z″ · zone"), keys.map((k) => el("th", { title: SPEC[k].description }, SPEC[k].label, el("br"), SPEC[k].unit === "%" ? "(%)" : "(×)")), el("th", { title: "Alerts out of all KPIs available" }, "Alerts"))));
    const tb = el("tbody");
    clipRows(scored, expanded).forEach(({ r, stt, prev, na, nw }) => {
      const tr = el("tr", { "data-s": slug(r.Sector) }, nameCell(r.Entity, r.Sector), statusCell(zk(r.Zone), fmt(r.Z_EM, 2), `${ZLABEL[zk(r.Zone)] || r.Zone} · ${r.Rating}`));
      keys.forEach((k) => { const s = stt[k]; tr.appendChild(statusCell(s.st, kpiFmt(k, r[k]), s.why || (prev && ok(prev[k]) ? `${prev.Year}: ${kpiFmt(k, prev[k])}` : null))); });
      const pips = el("span", { class: "pips", "aria-hidden": "true" });
      for (let i = 0; i < avail.length; i++) pips.appendChild(el("span", { class: i < na ? "on" : i < na + nw ? "w" : "" }));
      tr.appendChild(el("td", {}, el("span", { class: "flagcount" }, pips, `${na} / ${avail.length}`)));
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    const legend = legendRow([el("span", {}, stChip("ok")), el("span", {}, stChip("watch")), el("span", {}, stChip("alert")),
      el("span", { class: "lt" }, el("b", {}, "Cutoffs: "), keys.map((k) => `${SPEC[k].label} ${cutText(k)}`).join(" · ")),
      el("span", { class: "lt" }, "n/a with a reason: the ratio is suppressed because equity, EBITDA or EBIT is negative, and counts as an alert.")], "");
    return { table: el("div", { class: "tbl-wrap" }, t), legend, scored };
  }
  pages.kpi = {
    build(root) {
      const st = S.kpi, H = (this.H = {});
      if (!S.years.includes(st.from)) st.from = S.years[0];
      if (!S.years.includes(st.to)) st.to = last(S.years);
      const rowsK = () => F().filter((r) => r.Year >= st.from && r.Year <= st.to);
      this.rowsK = rowsK;
      const avail = E.availableKpis(rowsK());
      this.avail = avail;
      const tools = el("div", { class: "row-ctl" },
        el("div", { class: "fld" }, el("span", { class: "lbl" }, "View"), seg([["trend", "Trend for one SOE"], ["compare", "Compare across SOEs"], ["scorecard", "Full scorecard"]], st.view, (v) => { st.view = v; rebuild(); })),
        S.years.length > 1 ? yearRangeCtl(S.years, st.from, st.to, (f, t) => { st.from = f; st.to = t; rebuild(); }) : null);
      const head = pageHead("PERFORMANCE MONITORING", "KPI Dashboard", "Profitability, liquidity, solvency, and fiscal-dependency ratios. Pick a ratio from each column's dropdown — thresholds are illustrative, pending recalibration.");
      const foot = el("div", { class: "foot" },
        el("div", {}, el("b", {}, "Thresholds. "), "Illustrative IMF SOE Health Check Tool-style red/amber/green cuts — provisional starting points, not calibrated to a specific country sample."),
        el("div", {}, el("b", {}, "Suppressed ratios. "), "ROE, Debt/Equity, Debt/EBITDA, Depreciation/EBITDA and the effective tax rate show n/a when equity, EBITDA or EBIT is negative — the ratio's sign flips and would otherwise read as good. The scorecard counts these as alerts, as the guidance note recommends."));
      H.out = el("div");
      root.replaceChildren(head, el("div", { class: "card", style: "margin-bottom:16px" }, tools), H.out, foot);
      if (!avail.length) { H.out.replaceChildren(el("div", { class: "alert-box warn" }, "None of the KPI input fields were found in the data.")); return; }
      if (st.view === "trend") this.buildTrend();
      else if (st.view === "compare") this.buildCompare();
      else this.buildScorecard();
    },
    catKpis(cat) { return CFG.KPI_CATEGORIES[cat].filter((k) => this.avail.includes(k)); },
    buildTrend() {
      const st = S.kpi, H = this.H, names = uniq(this.rowsK().map((r) => r.Entity)).sort();
      if (!names.includes(st.soe)) st.soe = names[0];
      H.cards = {};
      const grid = el("div", { class: "grid4" });
      CFG.CATEGORY_ORDER.forEach((cat) => {
        const ks = this.catKpis(cat), c = card(CFG.CATEGORY_LABELS[cat], null, null, "top");
        if (!ks.length) { c.body.appendChild(el("p", { class: "kpi-desc" }, "No ratios available in this category for the current data.")); grid.appendChild(c.root); return; }
        if (!ks.includes(st.trend[cat])) st.trend[cat] = ks[0];
        const chart = el("div", { class: "chart" }), desc = el("p", { class: "kpi-desc" }), btn = el("div");
        c.body.append(fSelect("Ratio", ks.map((k) => [k, kpiTitle(k)]), st.trend[cat], (v) => { st.trend[cat] = v; this.render(); }), chart, desc, btn);
        H.cards[cat] = { chart, desc, btn };
        grid.appendChild(c.root);
      });
      H.out.replaceChildren(el("div", { class: "row-ctl", style: "margin-bottom:12px" }, fSelect("SOE", names, st.soe, (v) => { st.soe = v; this.render(); })), grid);
    },
    buildCompare() {
      const st = S.kpi, H = this.H;
      H.cards = {};
      const grid = el("div", { class: "grid4" });
      CFG.CATEGORY_ORDER.forEach((cat) => {
        const ks = this.catKpis(cat), c = card(CFG.CATEGORY_LABELS[cat], null, null, "top");
        if (!ks.length) { c.body.appendChild(el("p", { class: "kpi-desc" }, "No ratios available in this category for the current data.")); grid.appendChild(c.root); return; }
        if (!ks.includes(st.cmp[cat])) st.cmp[cat] = ks[0];
        const chart = el("div", { class: "chart" }), desc = el("p", { class: "kpi-desc" }), btn = el("div");
        c.body.append(fSelect("Ratio", ks.map((k) => [k, kpiTitle(k)]), st.cmp[cat], (v) => { st.cmp[cat] = v; this.render(); }), chart, desc, btn);
        H.cards[cat] = { chart, desc, btn };
        grid.appendChild(c.root);
      });
      H.period = el("div", { class: "note period-line" });
      H.out.replaceChildren(el("div", { style: "margin-bottom:8px" }, periodControls(st, () => this.render())), H.period, grid,
        legendRow([el("span", {}, stChip("ok")), el("span", {}, stChip("watch")), el("span", {}, stChip("alert")), el("span", { class: "lt" }, "Bars take the colour of their status; values carry the same symbol.")], ""));
    },
    buildScorecard() {
      const st = S.kpi, H = this.H;
      const cats = [["headline", "Headline"], ...CFG.CATEGORY_ORDER.filter((c) => this.catKpis(c).length).map((c) => [c, CFG.CATEGORY_LABELS[c]]), ["all", "All"]];
      H.table = el("div"); H.legend = el("div");
      const c = card("Full SOE scorecard", "Latest year per SOE within the selected years · SOEs with the most alerts come first", seg(cats, st.scCat, (v) => { st.scCat = v; this.render(); }, "KPI category"));
      H.more = el("div");
      H.btn = el("div", { style: "margin-top:10px" });
      c.body.append(H.table, H.more, H.legend, H.btn);
      H.out.replaceChildren(c.root);
    },
    render() {
      const st = S.kpi, H = this.H;
      if (!this.avail || !this.avail.length) return;
      if (st.view === "trend") {
        const d = this.rowsK().filter((r) => r.Entity === st.soe).sort((a, b) => a.Year - b.Year);
        for (const cat in H.cards) {
          const k = st.trend[cat], { chart, desc, btn } = H.cards[cat];
          const dd = d.filter((r) => ok(r[k]));
          desc.textContent = SPEC[k].description;
          if (d.length < 2) { chart.replaceChildren(el("p", { class: "kpi-desc" }, `Only one year of data for ${st.soe} — need at least two to plot a trend.`)); btn.replaceChildren(); continue; }
          if (!dd.length) { chart.replaceChildren(el("p", { class: "kpi-desc" }, "No data for this ratio.")); btn.replaceChildren(); continue; }
          if (dd.length >= LINE_CHART_MIN_YEARS) {
            // long series (e.g. 20 years): a line reads better than a thicket of thin bars
            lines(chart, dd.map((r) => r.Year), [{ vals: dd.map((r) => r[k]), cls: "ln", dot: "hl", label: SPEC[k].label }],
              { h: 190, L: 46, R: 14, yFmt: kpiTick(k), tipTitle: (i) => `${st.soe} · ${dd[i].Year}`, tip: (i) => [[kpiFmt(k, dd[i][k]), SPEC[k].label], [STLABEL[RAG[E.classify(dd[i][k], k)[0]]] || "—", cutText(k)]] });
          } else cols(chart, dd.map((r) => r.Year), dd.map((r) => r[k]), { hl: dd.length - 1, fmt: (v) => kpiFmt(k, v), tick: kpiTick(k), title: SPEC[k].label, h: 190 });
          btn.replaceChildren(dataButtons(() => toCSV(["Entity", "Sector", "Year", k], dd.map((r) => [r.Entity, r.Sector, r.Year, r[k]])), `${st.soe}_${k}_trend.csv`));
        }
      } else if (st.view === "compare") {
        const keys = this.avail;
        const base = periodRows(this.rowsK(), st, keys);
        const nE = uniq(base.map((r) => r.Entity)).length;
        put(H.period, el("span", {}, "Showing: ", el("b", {}, periodLabel(st)), nE > LIMIT ? ` · ${st.all ? "all " + nE + " SOEs" : `the ${LIMIT} weakest of ${nE} SOEs on each ratio`}, weakest first` : " · weakest first"),
          moreToggle(nE, st.all, (v) => { st.all = v; this.render(); }));
        for (const cat in H.cards) {
          const k = st.cmp[cat], { chart, desc, btn } = H.cards[cat];
          const dir = SPEC[k].direction === "higher_is_better" ? 1 : -1;
          const rowsAll = base.filter((r) => ok(r[k])).sort((a, b) => dir * (a[k] - b[k]));
          const rows = clipRows(rowsAll, st.all);
          desc.textContent = SPEC[k].description;
          if (!rows.length) { chart.replaceChildren(el("p", { class: "kpi-desc" }, "No data for this ratio in the current selection.")); btn.replaceChildren(); continue; }
          hbars(chart, rows.map((r) => {
            const s = RAG[E.classify(r[k], k)[0]] || "none";
            return { label: r.Entity, v: r[k], cls: "bar st-" + s, lab: `${GLYPH[s] || ""} ${kpiFmt(k, r[k])}`.trim(), s: slug(r.Sector), tipTitle: `${r.Entity} · ${r.Sector}`, tip: [[kpiFmt(k, r[k]), SPEC[k].label], [STLABEL[s] || "No data", cutText(k)]] };
          }), { L: 70, R: 66, rowH: 28, nTicks: 3, tick: kpiTick(k) });
          btn.replaceChildren(dataButtons(() => toCSV(["Entity", "Sector", k], rowsAll.map((r) => [r.Entity, r.Sector, r[k]])), `${k}_by_soe.csv`));
        }
      } else {
        const cat = st.scCat;
        const keys = cat === "headline" ? CFG.REPORT_HEADLINE_KPIS.filter((k) => this.avail.includes(k)) : cat === "all" ? this.avail : this.catKpis(cat);
        const rowsK = this.rowsK(), latest = latestOf(rowsK);
        const sc = scorecard(rowsK, this.avail, keys, st.all);
        H.table.replaceChildren(sc.table);
        put(H.more, moreToggle(latest.length, st.all, (v) => { st.all = v; this.render(); }, `Show the ${LIMIT} with most alerts only`));
        H.legend.replaceChildren(sc.legend);
        H.btn.replaceChildren(dataButtons(() => toCSV(["Entity", "Sector", "Year", ...this.avail], latest.map((r) => [r.Entity, r.Sector, r.Year, ...this.avail.map((k) => r[k])])), "kpi_scorecard.csv"));
      }
    },
  };

  /* =====================================================================
     ALTMAN Z-EM
     ===================================================================== */
  const ZKEYS = ["X1", "X2", "X3", "X4"];
  const SHORT = { X1: "WC / assets", X2: "RE / assets", X3: "EBIT / assets", X4: "Equity / liab." };
  const COMP_TITLES = { X1: "X1: Working capital / assets", X2: "X2: Retained earnings / assets", X3: "X3: EBIT / assets", X4: "X4: Equity / liabilities", Z_EM: "Z-EM score" };
  const GLOSS = { X1: "X1", X2: "X2", X3: "X3", X4: "X4", Z_EM: "Z-EM score" };
  pages.altman = {
    build(root) {
      const st = S.alt, H = (this.H = {});
      const head = pageHead("FINANCIAL DISTRESS SIGNAL", "Altman Z-EM Score", "The four components behind the Altman Z″-EM score, the score itself, and where each SOE sits in the distress / grey / safe distribution. Hover the i icons for plain-language definitions.");
      H.out = el("div");
      const c = CFG.ZEM_COEFFICIENTS;
      const foot = el("div", { class: "foot" }, el("div", {}, el("b", {}, "Z-EM score. "), `Z = ${c.X1}·X1 + ${c.X2}·X2 + ${c.X3}·X3 + ${c.X4}·X4${CFG.ZEM_CONSTANT ? " + " + CFG.ZEM_CONSTANT : ""} (no constant — Eidelman convention). Z ≤ ${CFG.Z_DISTRESS_CUTOFF} distress, ${CFG.Z_DISTRESS_CUTOFF}–${CFG.Z_SAFE_CUTOFF} grey zone, > ${CFG.Z_SAFE_CUTOFF} safe. The rating is an indicative cohort mapping for reference only. For SOEs with large government transfers the unadjusted score is more likely to overstate than understate health.`));
      root.replaceChildren(head, el("div", { class: "card", style: "margin-bottom:16px" }, el("div", { class: "row-ctl" }, el("div", { class: "fld" }, el("span", { class: "lbl" }, "View"), seg([["components", "Components for one SOE"], ["portfolio", "Portfolio view"]], st.view, (v) => { st.view = v; rebuild(); })))), H.out, foot);
      if (st.view === "components") this.buildComponents(); else this.buildPortfolio();
    },
    buildComponents() {
      const st = S.alt, H = this.H, names = uniq(F().map((r) => r.Entity)).sort();
      if (!names.includes(st.soe)) st.soe = names[0];
      const yrs = uniq(F().filter((r) => r.Entity === st.soe).map((r) => r.Year)).sort((a, b) => a - b);
      if (!yrs.includes(st.from)) st.from = yrs[0];
      if (!yrs.includes(st.to)) st.to = last(yrs);
      const ctl = el("div", { class: "row-ctl", style: "margin-bottom:12px" }, fSelect("SOE", names, st.soe, (v) => { st.soe = v; rebuild(); }));
      if (yrs.length > 2) ctl.append(fSelect("From", yrs, st.from, (v) => { st.from = Math.min(v, st.to); this.render(); }, { num: true }), fSelect("To", yrs, st.to, (v) => { st.to = Math.max(v, st.from); this.render(); }, { num: true }));
      H.charts = {};
      const grid = el("div", { class: "grid3" });
      ["X1", "X2", "X3", "X4", "Z_EM"].forEach((k) => {
        const chart = el("div", { class: "chart" });
        const c = el("div", { class: "card top" }, el("div", { class: "card-head", style: "margin-bottom:6px" }, el("div", {}, el("h3", {}, COMP_TITLES[k], info(CFG.GLOSSARY[GLOSS[k]] || "")))), chart);
        if (k === "Z_EM") c.insertBefore(legendRow([legendItem(LG.thrC, `Distress (${CFG.Z_DISTRESS_CUTOFF})`), legendItem(LG.thrW, `Safe threshold (${CFG.Z_SAFE_CUTOFF})`)]), chart);
        H.charts[k] = chart; grid.appendChild(c);
      });
      H.sum = el("div", { class: "card top" });
      grid.appendChild(H.sum);
      H.narr = el("div", { style: "margin-top:16px" });
      H.out.replaceChildren(ctl, grid, H.narr);
    },
    buildPortfolio() {
      const st = S.alt, H = this.H;
      H.label = el("div", { class: "note period-line" });
      H.bench = card("Benchmark across SOEs", null, null); H.dist = card("Portfolio distribution", null, null); H.drv = card("Scorecard and what drives each score", "Weighted contribution of each component (β × ratio), with the tool's rule-based reading underneath. Bars share one scale.");
      H.bench.body.append(el("div", { class: "chart" })); H.dist.body.append(el("div"));
      H.out.replaceChildren(el("div", { style: "margin-bottom:8px" }, periodControls(st, () => this.render())), H.label,
        el("div", { class: "grid" }, el("div", { class: "s7" }, H.bench.root), el("div", { class: "s5" }, H.dist.root), el("div", { class: "s12" }, H.drv.root)));
    },
    render() {
      const st = S.alt, H = this.H;
      if (st.view === "components") {
        const full = F().filter((r) => r.Entity === st.soe).sort((a, b) => a.Year - b.Year);
        const d = full.filter((r) => r.Year >= st.from && r.Year <= st.to);
        if (full.length < 2) {
          Object.values(H.charts).forEach((c) => c.replaceChildren(el("p", { class: "kpi-desc" }, `Only one year of data for ${st.soe} — need at least two to plot a trend.`)));
        } else {
          for (const k in H.charts) {
            const zs = k === "Z_EM";
            lines(H.charts[k], d.map((r) => r.Year), [{ vals: d.map((r) => r[k]), cls: "ln", dot: zs ? "now" : "hl", label: COMP_TITLES[k] }], {
              h: 190, R: 16, L: 44, zones: zs, hlines: zs ? [{ y: CFG.Z_DISTRESS_CUTOFF, cls: "thr-crit" }, { y: CFG.Z_SAFE_CUTOFF, cls: "thr-warn" }] : [],
              tip: (i) => [[fmt(d[i][k], zs ? 2 : 3), COMP_TITLES[k]], ...(zs ? [[d[i].Rating, ZLABEL[zk(d[i].Zone)]]] : [[sgn(d[i][k + "_contrib"], 2), "weighted contribution to Z″"]])],
            });
          }
        }
        H.sum.replaceChildren(el("h3", { style: "font-size:15px;margin-bottom:8px" }, "Summary"), summaryBox(E.zTrendSummary(d, st.soe)), el("div", { style: "margin-top:10px" },
          dataButtons(() => toCSV(["Entity", "Sector", "Year", "X1", "X2", "X3", "X4", "Z_EM", "Zone"], d.map((r) => [r.Entity, r.Sector, r.Year, ...["X1", "X2", "X3", "X4", "Z_EM"].map((c) => +(+r[c]).toFixed(3)), r.Zone])), `${st.soe}_z_components.csv`)));
        H.narr.replaceChildren(el("div", { class: "card" }, summaryBox(E.singleNarrative(last(full)), `Reading for ${last(full).Year} — rule-based, generated from the numbers`)));
        return;
      }
      const cols = ["Z_EM", ...ZKEYS, ...ZKEYS.map((k) => k + "_contrib")];
      const rows = periodRows(F(), st, cols).map((r) => Object.assign({}, r, r._avg ? { Zone: E.classifyZone(r.Z_EM), Rating: E.zRating(r.Z_EM) } : {})).sort((a, b) => a.Z_EM - b.Z_EM);
      const shown = clipRows(rows, st.all);
      put(H.label, el("span", {}, "Showing: ", el("b", {}, periodLabel(st)), rows.length > LIMIT ? ` · ${st.all ? "all " + rows.length + " SOEs" : `the ${LIMIT} weakest of ${rows.length} SOEs`} in the benchmark and scorecard, weakest first` : " · weakest first"),
        moreToggle(rows.length, st.all, (v) => { st.all = v; this.render(); }));
      hbars(H.bench.body.firstChild, shown.map((r) => ({ label: r.Entity, sub: r.Sector, s: slug(r.Sector), v: r.Z_EM, lab: `${fmt(r.Z_EM, 2)} · ${r.Rating}`, tipTitle: `${r.Entity} · ${r.Sector}`, tip: [[fmt(r.Z_EM, 2), "Z″" + (r._avg ? " (average)" : ` (${r.Year})`)], [ZLABEL[zk(r.Zone)] || r.Zone, "zone"], [r.Rating, `rating · PD ${pctAuto(E.pdByRating(r.Rating))}`]] })), { shade: true, max: CFG.Z_SAFE_CUTOFF + 0.4 });
      if (!H.bench.body.querySelector(".btn-row")) H.bench.body.appendChild(el("div", { style: "margin-top:8px" }));
      H.bench.body.lastChild.replaceChildren(dataButtons(() => toCSV(["Entity", "Sector", "Year", "Z_EM", "Zone", "Rating"], rows.map((r) => [r.Entity, r.Sector, r.Year ?? "avg", r.Z_EM, r.Zone, r.Rating])), "altman_z_benchmark.csv"));
      const zc = zoneCounts(rows), n = rows.length;
      H.dist.body.firstChild.replaceChildren(el("div", { class: "hero", style: "gap:12px" },
        el("div", { class: "hero-value", style: "font-size:40px" }, String(zc.Distress), el("small", {}, `of ${pl(n, "SOE")} in distress`)), ...zoneBar(zc, n), summaryBox(E.zoneSummary(rows))));
      // drivers table
      const maxAbs = Math.max(0.5, ...shown.flatMap((r) => ZKEYS.map((k) => Math.abs(r[k + "_contrib"])).filter(ok)));
      const t = el("table", { id: "compTable" });
      t.appendChild(el("thead", {}, el("tr", {}, el("th", {}, "SOE"), el("th", {}, "Year"), ZKEYS.map((k) => el("th", { title: CFG.ZEM_LABELS[k] }, `${k} · ${["working capital", "retained earnings", "EBIT", "equity / liabilities"][ZKEYS.indexOf(k)]}`)), el("th", {}, "Z″ · zone"), el("th", {}, "Rating · PD"))));
      const tb = el("tbody");
      const cross = E.crossNarrative(rows), flags = Object.fromEntries(cross.table.map((x) => [x.Entity, x.Flag]));
      shown.forEach((r) => {
        tb.appendChild(el("tr", { class: "main", "data-s": slug(r.Sector) }, nameCell(r.Entity, r.Sector), el("td", {}, r.Year ?? "avg"),
          ZKEYS.map((k) => {
            const c = r[k + "_contrib"];
            return el("td", { title: `${CFG.ZEM_LABELS[k]} = ${fmt(r[k], 3)} × ${CFG.ZEM_COEFFICIENTS[k]} = ${fmt(c, 2)}` }, el("div", { class: "mini" },
              el("div", { class: "track" }, ok(c) ? el("span", { class: c >= 0 ? "pos" : "neg", style: `width:${(Math.min(Math.abs(c), maxAbs) / maxAbs) * 50}%` }) : null), el("span", { class: "val num" }, sgn(c, 2))));
          }),
          statusCell(zk(r.Zone), fmt(r.Z_EM, 2), ZLABEL[zk(r.Zone)] || r.Zone), el("td", { style: "white-space:nowrap" }, `${r.Rating} · ${pctAuto(E.pdByRating(r.Rating))}`)));
        const rd = el("td", { class: "reading", colspan: "8" });
        boldText(rd, E.singleNarrative(r).replace(/^\*\*[^*]*\*\*\s*/, "") || "—");
        const fl = [flags[r.Entity]];
        if (ok(r.grants_to_revenue) && r.grants_to_revenue > SPEC.grants_to_revenue.red_cut && r.Zone !== "Distress") fl.push(`Grants equal ${fmt(r.grants_to_revenue * 100, 0)}% of revenue, so Z″ likely overstates health`);
        if (fl.filter(Boolean).length) { rd.appendChild(el("br")); fl.filter(Boolean).forEach((f) => rd.appendChild(el("span", { class: "flag" }, f))); }
        tb.appendChild(el("tr", { class: "read", "data-s": slug(r.Sector) }, rd));
      });
      t.appendChild(tb);
      H.drv.body.replaceChildren(el("div", { class: "tbl-wrap" }, t), el("p", { class: "note" }, cross.paragraph),
        el("div", { style: "margin-top:8px" }, dataButtons(() => toCSV(["Entity", "Sector", "Year", "Z_EM", "Zone", "Rating", ...ZKEYS, ...ZKEYS.map((k) => k + "_contrib")], rows.map((r) => [r.Entity, r.Sector, r.Year ?? "avg", r.Z_EM, r.Zone, r.Rating, ...ZKEYS.map((k) => r[k]), ...ZKEYS.map((k) => r[k + "_contrib"])])), "altman_z_scorecard.csv")));
    },
  };

  /* =====================================================================
     EXPECTED FISCAL COST
     ===================================================================== */
  function gdpField(onChange) {
    const id = nid("gdp");
    const inp = el("input", { type: "number", id, min: "0", step: "any", placeholder: "e.g. 9500000000000", value: S.gdp ? String(S.gdp) : "" });
    const hint = el("small", {}, "Optional. Same currency and units as the statements.");
    const upd = () => { const v = Number(inp.value); S.gdp = inp.value.trim() && v > 0 ? v / 1 : null; hint.textContent = S.gdp ? `= ${money(S.gdp, true)}` : "Optional. Same currency and units as the statements."; onChange(); };
    inp.addEventListener("change", upd); inp.addEventListener("input", () => { clearTimeout(inp._t); inp._t = setTimeout(upd, 350); });
    if (S.gdp) hint.textContent = `= ${money(S.gdp, true)}`;
    return el("div", { class: "fld" }, el("label", { for: id }, el("span", {}, `Country GDP${CUR ? " (" + CUR + ")" : ""}`, info("Enter nominal GDP to express EFC as a share of GDP. Shared between the Expected Fiscal Cost and Shock Scenarios tabs."))), inp, hint);
  }
  pages.efc = {
    build(root) {
      const st = S.efc, H = (this.H = {});
      const yrs = uniq(F().map((r) => r.Year)).sort((a, b) => a - b);
      if (!yrs.includes(st.year)) st.year = last(yrs);
      const view = F().filter((r) => r.Year === st.year);
      const names = uniq(view.map((r) => r.Entity)).sort();
      const settings = card("Settings", null, null, "top");
      const lgdBox = el("div", { class: "fields" });
      if (st.mode === "single") lgdBox.appendChild(fSlider("LGD", { min: CFG.LGD_SLIDER_MIN, max: CFG.LGD_SLIDER_MAX, step: 1, value: st.lgd, fmt: (v) => v + "%", info: CFG.GLOSSARY.LGD }, (v) => { st.lgd = v; this.render(); }));
      else names.forEach((n) => lgdBox.appendChild(fSlider(`${n} LGD`, { min: CFG.LGD_SLIDER_MIN, max: CFG.LGD_SLIDER_MAX, step: 1, value: st.per[n] ?? st.lgd, fmt: (v) => v + "%" }, (v) => { st.per[n] = v; this.render(); })));
      const gRows = view.filter((r) => ok(r["Government Guaranteed Debt"])).length;
      H.eadNote = el("small", { class: "muted" });
      settings.body.append(el("div", { class: "fields" },
        fSelect("Year", yrs, st.year, (v) => { st.year = v; rebuild(); }, { num: true }),
        el("div", { class: "fld" }, el("span", { class: "lbl" }, "LGD input mode"), seg([["single", "Single LGD"], ["per", "Per-SOE LGD"]], st.mode, (v) => { st.mode = v; rebuild(); })),
        lgdBox,
        el("div", { class: "fld" }, el("span", { class: "lbl" }, "Exposure at default (EAD)", info("What the government would have to cover if the SOE defaulted. Total liabilities overstate it when part of the debt is owed to parties the government would not bail out, so 60% and 80% are sensitivity cases. Where the data report government-guaranteed debt, that observed figure can be used instead.")),
          seg([["total_liabilities", "Share of liabilities"], ["guaranteed_debt", "Guaranteed debt"]], st.basis, (v) => { st.basis = v; rebuild(); }, "EAD basis"),
          el("small", { class: "muted" }, st.basis === "guaranteed_debt"
            ? (gRows ? `${gRows} of ${pl(view.length, "SOE")} report guaranteed debt in ${st.year}; the others fall back to the share of liabilities below.` : `No SOE reports Government Guaranteed Debt in ${st.year}, so every SOE uses the share of liabilities below.`)
            : "Proxy: a share of total liabilities (100% was the original assumption).")),
        fSlider(st.basis === "guaranteed_debt" ? "Fallback: share of total liabilities" : "EAD: share of total liabilities", { min: 0.5, max: 1, step: 0.1, value: st.ead, fmt: pct0, info: "60% and 80% are the sensitivity cases agreed for the proxy; 100% counts every liability." }, (v) => { st.ead = v; this.render(); }),
        gdpField(() => this.render())));
      H.tiles = el("div", { class: "grid3 sm" });
      H.bar = card("EFC by SOE", null, null); H.bar.body.append(el("div", { class: "chart" }), el("div", { style: "margin-top:8px" }));
      if (!names.includes(st.sens)) st.sens = names[0];
      H.sens = card("Government backstop sensitivity — one SOE", null, fSelect(null, names, st.sens, (v) => { st.sens = v; this.render(); }));
      H.sens.head.querySelector(".card-tools").prepend(el("span", { class: "chips-label" }, "SOE"));
      H.sens.body.append(el("div"), el("div", { class: "chart" }), el("p", { class: "note" }));
      const ref = card("LGD calibration reference", "Government LGD by sector from GEMs public-lending recovery data 1994–2024. Lender recovery rate is taken directly as government LGD: a high lender recovery reflects a large government backstop.");
      ref.body.appendChild(simpleTable(["Sector · GEMs source row", "Average", "P10–P90", "n"],
        Object.entries(CFG.SECTOR_RECOVERY_DATA).map(([s, d]) => [nameCell(s, d.gems_source), pct(d.average, 1), `${fmt(d.p10 * 100, 0)}–${fmt(d.p90 * 100, 0)}%`, String(d.n_defaults)]), { right: (i) => i >= 1, cls: "compact" }));
      ref.root.querySelectorAll("td.name").forEach((t) => (t.style.whiteSpace = "normal"));
      H.table = card("EFC results", null, null);
      root.replaceChildren(
        pageHead("FISCAL EXPOSURE", "Expected Fiscal Cost", "EFC = PD × EAD × LGD — PD from each SOE's own Z-EM-derived rating (20-band cohort table), EAD a share of total liabilities or the reported guaranteed debt, LGD set by you. A triage-level estimate, not a budget forecast."),
        el("div", { class: "grid" }, el("div", { class: "s4 sticky-panel" }, settings.root), el("div", { class: "s8 stack" }, H.tiles, H.bar.root)),
        el("div", { class: "grid", style: "margin-top:16px" }, el("div", { class: "s7" }, H.sens.root), el("div", { class: "s5" }, ref.root), el("div", { class: "s12" }, H.table.root)),
        el("div", { class: "foot" }, el("div", {}, el("b", {}, "Triage-level estimate. "), "PD is each SOE's own one-year PD from the rating cohort table — a placeholder pending probit-estimated probabilities. EAD is a proxy (a share of total liabilities) unless the data report government-guaranteed debt and that basis is selected; the table's EAD column says which each SOE used.")));
    },
    render() {
      const st = S.efc, H = this.H;
      const view = F().filter((r) => r.Year === st.year);
      const res = view.map((r) => { const lgd = st.mode === "single" ? st.lgd : st.per[r.Entity] ?? st.lgd; return Object.assign({ r, lgd }, E.efcRow(r, lgd, st.ead, st.basis)); }).sort((a, b) => (b.EFC || 0) - (a.EFC || 0));
      const eadShort = (x) => (x.EAD_source.startsWith("Observed") ? "guaranteed debt" : `${pct0(st.ead)} of liabilities`);
      const total = sum(res.map((x) => x.EFC)), g = S.gdp;
      H.tiles.replaceChildren(
        tile(`Aggregate EFC${CUR ? " (" + CUR + ")" : ""}`, null, null, money(total), "", g ? `${pctS(total / g)} of GDP · ${st.year}` : `${st.year} · ${CFG.GLOSSARY.EFC.split(".")[0]}.`),
        tile("SOEs in Distress zone", res.some((x) => x.r.Zone === "Distress") ? "alert" : "ok", null, String(res.filter((x) => x.r.Zone === "Distress").length), `of ${res.length}`, `Z-EM ≤ ${CFG.Z_DISTRESS_CUTOFF}`),
        tile("SOEs assessed", null, null, String(res.length), "", `LGD ${st.mode === "single" ? st.lgd + "% for all" : "set per SOE"} · EAD ${st.basis === "guaranteed_debt" ? `guaranteed debt for ${res.filter((x) => x.EAD_source.startsWith("Observed")).length}, else ${pct0(st.ead)} of liabilities` : pct0(st.ead) + " of liabilities"}`));
      H.bar.head.querySelector(".sub") || H.bar.head.firstChild.appendChild(el("p", { class: "sub" }));
      H.bar.head.querySelector(".sub").textContent = `${st.year} · ${g ? "labels show share of GDP" : "labels show share of portfolio EFC"}` + (res.length > LIMIT ? ` · ${st.all ? "all " + res.length + " SOEs" : `the ${LIMIT} largest of ${res.length}`}` : "");
      hbars(H.bar.body.firstChild, clipRows(res, st.all).map((x) => ({
        label: x.r.Entity, sub: `${x.r.Rating} · PD ${pctAuto(x.PD)}`, s: slug(x.r.Sector), v: ok(x.EFC) ? x.EFC * SC : null, cls: "bar",
        lab: `${money(x.EFC)} · ${g ? pctS(x.EFC / g) : pct(total ? x.EFC / total : NaN, 0)}`, tipTitle: `${x.r.Entity} · ${x.r.Sector}`,
        tip: [[money(x.EFC, true), "expected fiscal cost"], [pctAuto(x.PD), `PD (${x.r.Rating})`], [money(x.EAD, true), `EAD (${eadShort(x)})`], [x.lgd + "%", "LGD"]],
      })), { tick: (t, s) => moneyTick(t / SC, s / SC), nTicks: 4 });
      H.bar.body.lastChild.replaceChildren(el("div", { class: "btn-row" }, moreToggle(res.length, st.all, (v) => { st.all = v; this.render(); }, `Show the ${LIMIT} largest only`),
        dataButtons(() => toCSV(["Entity", "Sector", "Zone", "Z_EM", "Rating", "PD", "EAD", "EAD_source", "LGD", "EFC"], res.map((x) => [x.r.Entity, x.r.Sector, x.r.Zone, x.r.Z_EM, x.r.Rating, x.PD, x.EAD, x.EAD_source, x.LGD, x.EFC])), `efc_${st.year}.csv`)));
      // backstop sensitivity
      const s = res.find((x) => x.r.Entity === st.sens) || res[0];
      if (s) {
        const sc = E.recoveryScenarios(s.r.Sector), pdMax = E.worstPdInZone(s.r.Zone), isD = s.r.Rating === "D";
        const [lgBox, chart, note] = H.sens.body.children;
        const recs = sc.map(([label, lgd]) => ({ label, lgd, efc: s.PD * s.EAD * lgd, max: pdMax * s.EAD * lgd }));
        lgBox.replaceChildren(legendRow([legendItem(LG.bar, `At own PD (${s.r.Rating}, ${pctAuto(s.PD)})`), isD ? null : legendItem(LG.max, `At zone max PD (${pctAuto(pdMax)})`), legendItem(LG.ref, `Current baseline, LGD ${s.lgd}%`)]));
        backstop(chart, recs, s.EFC, isD);
        const d = CFG.SECTOR_RECOVERY_DATA[s.r.Sector] || CFG.SECTOR_RECOVERY_DATA.Other;
        note.textContent = `From GEMs' 10th/25th/average/90th-percentile recovery rates for ${s.r.Sector} (source row: ${d.gems_source}, n = ${d.n_defaults} defaults). High backstop intensity means the government has historically absorbed more, so EFC rises from low to high. ` +
          (isD ? "Rated D, so own PD is already the maximum and the zone-max marker is left out. " : "Zone max PD is an interim placeholder pending a dedicated maximum-PD table. ") + "A static what-if on LGD, separate from the shock module.";
      }
      H.table.body.replaceChildren(simpleTable(["SOE", "Zone", "Z-EM", "Rating", "PD", `EAD${CUR ? " (" + CUR + ")" : ""}`, "EAD basis", "LGD", `EFC${CUR ? " (" + CUR + ")" : ""}`, ...(g ? ["EFC / GDP"] : []), "Share"],
        res.map((x) => [nameCell(x.r.Entity, x.r.Sector), el("td", {}, zoneChip(x.r.Zone)), fmt(x.r.Z_EM, 2), x.r.Rating, pctAuto(x.PD), money(x.EAD), el("td", { class: "muted", style: "white-space:nowrap" }, eadShort(x)), x.lgd + "%", money(x.EFC), ...(g ? [pctS(x.EFC / g)] : []), pct(total ? x.EFC / total : NaN, 1)]),
        { right: (i) => i >= 2 && i !== 3 && i !== 6, tall: res.length > 15, foot: ["Portfolio", "", "", "", "", money(sum(res.map((x) => x.EAD))), "", "", money(total), ...(g ? [pctS(total / g)] : []), "100%"] }));
    },
  };
  function backstop(box, recs, current, isD) {
    const W = widthOf(box), L = 56, R = 10, T = 18, B = 44, H = Math.round(Math.min(280, Math.max(220, W * 0.5)));
    const vals = recs.flatMap((p) => [p.efc, isD ? null : p.max]).concat([current]).filter(ok).map((v) => v * SC);
    const sc = nice(0, Math.max(...vals, 1), 4), y = lin(sc.lo, sc.hi, H - B, T);
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
    for (const t of sc.ticks) { svgEl("line", { x1: L, x2: W - R, y1: y(t), y2: y(t), class: t === 0 ? "axis-l" : "grid-l" }, svg); txt(svg, L - 6, y(t), moneyTick(t / SC, sc.step / SC), "t-muted num", "end", 11); }
    const band = (W - R - L) / recs.length, bw = Math.min(24, band * 0.4), short = ["Low · P10", "P25", "Average", "High · P90"];
    recs.forEach((p, i) => {
      const cx = L + band * i + band / 2, g = svgEl("g", { class: "row" }, svg);
      if (ok(p.efc)) { svgEl("path", { d: vbar(cx - bw / 2, y(0), y(p.efc * SC), bw), class: "bar" }, g); txt(g, cx - (isD ? 0 : 4), y(p.efc * SC) - 10, money(p.efc), "t-ink num", isD ? "middle" : "end", 11, 600); }
      if (!isD && ok(p.max)) svgEl("circle", { cx: cx + bw / 2 + 8, cy: y(p.max * SC), r: 5, class: "dot-max" }, g);
      txt(g, cx, H - B + 16, short[i], "t-ink2", "middle", 11.5, 600);
      txt(g, cx, H - B + 31, "LGD " + fmt(p.lgd * 100, 0) + "%", "t-muted num", "middle", 11);
      const hit = svgEl("rect", { x: cx - band / 2, y: T, width: band, height: H - B - T + 36, class: "hit", tabindex: 0, "aria-label": `${p.label} EFC ${money(p.efc)}` }, g);
      bindTip(hit, p.label, [[money(p.efc, true), "at own PD"], ...(isD ? [] : [[money(p.max, true), "at zone max PD"]]), [fmt(p.lgd * 100, 1) + "%", "government LGD"]]);
    });
    if (ok(current)) svgEl("line", { x1: L, x2: W - R, y1: y(current * SC), y2: y(current * SC), class: "ref-l" }, svg);
    box.replaceChildren(svg);
  }

  /* =====================================================================
     SHOCK SCENARIOS
     ===================================================================== */
  const pctSig = (v) => (v > 0 ? "+" : "") + fmt(v * 100, 0) + "%";
  const SLIDERS = {
    fuel: [
      ["fuel_cost_share", "Fuel cost share of OpEx", 0, 0.6, 0.01, pct0, "What share of this SOE's operating costs is spent on fuel. Higher share = more exposed to a fuel price shock."],
      ["fuel_shock_pct", "Fuel price shock", -0.5, 1, 0.01, pctSig, CFG.GLOSSARY["Fuel shock"] + " Negative means fuel gets cheaper. 0 = no shock."],
      ["tariff_passthrough", "Tariff pass-through rate (Case B)", 0, 1, 0.05, pct0, CFG.GLOSSARY["Tariff pass-through"] + " Case B: customers pay this share of the fuel-cost change through tariffs."],
      ["fuel_subsidy_share", "Government subsidy share (Case C)", 0, 1, 0.05, pct0, "Case C: the government pays this share of the fuel-cost change directly — a budget outlay reported as a direct fuel subsidy, on top of the expected fiscal cost. The SOE absorbs whatever customers and the government do not (Case A)."],
    ],
    fx: [
      ["fx_shock_pct", "FX shock", -0.3, 0.6, 0.01, pctSig, CFG.GLOSSARY["FX shock"] + " Negative means the local currency strengthens. 0 = no shock."],
      ["fx_cost_share", "FX share of operating costs", 0, 1, 0.05, pct0, "What share of this SOE's costs are paid in a foreign currency (e.g. imported fuel or equipment)."],
      ["fx_revenue_share", "FX share of revenue", 0, 1, 0.05, pct0, "What share of revenue is earned in a foreign currency. If lower than the FX cost share, a weaker local currency hurts profit."],
      ["fx_debt_share", "FX share of total liabilities", 0, 1, 0.05, pct0, "What share of debt is denominated in a foreign currency. A weaker local currency revalues it upward."],
    ],
    rates: [
      ["floating_debt_share", "Floating-rate share of debt", 0, 1, 0.05, pct0, "What share of debt has an interest rate that moves with market rates."],
      ["rate_shock_bps", "Interest rate shock", -500, 1000, 25, (v) => (v > 0 ? "+" : "") + fmt(v, 0) + " bps", CFG.GLOSSARY["Interest rate shock"] + " Negative means rates fall. 0 = no shock."],
      ["revenue_shock_std_devs", "Revenue shock", -3, 3, 0.25, (v) => (v > 0 ? "+" : "") + fmt(v, 2) + " s.d.", "0 = no shock. The standard DSA/DSF stress-test convention is −1 standard deviation of the SOE's own revenue growth."],
      ["revenue_elasticity", "EBIT elasticity to revenue shock", 0, 2, 0.1, (v) => fmt(v, 1), "How much EBIT moves for a given revenue change. 1.0 means one-for-one."],
      ["near_term_maturity_share", "Near-term maturity share of debt", 0, 1, 0.05, pct0, "What share of total liabilities is coming due soon and needs refinancing."],
      ["refinancing_spread_bps", "Refinancing stress spread", -300, 1000, 25, (v) => (v > 0 ? "+" : "") + fmt(v, 0) + " bps", "0 = no shock. Extra cost of rolling over near-term debt in stressed conditions — rollover risk, distinct from floating-rate repricing."],
    ],
    arrears: [
      ["arrears_pct_of_revenue", "Government arrears (% of revenue a year)", -0.3, 0.3, 0.01, pctSig, CFG.GLOSSARY["Government arrears"] + " Negative means the government clears existing arrears. 0 = no shock."],
    ],
  };
  pages.shock = {
    build(root) {
      const st = S.sh, H = (this.H = {});
      if (!S.names.includes(st.soe)) st.soe = S.names[0];
      const yrs = uniq(S.en.filter((r) => r.Entity === st.soe).map((r) => r.Year)).sort((a, b) => a - b);
      if (!yrs.includes(st.year)) st.year = last(yrs);
      const base = S.en.find((r) => r.Entity === st.soe && r.Year === st.year);
      const ekey = st.soe + "|" + st.year;
      if (st.expoFor !== ekey) { st.expoSrc = E.soeExposures(base); st.expo = expoFor(base); st.expoFor = ekey; }
      const [sig, fallback] = volFor(st.soe, base.Sector);
      const panel = card("Scenario", null, null, "top");
      const get = (k) => (k in st.mags ? st.mags[k] : st.expo[k]);
      const set = (k, v) => { if (k in st.mags) st.mags[k] = v; else st.expo[k] = v; };
      H.fuelWarn = el("div");
      const sl = ([k, label, mn, mx, step, f, help]) => {
        const src = st.expoSrc[k];
        return fSlider(label, { min: mn, max: mx, step, value: get(k), fmt: f, info: help, id: "sh-" + k, help: src ? `Starts at ${f(src[0])} — ${src[1]}` : null }, (v) => { set(k, v); this.fuelCheck(); this.schedule(); });
      };
      const tabs = [["fuel", "Fuel"], ["fx", "FX"], ["rates", "Rates & revenue"], ["arrears", "Arrears & horizon"]];
      const sub = el("div", { class: "subtabs", role: "tablist" });
      const pbox = el("div", { class: "fields" });
      const drawTab = () => {
        pbox.replaceChildren(...SLIDERS[st.ptab].map(sl));
        if (st.ptab === "fuel") pbox.append(H.fuelWarn);
        if (st.ptab === "arrears") {
          pbox.append(
            fSlider("Projection horizon (years)", { min: 1, max: 7, step: 1, value: st.H, fmt: (v) => String(v), info: "How many years into the future to project.", id: "sh-H" }, (v) => { st.H = v; st.D = Math.min(st.D, v); const d = $("#sh-D"); if (d) { d.max = v; d.value = st.D; d.dispatchEvent(new Event("input")); } this.schedule(); }),
            fSlider("Shock active duration (years)", { min: 1, max: st.H, step: 1, value: Math.min(st.D, st.H), fmt: (v) => String(v), info: "How many of those years the shock is applied. After that it stops, but its effects on debt and equity carry forward.", id: "sh-D" }, (v) => { st.D = v; this.schedule(); }));
        }
        sub.querySelectorAll("button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.t === st.ptab)));
      };
      tabs.forEach(([k, l]) => sub.appendChild(el("button", { role: "tab", type: "button", "data-t": k, onclick: () => { st.ptab = k; drawTab(); } }, l)));
      drawTab();
      const preset = (mags, D) => { Object.assign(st.mags, mags); if (D) st.D = Math.min(D, st.H); rebuild(); };
      panel.body.append(el("div", { class: "fields" },
        el("div", { class: "fields two" },
          fSelect("SOE", S.names, st.soe, (v) => { st.soe = v; st.year = null; rebuild(); }),
          fSelect("Base year", yrs, st.year, (v) => { st.year = v; rebuild(); }, { num: true })),
        el("p", { class: "note", style: "margin:0" }, el("b", {}, "Bottom-up exposures. "), `The exposure sliders start from this SOE's own data where the file carries them (fuel cost, FX debt, short-term debt, exposure shares), otherwise from sector or generic defaults — the line under each slider says which. Revenue volatility ${pct(sig, 1)} (${fallback ? "sector default — fewer than 3 years of data" : "from this SOE's own history"}).`),
        el("div", { class: "presets" }, el("button", { class: "btn", type: "button", onclick: () => preset(ZERO_MAG) }, "No shock (baseline)"),
          el("button", { class: "btn", type: "button", onclick: () => preset(STD_MAG, CFG.DEFAULT_SHOCK_PARAMS.shock_duration_years) }, "Standard stress (DSA/DSF)"),
          el("button", { class: "btn-ghost", type: "button", onclick: () => { st.expoFor = null; rebuild(); } }, "Reset exposures to this SOE's data"))),
        el("hr", { class: "divider" }), sub, pbox, el("hr", { class: "divider" }),
        el("div", { class: "fields" },
          fSlider("LGD", { min: CFG.LGD_SLIDER_MIN, max: CFG.LGD_SLIDER_MAX, step: 1, value: st.lgd, fmt: (v) => v + "%", info: CFG.GLOSSARY.LGD }, (v) => { st.lgd = v; this.schedule(); }),
          fSlider("EAD: share of total liabilities", { min: 0.5, max: 1, step: 0.1, value: st.ead, fmt: pct0, info: "Exposure at default as a share of the projected total liabilities. 60% and 80% are the sensitivity cases; 100% counts every liability." }, (v) => { st.ead = v; this.schedule(); }),
          gdpField(() => this.schedule()),
          fSlider("Nominal GDP growth", { min: -0.05, max: 0.15, step: 0.005, value: S.growth, fmt: (v) => fmt(v * 100, 1) + "%/yr" }, (v) => { S.growth = v; this.schedule(); })));
      H.view = seg([["single", "Single scenario"], ["mc", "Distribution (Monte Carlo)"], ["all", "All SOEs"]], st.view, (v) => { st.view = v; rebuild(); });
      H.desc = el("p", { class: "note", style: "margin:8px 0 0" });
      H.out = el("div", { class: "stack", style: "margin-top:16px" });
      root.replaceChildren(
        pageHead("DYNAMIC SIMULATION", "Shock Scenarios & Fiscal Risk", "Shocks hit balance-sheet and income-statement lines directly and compound over a multi-year horizon. Run the no-shock baseline first, then a shock; every stressed path is compared with the SOE's own no-shock path."),
        el("div", { class: "grid" }, el("div", { class: "s4 sticky-panel" }, panel.root), el("div", { class: "s8" }, el("div", { class: "card" }, el("div", { class: "row-ctl" }, el("div", { class: "fld" }, el("span", { class: "lbl" }, "View"), H.view)), H.desc), H.out)),
        el("div", { class: "foot" },
          el("div", {}, el("b", {}, "Simplifications. "), "Tax expense and current liabilities are held flat; net income carries the reported figure plus the shock's effect on EBIT and interest; losses are assumed debt-financed; operating expense and revenue are held at base-year values."),
          el("div", {}, el("b", {}, "Fuel cost split. "), "A fuel-cost change is shared between customers (tariff pass-through, Case B), the government (subsidy share, Case C — a direct budget outlay) and the SOE (the rest, Case A). With both at zero the SOE absorbs it all."),
          el("div", {}, el("b", {}, "Monte Carlo. "), "Fuel and FX shock magnitudes are always drawn from a correlated normal distribution around their sliders; the interest-rate and revenue shocks are drawn too when their standard deviation is above zero, with the correlations you set. Every other parameter stays at its slider value. The seed is fixed, so identical settings reproduce identical results.")));
      this.fuelCheck();
      if (st.view === "single") this.buildSingle(); else if (st.view === "mc") this.buildMC(); else this.buildAll();
    },
    schedule() { clearTimeout(this._t); this._t = setTimeout(() => this.render(), S.sh.view === "mc" ? 160 : 30); },
    fuelCheck() {
      const e = S.sh.expo, over = e.tariff_passthrough + e.fuel_subsidy_share > 1 + 1e-9;
      put(this.H.fuelWarn, over ? el("div", { class: "alert-box warn" }, `Pass-through (${pct0(e.tariff_passthrough)}) and subsidy (${pct0(e.fuel_subsidy_share)}) add up to more than 100% of the fuel-cost change. The SOE's share is floored at zero, and the government still pays its full subsidy share.`) : null);
    },
    base() { const st = S.sh; return S.en.find((r) => r.Entity === st.soe && r.Year === st.year); },
    params(mags) { const st = S.sh, b = this.base(); return paramsFor(b, mags || st.mags, st.expo, st.D, st.H); },
    buildSingle() {
      const H = this.H;
      H.tiles = el("div", { class: "grid4 sm" });
      H.subsidy = el("div");
      H.z = card("Z-EM trajectory", "Stressed path against the no-shock path for the same SOE"); H.z.body.append(legendRow([legendItem(LG.str, "Stressed"), legendItem(LG.base, "No shock"), legendItem(LG.act, "Shock active"), legendItem(LG.grey, "Grey zone"), legendItem(LG.dist, "Distress")]), el("div", { class: "chart" }));
      H.e = card("Expected fiscal cost path", null); H.e.body.append(legendRow([legendItem(LG.str, "Stressed"), legendItem(LG.base, "No shock")]), el("div", { class: "chart" }));
      H.imp = card("KPI impact (base → final year)", "Change in each Z-EM component; weighted = change × coefficient"); H.tor = card("Tornado — driver of Z-EM change", "Weighted contribution to the change in Z″, base year to final year"); H.tor.body.append(el("div", { class: "chart" }));
      H.proj = card("Full projection", null);
      H.out.replaceChildren(H.subsidy, H.tiles, el("div", { class: "grid" }, el("div", { class: "s6" }, H.z.root), el("div", { class: "s6" }, H.e.root)), el("div", { class: "grid" }, el("div", { class: "s5" }, H.tor.root), el("div", { class: "s7" }, H.imp.root)), H.proj.root);
    },
    buildMC() {
      const st = S.sh.mc, H = this.H;
      const LBL = { fuel: "Fuel", fx: "FX", rate: "Rate", revenue: "Revenue" };
      const corrBox = el("div", { class: "fields three" });
      const drawCorr = () => {
        const names = ["fuel", "fx"].concat(st.rsd > 0 ? ["rate"] : [], st.vsd > 0 ? ["revenue"] : []);
        const pairs = [];
        names.forEach((a, i) => names.slice(i + 1).forEach((b) => pairs.push([a, b])));
        corrBox.replaceChildren(...pairs.map(([a, b]) => fSlider(`${LBL[a]}–${LBL[b]} correlation`, { min: -1, max: 1, step: 0.05, value: st.corr[`${a}|${b}`] ?? 0, fmt: (v) => fmt(v, 2),
          info: a === "fuel" && b === "fx" ? "Positive correlation reflects fuel and FX shocks often moving together." : "How the two shocks move together across draws. The set of correlations has to be internally consistent; the page says so if it is not." }, (v) => { st.corr[`${a}|${b}`] = v; this.schedule(); })));
      };
      const sdSlider = (label, key, o, info) => fSlider(label, Object.assign({ value: st[key], info }, o), (v) => { const was = st[key] > 0; st[key] = v; if (was !== v > 0) drawCorr(); this.schedule(); });
      const set = el("div", { class: "fields two" },
        fSlider("Simulations", { min: 100, max: 5000, step: 100, value: st.n, fmt: (v) => v.toLocaleString("en-US"), info: "How many random shock draws to run." }, (v) => { st.n = v; this.schedule(); }),
        el("div"),
        sdSlider("Fuel shock std. dev.", "fsd", { min: 0.01, max: 0.3, step: 0.01, fmt: pct0 }, "Spread of the fuel shock across simulations, centred on the Fuel slider."),
        sdSlider("FX shock std. dev.", "xsd", { min: 0.01, max: 0.3, step: 0.01, fmt: pct0 }, "Spread of the FX shock across simulations, centred on the FX slider."),
        sdSlider("Interest-rate shock std. dev.", "rsd", { min: 0, max: 500, step: 25, fmt: (v) => (v ? fmt(v, 0) + " bps" : "off") }, "Spread of the interest-rate shock, centred on the rate slider. 0 = not drawn (held at the slider value)."),
        sdSlider("Revenue shock std. dev.", "vsd", { min: 0, max: 2, step: 0.1, fmt: (v) => (v ? fmt(v, 1) + " s.d." : "off") }, "Spread of the revenue shock in standard deviations of this SOE's own revenue growth, centred on the revenue slider. 0 = not drawn."));
      drawCorr();
      H.mcnote = el("p", { class: "note" });
      H.mcerr = el("div");
      const c = card("Monte Carlo settings", null, null); c.body.append(set, el("div", { class: "lbl", style: "margin:12px 0 6px" }, "Correlations between the drawn shocks"), corrBox, H.mcnote, H.mcerr);
      H.tiles = el("div", { class: "grid4 sm" });
      H.zh = card("Z-EM distribution (final year)"); H.zh.body.append(legendRow([legendItem(LG.thrC, `Distress (${CFG.Z_DISTRESS_CUTOFF})`), legendItem(LG.thrW, `Safe (${CFG.Z_SAFE_CUTOFF})`)]), el("div", { class: "chart" }));
      H.zd = card("Zone distribution across simulations"); H.zd.body.append(el("div"));
      H.eh = card("Expected fiscal cost distribution (final year)"); H.eh.body.append(el("div", { class: "chart" }));
      H.fan = card("Expected fiscal cost — percentile path"); H.fan.body.append(legendRow([legendItem(LG.med, "Median"), legendItem(LG.inner, "25th–75th"), legendItem(LG.outer, "5th–95th")]), el("div", { class: "chart" }));
      H.pt = card("Percentile summary (final year)");
      H.mcres = el("div", { class: "stack" }, H.tiles, el("div", { class: "grid" }, el("div", { class: "s7" }, H.zh.root), el("div", { class: "s5" }, H.zd.root)), H.eh.root, H.fan.root, H.pt.root);
      H.out.replaceChildren(c.root, H.mcres);
    },
    buildAll() {
      const H = this.H;
      H.all = card("All SOEs under these shocks", "Latest year of each SOE as the base year · sorted by the rise in final-year EFC against the no-shock path · select a row to open it in Single scenario",
        seg([["own", "Each SOE's own exposures"], ["panel", "Panel exposures for all"]], S.sh.allExpo, (v) => { S.sh.allExpo = v; this.render(); }, "Exposures"));
      H.out.replaceChildren(H.all.root);
    },
    render() {
      const st = S.sh, H = this.H, b = this.base();
      if (!b) return;
      const p = this.params(), gs = S.gdp ? E.gdpPath(S.gdp, S.growth, st.H) : null;
      H.desc.replaceChildren(el("b", {}, "Active shocks: "), E.describeShocks(p) + (st.view === "all" ? "" : ` · ${st.soe}, base year ${st.year}`));
      if (st.view === "single") this.renderSingle(b, p, gs);
      else if (st.view === "mc") this.renderMC(b, p, gs);
      else this.renderAll(gs);
    },
    renderSingle(b, p, gs) {
      const st = S.sh, H = this.H;
      const path = E.costPath(E.runScenario(b, p, st.H), st.lgd, gs, st.ead), base = E.costPath(E.runScenario(b, this.params(ZERO_MAG), st.H), st.lgd, gs, st.ead);
      const f = last(path), f0 = path[0], fb = last(base), mig = f0.Zone !== f.Zone;
      const subT = sum(path.map((r) => r["Direct Fuel Subsidy"])), hasSub = !!p.fuel_subsidy_share;
      put(H.subsidy, subT ? el("div", { class: "alert-box warn", style: "margin-bottom:16px" }, el("span", {}, el("b", {}, `Direct fuel subsidy: ${money(subT, true)} over ${pl(Math.min(st.D, st.H), "year")}`),
        subT > 0 ? ` — a budget outlay on top of the expected fiscal cost, because the government absorbs ${pct0(p.fuel_subsidy_share)} of the fuel-cost change (Case C).` : ` — negative: cheaper fuel lowers the ${pct0(p.fuel_subsidy_share)} share the government covers, a budget saving.`,
        gs ? ` That is ${pctS(subT / gs[1])} of year-1 GDP.` : "")) : null);
      H.tiles.replaceChildren(
        tile(`Z-EM in ${f["Calendar Year"]}`, zk(f.Zone), ZLABEL[zk(f.Zone)], fmt(f.Z_EM, 2), `from ${fmt(f0.Z_EM, 2)}`, `No shock: ${fmt(fb.Z_EM, 2)} · base year ${f0["Calendar Year"]}`),
        tile("Final-year EFC", null, null, money(f.EFC), CUR, `No shock: ${money(fb.EFC)} · ${sgn(fb.EFC ? (f.EFC / fb.EFC - 1) * 100 : NaN, 0)}%`),
        tile("Zone migration", mig ? "watch" : "ok", mig ? "Yes" : "No", mig ? "Yes" : "No", "", `${f0.Zone} → ${f.Zone} by ${f["Calendar Year"]}`),
        tile("Final-year EFC / GDP", null, null, gs ? pctS(f.EFC_GDP) : "—", "", gs ? `GDP projected at ${fmt(S.growth * 100, 1)}%/yr` : "Enter GDP in the panel to populate"));
      const xs = path.map((r) => r["Calendar Year"]);
      const tipRows = (i) => [[fmt(path[i].Z_EM, 2), `stressed · ${path[i].Rating} · ${path[i].Zone}`], [fmt(base[i].Z_EM, 2), `no shock · ${base[i].Rating}`], [money(path[i].EFC), `EFC stressed (no shock ${money(base[i].EFC)})`]];
      lines(H.z.body.lastChild, xs, [{ vals: base.map((r) => r.Z_EM), cls: "ln-base", dot: "prev", skipFirstDot: true, label: "No shock" }, { vals: path.map((r) => r.Z_EM), cls: "ln-str", dot: "now", label: "Stressed" }],
        { zones: true, active: [1, Math.min(st.D, st.H)], xLab: (i) => (i === 0 ? `${xs[i]} base` : String(xs[i])), tip: tipRows, tipTitle: (i) => `${st.soe} · ${xs[i]}`, endLabel: { series: 1, fmt: (v) => fmt(v, 2) } });
      const useG = !!gs, key = useG ? "EFC_GDP" : "EFC";
      H.e.head.querySelector("h3").textContent = useG ? "Expected fiscal cost / GDP — path" : `Expected fiscal cost path${CUR ? " (" + CUR + ")" : ""}`;
      const yF = useG ? (t) => pctS(t) : (t, s) => moneyTick(t, s);
      lines(H.e.body.lastChild, xs, [{ vals: base.map((r) => r[key]), cls: "ln-base", dot: "prev", skipFirstDot: true, label: "No shock" }, { vals: path.map((r) => r[key]), cls: "ln-str", dot: "now", label: "Stressed" }],
        { zeroFloor: true, yFmt: yF, L: 62, xLab: (i) => (i === 0 ? `${xs[i]} base` : String(xs[i])), tipTitle: (i) => `${st.soe} · ${xs[i]}`, tip: (i) => [[useG ? pctS(path[i][key]) : money(path[i][key]), `stressed · PD ${pctAuto(path[i].PD)}`], [useG ? pctS(base[i][key]) : money(base[i][key]), "no shock"]], endLabel: { series: 1, fmt: (v) => (useG ? pctS(v) : money(v)) } });
      const imp = E.kpiImpact(path), impB = E.kpiImpact(base);
      H.imp.body.replaceChildren(simpleTable(["Component", "Base", "Final", "Weighted ΔZ", "vs no shock"],
        imp.map((r, i) => [el("td", { title: r.Component, style: "white-space:nowrap" }, el("b", {}, r.key), " ", el("span", { class: "muted" }, SHORT[r.key])), fmt(r.base, 3), fmt(r.final, 3), sgn(r.weighted, 2), sgn(r.weighted - impB[i].weighted, 2)]), { right: (i) => i >= 1, cls: "compact" }),
        el("p", { class: "note" }, "Weighted ΔZ = (final − base ratio) × coefficient. “vs no shock” measures the same against the no-shock path's final year, which isolates the effect of the shock itself."));
      const tor = imp.slice().sort((a, b2) => Math.abs(b2.weighted) - Math.abs(a.weighted));
      hbars(H.tor.body.firstChild, tor.map((r) => ({ label: r.key, sub: SHORT[r.key], v: r.weighted, cls: "bar" + (r.weighted < 0 ? " neg" : ""), lab: sgn(r.weighted, 2), tipTitle: r.Component, tip: [[sgn(r.weighted, 3), "weighted contribution to ΔZ″"], [`${fmt(r.base, 3)} → ${fmt(r.final, 3)}`, "ratio, base → final"]] })), { L: 120, R: 60, nTicks: 4 });
      const heads = ["Year", "EBIT", "Equity", "Liabilities", "Z-EM", "No shock", "Zone", "Rating", "PD", "EFC", ...(hasSub ? ["Fuel subsidy"] : []), ...(gs ? ["EFC / GDP"] : [])];
      H.proj.body.replaceChildren(simpleTable(heads, path.map((r, i) => [String(r["Calendar Year"]) + (i === 0 ? " base" : ""), money(r.EBIT), money(r.Equity), money(r["Total Liabilities"]), fmt(r.Z_EM, 2), fmt(base[i].Z_EM, 2), el("td", {}, zoneChip(r.Zone)), r.Rating, pctAuto(r.PD), money(r.EFC), ...(hasSub ? [money(r["Direct Fuel Subsidy"])] : []), ...(gs ? [pctS(r.EFC_GDP)] : [])]), { right: (i) => i >= 1 && i !== 6 && i !== 7, cls: "compact" }),
        el("div", { style: "margin-top:10px" }, dataButtons(() => toCSV(["Calendar Year", "EBIT", "Interest Expense", "Retained Earnings", "Equity", "Total Liabilities", "Total Assets", "Current Assets", "X1", "X2", "X3", "X4", "Z_EM", "Z_EM_no_shock", "Zone", "Rating", "PD", "EAD", "EFC", "Direct Fuel Subsidy", "GDP", "EFC_GDP"],
          path.map((r, i) => [r["Calendar Year"], r.EBIT, r["Interest Expense"], r["Retained Earnings"], r.Equity, r["Total Liabilities"], r["Total Assets"], r["Current Assets"], r.X1, r.X2, r.X3, r.X4, r.Z_EM, base[i].Z_EM, r.Zone, r.Rating, r.PD, r.EAD, r.EFC, r["Direct Fuel Subsidy"], r.GDP, r.EFC_GDP])), `scenario_${st.soe}.csv`)));
    },
    renderMC(b, p, gs) {
      const st = S.sh, m = st.mc, H = this.H;
      H.mcnote.textContent = `Draws are centred on the sliders (mean fuel shock ${pctSig(p.fuel_shock_pct)}, mean FX shock ${pctSig(p.fx_shock_pct)}` + (m.rsd > 0 ? `, mean rate shock ${sgn(p.rate_shock_bps, 0)} bps` : "") + (m.vsd > 0 ? `, mean revenue shock ${sgn(p.revenue_shock_std_devs, 2)} s.d.` : "") + "); all other parameters stay at their slider values.";
      let sims;
      try {
        sims = E.monteCarlo(b, p, { n: m.n, fuelSd: m.fsd, fxSd: m.xsd, rho: m.corr["fuel|fx"], rateSd: m.rsd, revSd: m.vsd, correlations: m.corr, H: st.H, lgd: st.lgd, gdp: gs, seed: 42, eadShare: st.ead });
      } catch (e) {
        H.mcerr.replaceChildren(el("div", { class: "alert-box warn", style: "margin-top:10px" }, e.message));
        H.mcres.hidden = true;
        return;
      }
      H.mcerr.replaceChildren(); H.mcres.hidden = false;
      const fin = sims.map((s) => last(s.path));
      const q = (k, x) => E.quantile(fin.map((r) => r[k]), x);
      const p50 = q("EFC", 0.5), p95 = q("EFC", 0.95), dist = fin.filter((r) => r.Zone === "Distress").length / fin.length;
      const gF = gs ? last(gs) : null;
      H.tiles.replaceChildren(
        tile(`Median EFC, year ${st.H}`, null, null, money(p50), CUR, `${m.n.toLocaleString("en-US")} simulations`),
        tile("Fiscal-at-risk (p95)", null, null, money(p95), CUR, "Bad but plausible: 1 in 20 draws is worse"),
        tile("Ending in distress", dist > 0.5 ? "alert" : dist > 0 ? "watch" : "ok", null, pct(dist, 0), "", `of simulations, Z-EM ≤ ${CFG.Z_DISTRESS_CUTOFF} in ${last(fin)["Calendar Year"]}`),
        tile("Fiscal-at-risk / GDP", null, null, gF ? pctS(p95 / gF) : "—", "", gF ? `GDP in ${last(fin)["Calendar Year"]}: ${money(gF)}` : "Enter GDP in the panel"));
      histogram(H.zh.body.lastChild, fin.map((r) => r.Z_EM), { zones: true, vlines: [{ x: CFG.Z_DISTRESS_CUTOFF, cls: "thr-crit" }, { x: CFG.Z_SAFE_CUTOFF, cls: "thr-warn" }] });
      const zc = zoneCounts(fin);
      H.zd.body.firstChild.replaceChildren(el("div", { class: "hero", style: "gap:12px" }, el("div", { class: "hero-value", style: "font-size:40px" }, pct(dist, 0), el("small", {}, "of simulations end in distress")), ...zoneBar(zc, fin.length),
        el("p", { class: "note", style: "margin:0" }, `Median Z″ ${fmt(q("Z_EM", 0.5), 2)}; 5th percentile ${fmt(q("Z_EM", 0.05), 2)}.`)));
      histogram(H.eh.body.firstChild, fin.map((r) => r.EFC), { xFmt: (t, s) => moneyTick(t, s), vlines: [{ x: p95, cls: "thr-crit", label: "95th pct. (fiscal-at-risk)" }, { x: p50, cls: "ref-l", label: "median" }] });
      const key = gs ? "EFC_GDP" : "EFC", pp = E.percentilePath(sims, key), xs = pp.map((r) => r.year);
      H.fan.head.querySelector("h3").textContent = gs ? "Expected fiscal cost / GDP — percentile path" : `Expected fiscal cost — percentile path${CUR ? " (" + CUR + ")" : ""}`;
      const f = gs ? (v) => pctS(v) : (v) => money(v);
      lines(H.fan.body.lastChild, xs, [{ vals: pp.map((r) => r.p50), cls: "ln-med", dot: "now", label: "Median" }],
        { band: [{ lo: pp.map((r) => r.p5), hi: pp.map((r) => r.p95), cls: "band-outer" }, { lo: pp.map((r) => r.p25), hi: pp.map((r) => r.p75), cls: "band-inner" }], zeroFloor: true, L: 62, yFmt: gs ? (t) => pctS(t) : (t, s) => moneyTick(t, s),
          tip: (i) => [[f(pp[i].p95), "95th"], [f(pp[i].p75), "75th"], [f(pp[i].p50), "median"], [f(pp[i].p25), "25th"], [f(pp[i].p5), "5th"]], xLab: (i) => (i === 0 ? `${xs[i]} base` : String(xs[i])) });
      H.pt.body.replaceChildren(simpleTable(["Percentile", "Z-EM", `EFC${CUR ? " (" + CUR + ")" : ""}`, ...(gF ? ["EFC / GDP"] : [])],
        [[0.05, "5th"], [0.25, "25th"], [0.5, "Median"], [0.75, "75th"], [0.95, "95th"]].map(([x, l]) => [l, fmt(q("Z_EM", x), 2), money(q("EFC", x)), ...(gF ? [pctS(q("EFC", x) / gF)] : [])]), { right: (i) => i >= 1 }),
        el("div", { style: "margin-top:10px" }, dataButtons(() => toCSV(["sim", "fuel_shock_pct", "fx_shock_pct", ...(m.rsd > 0 ? ["rate_shock_bps"] : []), ...(m.vsd > 0 ? ["revenue_shock_std_devs"] : []), "Z_EM_final", "Zone_final", "EFC_final"],
          sims.map((s, i) => [i, s.fuel, s.fx, ...(m.rsd > 0 ? [s.draw.rate] : []), ...(m.vsd > 0 ? [s.draw.revenue] : []), last(s.path).Z_EM, last(s.path).Zone, last(s.path).EFC])), `monte_carlo_${st.soe}.csv`)));
    },
    renderAll(gs) {
      const st = S.sh, H = this.H;
      const own = st.allExpo === "own";
      const expoFn = own ? (r) => Object.assign(expoFor(r), { fuel_subsidy_share: st.expo.fuel_subsidy_share }) : () => st.expo;
      const res = stressAll(S.en, st.mags, expoFn, st.D, st.H, st.lgd, S.gdp, S.growth, st.ead).map((x) => Object.assign(x, { de: (last(x.str).EFC || 0) - (last(x.base).EFC || 0), sub: sum(x.str.map((r) => r["Direct Fuel Subsidy"])) })).sort((a, b2) => b2.de - a.de);
      const hasSub = res.some((x) => x.sub);
      const lastY = res.length ? last(res[0].base)["Calendar Year"] : "";
      const t = el("table");
      const heads = ["SOE", "Z″ base", "Z″ no shock", "Z″ stressed", "Zone drop", "EFC no shock", "EFC stressed", "Δ EFC", ...(hasSub ? ["Fuel subsidy"] : []), ...(gs ? ["Δ / GDP"] : [])];
      t.className = "compact";
      t.appendChild(el("thead", {}, el("tr", {}, heads.map((h, i) => el("th", { class: i ? "r" : "" }, h)))));
      const tb = el("tbody");
      let tB = 0, tS = 0;
      res.forEach((x) => {
        const fb = last(x.base), fs = last(x.str); tB += fb.EFC || 0; tS += fs.EFC || 0;
        const tr = el("tr", { class: "pick" + (x.row.Entity === st.soe ? " sel" : ""), tabindex: "0" }, nameCell(x.row.Entity, `${x.row.Sector} · ${x.row.Year}`), el("td", { class: "r" }, fmt(x.row.Z_EM, 2)), el("td", { class: "r" }, fmt(fb.Z_EM, 2)),
          statusCell(zk(fs.Zone), fmt(fs.Z_EM, 2), fs.Rating, "r"), el("td", { class: "r" }, x.drop ? stChip("alert", "Yes") : stChip("none", "No")),
          el("td", { class: "r" }, money(fb.EFC)), el("td", { class: "r" }, money(fs.EFC)), el("td", { class: "r" }, (x.de >= 0 ? "+" : "") + money(x.de)), hasSub ? el("td", { class: "r" }, money(x.sub)) : null, gs ? el("td", { class: "r" }, pctS(x.de / last(gs))) : null);
        const pick = () => { st.soe = x.row.Entity; st.year = x.row.Year; st.view = "single"; rebuild(); };
        tr.addEventListener("click", pick);
        tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
        tb.appendChild(tr);
      });
      t.append(tb, el("tfoot", {}, el("tr", {}, el("td", {}, "Portfolio"), el("td"), el("td"), el("td"), el("td", { class: "r" }, `${res.filter((x) => x.drop).length} of ${res.length}`), el("td", { class: "r" }, money(tB)), el("td", { class: "r" }, money(tS)), el("td", { class: "r" }, (tS - tB >= 0 ? "+" : "") + money(tS - tB)), hasSub ? el("td", { class: "r" }, money(sum(res.map((x) => x.sub)))) : null, gs ? el("td", { class: "r" }, pctS((tS - tB) / last(gs))) : null)));
      H.all.body.replaceChildren(el("div", { class: "tbl-wrap" + (res.length > 15 ? " tall" : "") }, t),
        el("p", { class: "note" }, `Z″ and EFC columns are for the final projection year, ${lastY}. ` + (own
          ? "Each SOE uses its own exposures from the data (sector or generic defaults where the file has none) and its own revenue volatility; the shock sizes, horizon and fuel subsidy share are as set in the panel."
          : `Every SOE uses the exposure values set in the panel for ${st.soe}; revenue volatility is each SOE's own.`) + " Zone drop means the stressed path falls at least one zone below the no-shock path in some projection year."),
        el("div", { style: "margin-top:8px" }, dataButtons(() => toCSV(["Entity", "Sector", "Base year", "Z_EM_base", "Z_EM_no_shock_final", "Z_EM_stressed_final", "Zone_stressed_final", "Zone_drop", "EFC_no_shock_final", "EFC_stressed_final", "EFC_change"],
          res.map((x) => [x.row.Entity, x.row.Sector, x.row.Year, x.row.Z_EM, last(x.base).Z_EM, last(x.str).Z_EM, last(x.str).Zone, x.drop ? "Yes" : "No", last(x.base).EFC, last(x.str).EFC, x.de])), "all_soes_under_shock.csv")));
    },
  };

  /* =====================================================================
     GOVERNMENT SUPPORT (GRE)
     ===================================================================== */
  pages.gre = {
    build(root) {
      const st = S.gre, H = (this.H = {});
      if (!S.names.includes(st.sel)) st.sel = S.names[0];
      const sov = card("Sovereign context", "Set once for the country these SOEs sit in; take the rating from the agency's current list.", null, "top");
      sov.body.append(el("div", { class: "fields" },
        fSelect("Sovereign rating (local currency, long-term)", CFG.RATING_SCALE_ASC.slice().reverse(), st.sov, (v) => { st.sov = v; this.render(); }),
        fSelect("Sovereign outlook", CFG.SOVEREIGN_OUTLOOK_OPTIONS, st.outlook, (v) => { st.outlook = v; this.render(); })),
        el("details", { class: "plain" }, el("summary", {}, "What do Role, Link and the uplift mean?"),
          el("p", { class: "note" }, "A simplified, transparent stand-in for S&P Global Ratings' GRE methodology (25 March 2015) — not a reproduction of its Role–Link matrix or notching tables. Role and Link scores are summed into a likelihood-of-support tier, which sets a maximum notch uplift and a minimum gap below the sovereign."),
          el("p", { class: "note" }, el("b", {}, "Role"), " — how important is a default of this SOE to the government?"),
          simpleTable(["Role", "Criteria"], CFG.ROLE_LEVELS.map((r) => [r, CFG.ROLE_CRITERIA[r]]), { cls: "glossary" }),
          el("p", { class: "note" }, el("b", {}, "Link"), " — how tightly bound is the government to this SOE?"),
          simpleTable(["Link", "Criteria"], CFG.LINK_LEVELS.map((r) => [r, CFG.LINK_CRITERIA[r]]), { cls: "glossary" }),
          simpleTable(["Likelihood tier", "Max uplift (notches)", "Min. gap below sovereign"], CFG.LIKELIHOOD_TIERS_ASC.slice().reverse().map((t) => [t, CFG.LIKELIHOOD_UPLIFT[t].max_notches === null ? "up to sovereign" : String(CFG.LIKELIHOOD_UPLIFT[t].max_notches), CFG.LIKELIHOOD_UPLIFT[t].min_gap_to_sovereign === null ? "—" : String(CFG.LIKELIHOOD_UPLIFT[t].min_gap_to_sovereign)]), { right: (i) => i >= 1 }),
          el("p", { class: "note" }, `Dynamic cap: if an SOE's rating has fallen ${CFG.DYNAMIC_CAP_TRIGGER_NOTCHES}+ notches across its years, or the sovereign outlook is Negative, the tier is capped at ${CFG.DYNAMIC_CAP_TIER}.`)));
      H.tbl = card("Per-SOE assessment", "Set Role and Link for each SOE; select a row to see its rating ladder");
      H.det = card("Rating ladder", null); H.det.body.append(el("div", { class: "chart" }));
      H.res = card("Result", null);
      root.replaceChildren(
        pageHead("GOVERNMENT SUPPORT", "Strategic SOEs & Government-Related Entity Uplift", "How important is this SOE to the government (Role), and how tightly linked (Link)? Together they set a bounded uplift above the SOE's own Z-EM-derived rating, capped by the sovereign's rating and tightened automatically if the SOE's rating is falling fast or the sovereign outlook turns negative."),
        el("div", { class: "grid" }, el("div", { class: "s4 sticky-panel" }, sov.root), el("div", { class: "s8 stack" }, H.tbl.root, el("div", { class: "grid" }, el("div", { class: "s7" }, H.det.root), el("div", { class: "s5" }, H.res.root)))),
        el("div", { class: "foot" }, el("div", {}, el("b", {}, "Simplified proxy, not S&P's methodology. "), "The Role × Link mapping and uplift ranges are editable in config.py. Uplift only raises a rating, never above the tier's ceiling, and is reported for comparison only — it does not feed PD or EFC, which stay on the standalone rating.")));
    },
    render() {
      const st = S.gre, H = this.H;
      const res = S.names.map((n) => E.gre(S.en, n, st.role[n] || CFG.ROLE_LEVELS[0], st.link[n] || CFG.LINK_LEVELS[0], st.sov, st.outlook));
      const t = el("table", { class: "ctl-table" });
      t.appendChild(el("thead", {}, el("tr", {}, ["SOE", "Own rating", "Role", "Link", "Likelihood", "Uplifted", "Notches", "Gap to sovereign"].map((h, i) => el("th", { class: i >= 6 ? "r" : "" }, h)))));
      const tb = el("tbody");
      res.forEach((g) => {
        const sector = (S.en.find((r) => r.Entity === g.entity) || {}).Sector || "";
        const sel = (opts, val, key) => { const s = el("select", { "aria-label": `${key} for ${g.entity}` }); opts.forEach((o) => s.appendChild(el("option", { value: o, selected: o === val ? true : null }, o))); s.addEventListener("click", (e) => e.stopPropagation()); s.addEventListener("change", () => { st[key][g.entity] = s.value; st.sel = g.entity; this.render(); }); return s; };
        const tr = el("tr", { class: "pick" + (g.entity === st.sel ? " sel" : ""), tabindex: "0" }, nameCell(g.entity, sector), el("td", {}, g.sacp),
          el("td", {}, sel(CFG.ROLE_LEVELS, g.role, "role")), el("td", {}, sel(CFG.LINK_LEVELS, g.link, "link")),
          el("td", {}, g.capped, g.capApplied && g.capped !== g.tier ? el("span", { class: "muted" }, " (capped)") : null), el("td", {}, el("b", {}, g.uplifted)),
          el("td", { class: "r" }, "+" + g.notches), el("td", { class: "r" }, g.gap === null ? "—" : String(g.gap)));
        const pick = () => { st.sel = g.entity; this.render(); };
        tr.addEventListener("click", pick);
        tr.addEventListener("keydown", (e) => { if (e.target === tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); pick(); } });
        tb.appendChild(tr);
      });
      t.appendChild(tb);
      H.tbl.body.replaceChildren(el("div", { class: "tbl-wrap" }, t), el("div", { style: "margin-top:10px" }, dataButtons(() => toCSV(["Entity", "Own rating", "Role", "Link", "Likelihood tier", "Dynamic cap applied", "Uplifted rating", "Notches gained", "Gap to sovereign"], res.map((g) => [g.entity, g.sacp, g.role, g.link, g.capped, g.capApplied ? "Yes" : "No", g.uplifted, g.notches, g.gap])), "gre_uplift_summary.csv")));
      const g = res.find((x) => x.entity === st.sel) || res[0];
      H.det.head.querySelector("h3").textContent = `Rating ladder · ${g.entity}`;
      ladder(H.det.body.firstChild, g);
      const words = g.sIdx === null ? "No standalone rating could be assigned." :
        `${g.entity} is ${g.sacp} on its own; the government's likely backing ${g.notches > 0 ? `lifts it to ${g.uplifted}` : "does not lift it"}; ${g.gap === 0 ? "it is rated level with the sovereign." : `it sits ${g.gap} notch${g.gap === 1 ? "" : "es"} below the sovereign.`}` +
        (g.notches > 0 && g.ceilingIdx !== null && g.uIdx === g.ceilingIdx ? " The ceiling, not the tier's maximum uplift, is binding, so stronger support in the same tier would not help — only a higher-rated sovereign would." : "");
      H.res.body.replaceChildren(el("div", { class: "fields" },
        el("div", { class: "res" }, el("div", { class: "res-h" }, "Likelihood of support"), el("div", { class: "res-z" }, el("b", { style: "font-size:20px" }, g.capped)), el("div", { class: "res-line" }, g.capApplied && g.capped !== g.tier ? `Capped from ${g.tier} by the dynamic trigger` : "From Role × Link")),
        el("div", { class: "res stress" }, el("div", { class: "res-h" }, "Uplifted rating"), el("div", { class: "res-z" }, el("b", {}, `${g.sacp} → ${g.uplifted}`)), el("div", { class: "res-line" }, `+${g.notches} notch${g.notches === 1 ? "" : "es"} · gap to sovereign ${g.gap ?? "—"}`)),
        g.capApplied ? el("div", { class: "alert-box warn" }, `Dynamic cap applies — ${g.triggers.join(", and ")}. Tier capped at ${CFG.DYNAMIC_CAP_TIER} regardless of Role and Link.`) : null,
        summaryBox(words, "In plain words")));
    },
  };
  function ladder(box, g) {
    const scale = CFG.RATING_SCALE_ASC, W = widthOf(box);
    const idxs = [g.sIdx, g.uIdx, g.vIdx, g.ceilingIdx].filter((v) => v !== null && v !== undefined);
    if (!idxs.length) { box.replaceChildren(el("p", { class: "note" }, "No rating to show.")); return; }
    const top = Math.min(scale.length - 1, Math.max(...idxs) + 1), bot = Math.max(0, Math.min(...idxs) - 2);
    const rowH = 26, T = 6, H = T + (top - bot + 1) * rowH + 6, L = 64, cw = 34, lx = L + cw + 16;
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
    const yOf = (i) => T + (top - i) * rowH;
    for (let i = top; i >= bot; i--) {
      const y = yOf(i);
      const inGap = g.vIdx !== null && g.uIdx !== null && i > g.uIdx && i <= g.vIdx;
      svgEl("rect", { x: L, y: y + 1, width: cw, height: rowH - 2, class: "lad-cell" + (inGap ? " span" : "") }, svg);
      txt(svg, L - 10, y + rowH / 2, scale[i], "t-ink2 num", "end", 12, 600);
      const tags = [];
      if (i === g.vIdx) tags.push("Sovereign");
      if (i === g.ceilingIdx) tags.push("Ceiling");
      if (i === g.uIdx && g.uIdx !== g.sIdx) tags.push("Uplifted");
      if (i === g.sIdx) tags.push(g.uIdx === g.sIdx ? "Standalone = Uplifted" : "Standalone");
      if (tags.length) txt(svg, lx, y + rowH / 2, tags.join(" = ").replace("Standalone = Uplifted = ", "Standalone = Uplifted = "), "t-head", "start", 12.5, 700);
    }
    if (g.uIdx !== null && g.sIdx !== null && g.uIdx > g.sIdx) {
      const x = L + cw / 2;
      svgEl("path", { d: `M${x},${yOf(g.sIdx) + rowH / 2 - 4}V${yOf(g.uIdx) + rowH / 2 + 6}`, class: "lad-arrow" }, svg);
      svgEl("path", { d: `M${x - 5},${yOf(g.uIdx) + rowH / 2 + 11}L${x},${yOf(g.uIdx) + rowH / 2 + 4}L${x + 5},${yOf(g.uIdx) + rowH / 2 + 11}`, class: "lad-arrow" }, svg);
    }
    if (g.gap && g.vIdx !== null && g.uIdx !== null && W > 360) {
      const y0 = yOf(g.vIdx) + 3, y1 = yOf(g.uIdx + 1) + rowH - 3, gx = W - 16;
      svgEl("path", { d: `M${gx - 6},${y0}H${gx}V${y1}H${gx - 6}`, class: "lad-arrow", style: "stroke:var(--muted);stroke-width:1.5" }, svg);
      txt(svg, gx - 10, (y0 + y1) / 2, `gap to sovereign = ${g.gap}`, "t-muted", "end", 11.5, 600);
    }
    box.replaceChildren(svg);
  }

  /* =====================================================================
     EARLY WARNING
     ===================================================================== */
  const RULE_BY = Object.fromEntries(CFG.TRIGGER_RULES.map((r) => [r.id, r]));
  /** which trigger rules each SOE fires (latest year) — Early Warning and the Report's policy section */
  function evalTriggers(rows, stress) {
    const hits = Object.fromEntries(CFG.TRIGGER_RULES.map((r) => [r.id, []])), by = {}, lvl = { alert: 0, watch: 1, ok: 2 };
    rows.forEach((r) => {
      const f = [];
      if (r.Zone === "Distress") f.push("distress");
      if (r.Equity <= 0) f.push("neg_equity");
      if ((ok(r.debt_to_ebitda) && r.debt_to_ebitda > SPEC.debt_to_ebitda.red_cut) || r.EBITDA <= 0) f.push("debt_ebitda");
      if (stress[r.Entity] && stress[r.Entity].drop) f.push("stress_drop");
      if (r.Zone === "Grey") f.push("grey");
      const nc = E.notchChange(S.en, r.Entity)[2];
      if (nc !== null && nc <= -CFG.DYNAMIC_CAP_TRIGGER_NOTCHES) f.push("rating_fall");
      if (ok(r.grants_to_revenue) && r.grants_to_revenue > SPEC.grants_to_revenue.red_cut) f.push("grant_dependency");
      if (!f.length && r.Zone === "Safe") f.push("routine");
      f.forEach((id) => hits[id] && hits[id].push(r.Entity));
      const lv = f.map((id) => (RULE_BY[id] || {}).level).filter(Boolean);
      by[r.Entity] = { level: lv.sort((a, b) => lvl[a] - lvl[b])[0] || "ok", rules: f };
    });
    return { hits, by };
  }
  function signalBoard(rows, by) {
    const board = el("div", { class: "zboard" });
    ["alert", "watch", "ok"].forEach((k) => {
      const list = rows.filter((r) => by[r.Entity].level === k);
      const cards = el("div", { class: "zcards" }, list.map((r) => el("div", { class: "ctry" }, el("span", {}, el("span", { class: "nm" }, r.Entity), el("span", { class: "zs" }, by[r.Entity].rules.map((id) => RULE_BY[id].short).join(" · "))), el("span", { class: "zv" }, fmt(r.Z_EM, 2)))));
      board.appendChild(el("div", { class: "zcol " + k }, el("h4", {}, el("span", {}, el("i", { "aria-hidden": "true" }, GLYPH[k] + " "), STLABEL[k]), el("span", { class: "cnt" }, pl(list.length, "SOE"))), list.length ? cards : el("div", { class: "empty" }, "None")));
    });
    return board;
  }
  pages.warning = {
    build(root) {
      const H = (this.H = {});
      H.rules = card(null); H.board = card("Signal board", "Each SOE sits under the most severe rule it triggers, with every rule it triggers listed");
      H.tl = card("Score history", "Z″, rating and PD by year, then the standard-stress projection");
      root.replaceChildren(
        pageHead("EARLY WARNING", "Trigger rules", `Example rules that link SOE financial health to pre-agreed fiscal responses, evaluated on the latest year of each SOE shown. The stress rule uses the standard stress (DSA/DSF convention) over ${CFG.MC_HORIZON_YEARS} years.`),
        el("div", { class: "grid" }, el("div", { class: "s12" }, H.rules.root), el("div", { class: "s7" }, H.board.root), el("div", { class: "s5" }, H.tl.root)),
        el("div", { class: "foot" }, el("div", {}, "Rules and actions are illustrative and live in config.TRIGGER_RULES. KPI cutoffs are illustrative.")));
    },
    render() {
      const H = this.H, rows = latestOf(F()).sort((a, b) => b.Z_EM - a.Z_EM);
      const stress = Object.fromEntries(standardStress(F()).map((x) => [x.row.Entity, x]));
      const { hits, by } = evalTriggers(rows, stress);
      H.rules.body.replaceChildren(simpleTable(["Signal", "Condition", "Pre-agreed action (example)", "SOEs"],
        CFG.TRIGGER_RULES.map((r) => [el("td", {}, stChip(r.level)), r.condition, r.action, el("td", {}, el("div", { class: "soe-list" }, hits[r.id].length ? hits[r.id].map((n) => el("span", {}, n)) : el("span", { style: "background:transparent;border-color:transparent;color:var(--muted)" }, "None")))])));
      H.rules.body.querySelector("table").id = "rulesTable";
      H.board.body.replaceChildren(signalBoard(rows, by));
      const names = rows.map((r) => r.Entity);
      if (!names.includes(S.ew.tl)) S.ew.tl = (rows.map((r) => [r.Entity, E.notchChange(S.en, r.Entity)[2] ?? 0]).sort((a, b) => a[1] - b[1])[0] || [])[0];
      const sel = fSelect(null, names, S.ew.tl, (v) => { S.ew.tl = v; this.render(); });
      const hist = S.en.filter((r) => r.Entity === S.ew.tl).sort((a, b) => a.Year - b.Year);
      const ol = el("ol", { class: "tl" }, hist.map((h) => el("li", { class: h.Zone === "Distress" ? "hot" : "" }, el("span", { class: "when" }, String(h.Year)), el("span", { class: "rail" }),
        el("div", { class: "what" }, "Z″ ", el("b", {}, fmt(h.Z_EM, 2)), ` · ${h.Rating} · PD ${pctAuto(E.pdByRating(h.Rating))}`, zoneChip(h.Zone)))));
      const x = stress[S.ew.tl];
      if (x) { const r = last(x.str), b = last(x.base); ol.appendChild(el("li", { class: "proj" }, el("span", { class: "when" }, `${r["Calendar Year"]} stress`), el("span", { class: "rail" }), el("div", { class: "what" }, "Z″ ", el("b", {}, fmt(r.Z_EM, 2)), ` · ${r.Rating} under standard stress (no shock ${fmt(b.Z_EM, 2)}, ${b.Rating})`, zoneChip(r.Zone)))); }
      H.tl.body.replaceChildren(el("div", { class: "row-ctl", style: "margin-bottom:10px" }, el("span", { class: "chips-label" }, "SOE"), sel), ol);
    },
  };

  /* =====================================================================
     REPORT — five sections, regenerated from the data on screen
     ===================================================================== */
  function dumbbell(box, items) {
    const W = widthOf(box), narrow = W < 520, L = narrow ? 84 : 130, R = 16, T = 20, rowH = 32;
    const vals = items.flatMap((s) => [s.a, s.b]).filter(ok);
    const sc = nice(Math.min(0, ...vals), Math.max(CFG.Z_SAFE_CUTOFF + 0.4, ...vals), W < 420 ? 4 : 5);
    const x = lin(sc.lo, sc.hi, L, W - R);
    const H = T + items.length * rowH + 26, pb = T + items.length * rowH;
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
    shadeZones(svg, sc, x, true, T, pb);
    for (const t of sc.ticks) { svgEl("line", { x1: x(t), x2: x(t), y1: T, y2: pb, class: t === 0 ? "zero-l" : "grid-l" }, svg); txt(svg, x(t), pb + 14, tickLab(t, sc.step), "t-muted num", "middle", 11); }
    items.forEach((s, i) => {
      const cy = T + i * rowH + rowH / 2, row = svgEl("g", { class: "row" }, svg);
      txt(row, 0, cy, clip(s.name, narrow ? 11 : 18), "t-head", "start", 12, 700);
      if (ok(s.a) && ok(s.b)) {
        svgEl("line", { x1: x(s.a), x2: x(s.b), y1: cy, y2: cy, class: "conn" }, row);
        if (s.ay !== s.by) svgEl("circle", { cx: x(s.a), cy, r: 4.5, class: "dot-prev" }, row);
        svgEl("circle", { cx: x(s.b), cy, r: 5, class: "dot-now" }, row);
        const right = s.b >= s.a, lx = x(s.b) + (right ? 9 : -9);
        if ((!right && lx - L < 34) || (right && lx > W - R - 30)) txt(row, x(s.b), cy - 12, fmt(s.b, 1), "t-ink num", "middle", 11.5, 600);
        else txt(row, lx, cy, fmt(s.b, 1), "t-ink num", right ? "start" : "end", 11.5, 600);
      }
      const hit = svgEl("rect", { x: 0, y: cy - rowH / 2, width: W, height: rowH, class: "hit", tabindex: 0, "aria-label": `${s.name} from ${fmt(s.a, 2)} to ${fmt(s.b, 2)}` }, row);
      bindTip(hit, `${s.name} · ${s.sector}`, [[fmt(s.b, 2), `Z″ ${s.by} · ${s.br}`], [fmt(s.a, 2), `Z″ ${s.ay} · ${s.ar}`], [sgn(s.b - s.a, 2), "change"]]);
    });
    box.replaceChildren(svg);
  }
  const CHANNELS = () => [["combined", "Combined (all channels)", STD_MAG], ...Object.entries(CFG.REPORT_STRESS_CHANNELS).map(([k, [label, mag]]) => [k, label, Object.assign({}, ZERO_MAG, { [mag]: STD_MAG[mag] })])];
  const magText = (mag, v) => (mag === "rate_shock_bps" || mag === "refinancing_spread_bps" ? `${sgn(v, 0)} bps` : mag === "revenue_shock_std_devs" ? `${sgn(v, 1)} s.d.` : mag === "arrears_pct_of_revenue" ? `${fmt(v * 100, 0)}% of revenue a year` : `${sgn(v * 100, 0)}%`);
  function caveats() {
    const c = CFG.ZEM_COEFFICIENTS, st = S.efc;
    const items = [
      `Z″ = ${c.X1}·X1 + ${c.X2}·X2 + ${c.X3}·X3 + ${c.X4}·X4, with no constant (Eidelman convention); zone cutoffs ${CFG.Z_DISTRESS_CUTOFF} and ${CFG.Z_SAFE_CUTOFF} and the 20-band rating table are calibrated to the same constant-free score.`,
      "Ratings are a mechanical mapping of Z″ on a standalone basis, not agency ratings. PD is the one-year PD of each SOE's rating band from the cohort table (a placeholder pending probit-estimated probabilities).",
      `EFC = PD × EAD × LGD. EAD is ${st.basis === "guaranteed_debt" ? `reported government-guaranteed debt where available, otherwise ${pct0(st.ead)} of total liabilities` : `${pct0(st.ead)} of total liabilities (a proxy; 60% and 80% are the sensitivity cases)`}. LGD is ${fmt(st.lgd, 0)}%${st.mode === "per" ? " unless set per SOE" : " for every SOE"}; the GEMs sector references take the lender recovery rate as government LGD, a working assumption.`,
      "For SOEs with large government transfers, the unadjusted Z″ is more likely to overstate than understate health. Read it with the fiscal-dependency KPIs.",
      `Stress test: shocks act on statement lines through each SOE's own exposures (sector or generic defaults where the data carry none) and roll forward over ${CFG.MC_HORIZON_YEARS} years; each SOE is compared with its own no-shock path. Tax and current liabilities are held flat, losses are debt-financed, and net income carries the reported figure plus the shock effect.`,
      "KPI cutoffs, EFC/GDP bands and trigger rules are illustrative starting points, not calibrated to a country sample. Suppressed ratios (negative equity or EBITDA) count as alerts.",
    ];
    if (S.gdp) items.push(`GDP entered by the user (${money(S.gdp, true)}) and projected forward at ${fmt(S.growth * 100, 1)}% a year for the stress-test EFC/GDP path.`);
    if (S.example) items.push(`The data are ${S.label.toLowerCase().startsWith("illustrative") || S.label.toLowerCase().startsWith("built-in") ? "the tool's invented example portfolio" : "example data"}, not real SOEs.`);
    return items;
  }
  pages.report = {
    build(root) {
      const H = (this.H = {});
      const SECS = [["exec", "Executive summary"], ["perf", "Financial performance"], ["risk", "Distress and fiscal risk"], ["stress", "Stress tests"], ["policy", "Policy implications"]];
      const printBtn = canDownload ? el("button", { class: "btn primary no-print", type: "button", onclick: () => window.print() }, "Print / save as PDF") : null;
      const toc = el("nav", { class: "rep-toc no-print", "aria-label": "Report sections" }, SECS.map(([id, t], i) => el("a", { href: "#view-report", onclick: (e) => { e.preventDefault(); const n = document.getElementById("rep-" + id); if (n) n.scrollIntoView({ behavior: "smooth", block: "start" }); } }, el("b", { class: "num" }, String(i + 1)), t)));
      H.sec = {};
      const secs = SECS.map(([id, title], i) => {
        const lead = el("p", { class: "rep-lead" }), body = el("div", { class: "stack" });
        H.sec[id] = { lead, body };
        return el("section", { class: "rep-sec", id: "rep-" + id, "aria-labelledby": "rep-h-" + id }, el("div", { class: "rep-head" }, el("span", { class: "rep-num num" }, String(i + 1)), el("div", {}, el("h2", { id: "rep-h-" + id }, title), lead)), body);
      });
      H.gen = el("p", { class: "rep-gen" });
      root.replaceChildren(pageHead("AUTOMATED REPORT", M.title || "SOE Fiscal Risk Report",
        "Five sections generated from the data loaded in this page. Every number is recomputed when you load other data or change LGD, EAD or GDP on the Expected Fiscal Cost tab; the text is rule-based, not written by a person.", printBtn), toc, ...secs, H.gen);
    },
    render() {
      const H = this.H, st = S.rep, rows = latestOf(allRows()), n = rows.length;
      const byZ = rows.slice().sort((a, b) => a.Z_EM - b.Z_EM);
      const efcOf = (r) => E.efcRow(r, S.efc.mode === "per" ? S.efc.per[r.Entity] ?? S.efc.lgd : S.efc.lgd, S.efc.ead, S.efc.basis);
      const chan = CHANNELS().map(([key, label, mags]) => {
        const res = standardStress(allRows(), mags);
        const eB = sum(res.map((x) => last(x.base).EFC)), eS = sum(res.map((x) => last(x.str).EFC));
        return { key, label, mags, res, eB, eS, drops: res.filter((x) => x.drop).map((x) => x.row.Entity), by: Object.fromEntries(res.map((x) => [x.row.Entity, x])) };
      });
      const comb = chan[0];
      const { hits, by } = evalTriggers(byZ, comb.by);
      const lastY = CFG.MC_HORIZON_YEARS;
      const moreBtn = () => moreToggle(n, st.all, (v) => { st.all = v; this.render(); });
      const horizonYear = comb.res.length ? last(comb.res[0].str)["Calendar Year"] : "";

      /* 1. executive summary */
      const ex = H.sec.exec;
      ex.lead.textContent = `${S.label} · ${pl(n, "SOE")} in ${pl(S.sectors.length, "sector")} · statements ${S.years[0]}–${last(S.years)} · latest year of each SOE.`;
      const hero = el("div", { class: "card s5 hero" }), tiles = el("div", { class: "s7 tiles" });
      const ov = overviewBlocks(hero, tiles, comb.res);
      const efcRows = rows.map((r) => ({ r, e: efcOf(r).EFC })).sort((a, b) => (b.e || 0) - (a.e || 0));
      const total = sum(efcRows.map((x) => x.e)), top3 = sum(efcRows.slice(0, 3).map((x) => x.e));
      const worstCh = chan.slice(1).map((c) => ({ c, up: c.eB ? c.eS / c.eB - 1 : NaN })).sort((a, b) => (b.up || 0) - (a.up || 0))[0];
      const nAlert = byZ.filter((r) => by[r.Entity].level === "alert").length, nWatch = byZ.filter((r) => by[r.Entity].level === "watch").length;
      const names = (a, k = 5) => (a.length > k ? a.slice(0, k).join(", ") + ` and ${a.length - k} more` : a.join(", "));
      const distressNames = byZ.filter((r) => r.Zone === "Distress").map((r) => r.Entity);
      const msgs = [
        [`${ov.zc.Distress} of ${pl(n, "SOE")} are in the distress zone and ${ov.zc.Grey} in the grey zone`, distressNames.length ? ` (distress: ${names(distressNames)}).` : "."],
        [`Expected fiscal cost is ${money(total, true)}`, (S.gdp ? `, ${pctS(total / S.gdp)} of GDP` : "") + (efcRows[0] && total ? `; ${efcRows[0].r.Entity} alone accounts for ${Math.round((efcRows[0].e / total) * 100)}%` + (n > 3 ? ` and the three largest exposures for ${Math.round((top3 / total) * 100)}%.` : ".") : ".")],
        [`Under the standard stress, ${pl(comb.drops.length, "SOE")} drop at least one zone`, (comb.drops.length ? ` (${names(comb.drops)})` : "") + ` and portfolio EFC ${comb.eB ? (comb.eS >= comb.eB ? "rises " : "falls ") + fmt(Math.abs(comb.eS / comb.eB - 1) * 100, 0) + "%" : "changes"} by ${horizonYear}` + (worstCh && ok(worstCh.up) && worstCh.up > 0 ? `; the costliest single channel is ${/^[A-Z]{2,}$/.test(worstCh.c.label) ? worstCh.c.label : worstCh.c.label.toLowerCase()} (+${fmt(worstCh.up * 100, 0)}%).` : ".")],
        ov.worst && ov.worst.dz < 0 ? [`Fastest deterioration: ${ov.worst.r.Entity}`, `, Z″ ${fmt(ov.worst.f.Z_EM, 2)} in ${ov.worst.f.Year} to ${fmt(ov.worst.r.Z_EM, 2)} in ${ov.worst.r.Year} (${ov.worst.f.Rating} to ${ov.worst.r.Rating}).`] : ["No SOE's Z″ fell", " between its first and latest year."],
        [`${pl(nAlert, "SOE")} trigger at least one alert rule and ${nWatch} are on watch`, " — the pre-agreed actions are in section 5."],
      ];
      const dq = S.rows.filter((r) => /proxy|estimate|unaudit/i.test(`${r["Data Quality Flag"] || ""} ${r["Audit Status"] || ""}`)).length;
      const ph = CFG.PARAMETER_REGISTER.filter((r) => r.status === "placeholder").length;
      msgs.push([`Data and assumptions: `, (dq ? `${dq} of ${S.rows.length} SOE-year rows are flagged as proxy, estimated or unaudited; ` : S.rows.some((r) => r["Data Quality Flag"] || r["Audit Status"]) ? "no rows are flagged as proxy or unaudited; " : "the file carries no provenance flags; ") + `${ph} of ${CFG.PARAMETER_REGISTER.length} model parameters are still placeholders that need a source.`]);
      ex.body.replaceChildren(el("div", { class: "card keymsg" }, el("h3", {}, "Key messages"), el("ul", {}, msgs.map(([b, t]) => el("li", {}, el("b", {}, b), t)))), el("div", { class: "grid" }, hero, tiles));

      /* 2. financial performance */
      const pf = H.sec.perf;
      pf.lead.textContent = "How the portfolio's distress score has moved over time, and the headline ratios of each SOE in its latest year.";
      const blocks = [];
      if (S.years.length > 1) {
        const ys = S.years, med = [], p25 = [], p75 = [], nd = [], cnt = [];
        ys.forEach((y) => { const z = S.en.filter((r) => r.Year === y).map((r) => r.Z_EM).filter(ok); cnt.push(z.length); med.push(E.quantile(z, 0.5)); p25.push(E.quantile(z, 0.25)); p75.push(E.quantile(z, 0.75)); nd.push(S.en.filter((r) => r.Year === y && r.Zone === "Distress").length); });
        const c = card("Portfolio Z″ over time", "Median and middle half (25th–75th percentile) of Z″ across the SOEs reporting each year");
        const box = el("div", { class: "chart" });
        c.body.append(legendRow([legendItem(LG.med, "Median"), legendItem(LG.inner, "25th–75th percentile"), legendItem(LG.grey, "Grey zone"), legendItem(LG.dist, "Distress")]), box);
        blocks.push(c.root);
        this.pending = () => lines(box, ys, [{ vals: med, cls: "ln-med", dot: "now", label: "Median" }], { band: [{ lo: p25, hi: p75, cls: "band-inner" }], zones: true, h: 240, tipTitle: (i) => String(ys[i]), tip: (i) => [[fmt(med[i], 2), "median Z″"], [`${fmt(p25[i], 2)} to ${fmt(p75[i], 2)}`, "middle half"], [`${nd[i]} of ${cnt[i]}`, "SOEs in distress"]], endLabel: { series: 0, fmt: (v) => fmt(v, 2) } });
        const i0 = 0, i1 = ys.length - 1;
        c.body.append(el("p", { class: "note" }, `Median Z″ ${med[i1] >= med[i0] ? "rose" : "fell"} from ${fmt(med[i0], 2)} in ${ys[i0]} to ${fmt(med[i1], 2)} in ${ys[i1]}; SOEs in distress went from ${nd[i0]} of ${cnt[i0]} to ${nd[i1]} of ${cnt[i1]}.` + (uniq(cnt).length > 1 ? " The number of SOEs reporting changes over the period, so part of the movement is composition." : "")));
      } else this.pending = null;
      const avail = E.availableKpis(S.en), keys = CFG.REPORT_HEADLINE_KPIS.filter((k) => avail.includes(k));
      if (keys.length) {
        const sc = scorecard(S.en, avail, keys, st.all);
        const freq = keys.map((k) => [k, sc.scored.filter((x) => x.stt[k].st === "alert").length]).filter((x) => x[1]).sort((a, b) => b[1] - a[1]).slice(0, 3);
        const c = card("KPI scorecard — headline ratios", `Latest year per SOE · SOEs with the most alerts first${n > LIMIT && !st.all ? ` · the ${LIMIT} with most alerts of ${n}` : ""}`);
        c.body.append(sc.table, el("div", { class: "btn-row no-print", style: "margin-top:8px" }, moreToggle(n, st.all, (v) => { st.all = v; this.render(); }, `Show the ${LIMIT} with most alerts only`)), sc.legend,
          el("p", { class: "note" }, freq.length ? `Most frequent alerts: ${freq.map(([k, c2]) => `${SPEC[k].label} (${pl(c2, "SOE")})`).join(", ")}.` : "No headline ratio is in the alert range."));
        blocks.push(c.root);
      }
      pf.body.replaceChildren(...blocks);

      /* 3. distress and fiscal risk */
      const rk = H.sec.risk;
      rk.lead.textContent = `Where each SOE sits on the Altman Z″-EM scale, how far it has moved since its first year, and what it could cost the budget (PD × EAD × LGD at LGD ${fmt(S.efc.lgd, 0)}%).`;
      const zc = card("Z″ score by SOE", `Latest year · weakest first${n > LIMIT && !st.all ? ` · ${LIMIT} of ${n}` : ""}`), zbox = el("div", { class: "chart" });
      zc.body.append(zbox);
      const dc = card("Change since the first year", "First year (grey dot) to latest year (dark dot), same order"), dbox = el("div", { class: "chart" });
      const fallers = rows.map((r) => [r, E.notchChange(S.en, r.Entity)]).filter(([, nc]) => nc[2] !== null && nc[2] <= -CFG.DYNAMIC_CAP_TRIGGER_NOTCHES);
      dc.body.append(legendRow([legendItem(LG.prev, "First year"), legendItem(LG.now, "Latest year")]), dbox,
        el("p", { class: "note" }, fallers.length ? el("span", {}, `Rating down ${CFG.DYNAMIC_CAP_TRIGGER_NOTCHES} notches or more: `, el("b", {}, names(fallers.sort((a, b) => a[1][2] - b[1][2]).map(([r, nc]) => `${r.Entity} (${nc[0]} to ${nc[1]})`), 6)), ". Once an SOE starts to slide, the fall tends to be fast, which leaves little time to act.") : `No SOE's indicative rating fell by ${CFG.DYNAMIC_CAP_TRIGGER_NOTCHES} notches or more over the period.`));
      const ec = card("Expected fiscal cost by SOE", `Latest year · largest first · ${S.gdp ? "labels show share of GDP" : "labels show share of portfolio EFC"}`), ebox = el("div", { class: "chart" });
      const conc = efcRows[0] && total ? `The largest exposure, ${efcRows[0].r.Entity}, is ${Math.round((efcRows[0].e / total) * 100)}% of the portfolio's ${money(total, true)}` + (n > 3 ? `; the top three are ${Math.round((top3 / total) * 100)}%.` : ".") : "";
      let band = "";
      if (S.gdp) { const g = total / S.gdp; band = ` At ${pctS(g)} of GDP the portfolio is ${g >= CFG.REPORT_EFC_GDP_ALERT ? "above the alert band" : g >= CFG.REPORT_EFC_GDP_WATCH ? "in the watch band" : "below the watch band"} (watch from ${pct(CFG.REPORT_EFC_GDP_WATCH, 1)}, alert from ${pct(CFG.REPORT_EFC_GDP_ALERT, 1)}, illustrative).`; }
      ec.body.append(ebox, el("p", { class: "note" }, conc + band));
      put(rk.body, el("div", { class: "grid" }, el("div", { class: "s6" }, zc.root), el("div", { class: "s6" }, dc.root), el("div", { class: "s12" }, ec.root)), n > LIMIT ? el("div", { class: "btn-row no-print" }, moreBtn()) : null);
      const zShown = clipRows(byZ, st.all);
      hbars(zbox, zShown.map((r) => ({ label: r.Entity, sub: r.Sector, v: r.Z_EM, lab: `${fmt(r.Z_EM, 2)} · ${r.Rating}`, tipTitle: `${r.Entity} · ${r.Sector}`, tip: [[fmt(r.Z_EM, 2), `Z″ (${r.Year})`], [ZLABEL[zk(r.Zone)] || r.Zone, "zone"], [r.Rating, `rating · PD ${pctAuto(E.pdByRating(r.Rating))}`]] })), { shade: true, max: CFG.Z_SAFE_CUTOFF + 0.4, L: 130 });
      const first = new Map(); byYearAsc(S.en).forEach((r) => { if (!first.has(r.Entity)) first.set(r.Entity, r); });
      dumbbell(dbox, zShown.map((r) => { const f = first.get(r.Entity); return { name: r.Entity, sector: r.Sector, a: f.Z_EM, b: r.Z_EM, ay: f.Year, by: r.Year, ar: f.Rating, br: r.Rating }; }));
      hbars(ebox, clipRows(efcRows, st.all).map((x) => { const e = efcOf(x.r); return { label: x.r.Entity, sub: `${x.r.Rating} · PD ${pctAuto(e.PD)}`, v: ok(x.e) ? x.e * SC : null, cls: "bar", lab: `${money(x.e)} · ${S.gdp ? pctS(x.e / S.gdp) : pct(total ? x.e / total : NaN, 0)}`, tipTitle: `${x.r.Entity} · ${x.r.Sector}`, tip: [[money(x.e, true), "expected fiscal cost"], [money(e.EAD, true), e.EAD_source]] }; }), { tick: (t, s2) => moneyTick(t / SC, s2 / SC), nTicks: 4 });

      /* 4. stress tests */
      const sx = H.sec.stress, m = STD_MAG, D = Math.min(CFG.DEFAULT_SHOCK_PARAMS.shock_duration_years, lastY);
      sx.lead.textContent = `Standard stress in the DSA/DSF convention: fuel ${magText("fuel_shock_pct", m.fuel_shock_pct)}, FX ${magText("fx_shock_pct", m.fx_shock_pct)}, interest rate ${magText("rate_shock_bps", m.rate_shock_bps)}, revenue ${magText("revenue_shock_std_devs", m.revenue_shock_std_devs)}, refinancing ${magText("refinancing_spread_bps", m.refinancing_spread_bps)}, arrears ${magText("arrears_pct_of_revenue", m.arrears_pct_of_revenue)}. Shocks act for ${D} of ${lastY} projection years through each SOE's own exposures; debt and equity built up meanwhile carry forward.`;
      const ct = el("table", { class: "compact" });
      ct.appendChild(el("thead", {}, el("tr", {}, ["Scenario", "Shock", "SOEs dropping a zone", `EFC no shock, ${horizonYear}`, "EFC stressed", "Change"].map((h, i) => el("th", { class: i >= 2 ? "r" : "" }, h)))));
      ct.appendChild(el("tbody", {}, chan.map((c) => {
        const mag = c.key === "combined" ? null : CFG.REPORT_STRESS_CHANNELS[c.key][1];
        const tr = el("tr", { class: "pick" + (c.key === st.scen ? " sel" : ""), tabindex: "0" }, el("td", {}, el("b", {}, c.label)), el("td", { class: "muted" }, mag ? magText(mag, m[mag]) : "all six at once"),
          el("td", { class: "r" }, c.drops.length ? stChip("alert", String(c.drops.length)) : stChip("none", "0")), el("td", { class: "r" }, money(c.eB)), el("td", { class: "r" }, money(c.eS)),
          el("td", { class: "r" }, c.eB ? sgn((c.eS / c.eB - 1) * 100, 0) + "%" : "—"));
        const pick = () => { st.scen = c.key; this.render(); };
        tr.addEventListener("click", pick); tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
        return tr;
      })));
      const cc = card("Stress by channel", "Each channel alone, then all together · select a row to chart it below");
      cc.body.append(el("div", { class: "tbl-wrap" }, ct), el("p", { class: "note" }, "Channels do not add up to the combined scenario: losses compound through the balance sheet, and the rating-band PD steps are not linear."));
      const cur = chan.find((c) => c.key === st.scen) || comb;
      const gap = (x) => last(x.str).Z_EM - last(x.base).Z_EM;
      if (!S.names.includes(st.soe) || !cur.by[st.soe]) st.soe = (cur.res.find((x) => x.drop) || cur.res.slice().sort((a, b) => gap(a) - gap(b))[0] || {}).row?.Entity;
      const x = cur.by[st.soe];
      const pc = card(`Z″ path against the no-shock path · ${cur.label}`, x ? x.desc : "", fSelect(null, byZ.map((r) => r.Entity), st.soe, (v) => { st.soe = v; this.render(); }));
      const pbox = el("div", { class: "chart" });
      pc.body.append(legendRow([legendItem(LG.str, "Stressed"), legendItem(LG.base, "No shock"), legendItem(LG.act, "Shock active"), legendItem(LG.grey, "Grey zone"), legendItem(LG.dist, "Distress")]), pbox);
      const rc = card(x ? `${st.soe} in ${last(x.str)["Calendar Year"]}` : "Result", `${cur.label} · year ${lastY} of the projection`);
      if (x) {
        const b = last(x.base), r = last(x.str);
        const resBox = el("div", { class: "results" }, [["No shock", "base", b], ["Stressed", "stress", r]].map(([h, cls, v]) => el("div", { class: "res " + cls }, el("div", { class: "res-h" }, h), el("div", { class: "res-z" }, el("b", {}, fmt(v.Z_EM, 2)), zoneChip(v.Zone)),
          el("div", { class: "res-line" }, "Rating ", el("b", {}, `${v.Rating} · PD ${pctAuto(v.PD)}`)), el("div", { class: "res-line" }, "EFC ", el("b", {}, money(v.EFC, true) + (S.gdp ? ` · ${pctS(v.EFC_GDP)} of GDP` : ""))))));
        const dz = r.Z_EM - b.Z_EM, de = (r.EFC || 0) - (b.EFC || 0);
        const delta = el("div", { class: "delta" + (x.drop ? " hot" : "") }, "Stress moves Z″ by ", el("b", {}, sgn(dz, 2)), " and EFC by ", el("b", {}, (de >= 0 ? "+" : "") + money(de, true) + (b.EFC ? ` (${sgn((de / b.EFC) * 100, 0)}%)` : "")), x.drop ? " · drops a zone below the no-shock path, so the stress trigger applies." : " against the no-shock path.");
        const drv = E.ZCOMP.map((k) => (r[k] - b[k]) * CFG.ZEM_COEFFICIENTS[k]);
        rc.body.append(resBox, delta, el("div", { class: "lbl", style: "margin-bottom:6px" }, "What moves the score — weighted change, stressed minus no shock"), tracks(E.ZCOMP.map((k) => `${CFG.ZEM_COEFFICIENTS[k]} × ${SHORT[k]}`), drv));
      }
      sx.body.replaceChildren(cc.root, el("div", { class: "grid" }, el("div", { class: "s7" }, pc.root), el("div", { class: "s5" }, rc.root)));
      if (x) {
        const xs = x.str.map((q) => q["Calendar Year"]);
        lines(pbox, xs, [{ vals: x.base.map((q) => q.Z_EM), cls: "ln-base", dot: "prev", skipFirstDot: true, label: "No shock" }, { vals: x.str.map((q) => q.Z_EM), cls: "ln-str", dot: "now", label: "Stressed" }],
          { zones: true, active: [1, D], xLab: (i) => (i === 0 ? `${xs[i]} base` : String(xs[i])), tipTitle: (i) => `${st.soe} · ${xs[i]}`, tip: (i) => [[fmt(x.str[i].Z_EM, 2), `stressed · ${x.str[i].Rating}`], [fmt(x.base[i].Z_EM, 2), `no shock · ${x.base[i].Rating}`], [money(x.str[i].EFC), "EFC stressed"]], endLabel: { series: 1, fmt: (v) => fmt(v, 2) } });
      }

      /* 5. policy implications */
      const po = H.sec.policy;
      po.lead.textContent = "Example rules that link each SOE's financial health to a pre-agreed fiscal response, the SOEs that trigger them, and what the numbers rest on.";
      const fired = CFG.TRIGGER_RULES.filter((r) => hits[r.id].length && r.id !== "routine");
      const rt = card("Triggered rules and pre-agreed actions", fired.length ? "Most severe first · actions are examples, to be agreed with the ministry" : null);
      rt.body.append(fired.length ? simpleTable(["Signal", "Condition", "Pre-agreed action (example)", "SOEs"], fired.map((r) => [el("td", {}, stChip(r.level)), r.condition, r.action, el("td", {}, el("div", { class: "soe-list" }, hits[r.id].map((nm) => el("span", {}, nm))))]), { cls: "rules" }) : el("p", { class: "note" }, "No SOE triggers an alert or watch rule; routine annual monitoring applies."));
      const bd = card("Signal board", "Each SOE under the most severe rule it triggers");
      bd.body.append(signalBoard(byZ.slice().reverse(), by));
      const cv = card("Sources and caveats");
      const cnts = Object.keys(CFG.PARAMETER_STATUS_LABELS).map((k) => [k, CFG.PARAMETER_REGISTER.filter((r) => r.status === k).length]);
      cv.body.append(el("ul", { class: "caveats" }, caveats().map((t) => el("li", {}, t))),
        el("p", { class: "note" }, "Parameter register: ", cnts.map(([k, c2], i) => [i ? " · " : "", el("b", {}, String(c2)), " " + CFG.PARAMETER_STATUS_LABELS[k].toLowerCase()]), ". Each is listed with its source on the ", go("assumptions", "Assumptions & sources"), " tab."));
      po.body.replaceChildren(rt.root, bd.root, cv.root);
      H.gen.textContent = `Generated in this page on ${new Date().toISOString().slice(0, 10)} from ${S.label}. SOE Fiscal Risk Tool — HTML version.`;
      if (this.pending) this.pending();
    },
  };

  /* =====================================================================
     ASSUMPTIONS & SOURCES
     ===================================================================== */
  const ASM_K = { literature: "ok", user: "none", proxy: "watch", placeholder: "alert", design: "watch" };
  pages.assumptions = {
    build(root) {
      const st = S.asm, H = (this.H = {});
      const reg = CFG.PARAMETER_REGISTER, labels = CFG.PARAMETER_STATUS_LABELS;
      const tiles = el("div", { class: "autogrid" }, Object.keys(labels).map((k) => { const [a, b] = labels[k].split(" — "); return tile(a, ASM_K[k], ({ literature: "Sourced", user: "Set by you", proxy: "Proxy", placeholder: "Needs source", design: "Justify" })[k], String(reg.filter((r) => r.status === k).length), `of ${reg.length}`, b ? b[0].toUpperCase() + b.slice(1) : ""); }));
      const groups = uniq(reg.map((r) => r.group));
      const ctl = el("div", { class: "row-ctl" },
        el("div", { class: "fld" }, el("span", { class: "lbl" }, "Status"), chipsMulti(Object.keys(labels).map((k) => [k, labels[k].split(" — ")[0]]), st.status, () => this.render())),
        fSelect("Group", [["all", "All groups"], ...groups.map((g) => [g, g])], st.group, (v) => { st.group = v; this.render(); }));
      H.reg = card("Parameter register", "Every coefficient, threshold and default the tool uses, with its source and status", null, "top");
      H.reg.body.append(ctl, el("div", { style: "margin-top:12px" }), el("div", { style: "margin-top:10px" }));
      const dict = card("Standard data schema", `The ${CFG.SCHEMA.variables.length} variables the upload understands. Headers are matched by exact name, then known synonyms, then close spelling (similarity ≥ ${CFG.SCHEMA.fuzzy_cutoff}).`);
      dict.body.append(simpleTable(["Key", "Label", "Statement", "Kind", "Req.", "Used by", "Also recognised as"], SCHEMA_VARS().map((v) => [el("td", { class: "mono" }, v.key), v.label, v.statement, v.kind, v.required ? "yes" : "", v.used_by, el("td", { class: "wrap-cell" }, v.synonyms.join("; "))]), { cls: "compact dict", tall: true }),
        el("div", { class: "btn-row", style: "margin-top:10px" }, dataButtons(templateCSV, "soe_tool_template.csv", "template"), dataButtons(dictionaryCSV, "soe_variable_dictionary.csv", "dictionary")));
      root.replaceChildren(pageHead("MODEL GOVERNANCE", "Assumptions & sources", "Every number the tool relies on, where it comes from, and how firm it is. Placeholders are numbers the tool needs to run but that still need a literature or data source before results are used in policy advice."),
        tiles, el("div", { class: "stack", style: "margin-top:16px" }, H.reg.root, dict.root),
        el("div", { class: "foot" }, el("div", {}, "The register lives in config.PARAMETER_REGISTER; update a row's status and source there when a placeholder gets calibrated. Values shown are the config defaults — sliders on the other tabs can change them for a run.")));
    },
    render() {
      const st = S.asm, H = this.H, labels = CFG.PARAMETER_STATUS_LABELS;
      const rows = CFG.PARAMETER_REGISTER.filter((r) => st.status.has(r.status) && (st.group === "all" || r.group === st.group));
      const [, tblBox, btnBox] = H.reg.body.children;
      tblBox.replaceChildren(rows.length ? simpleTable(["Group", "Parameter", "Value", "Status", "Source", "Used in"], rows.map((r) => [r.group, el("td", {}, el("b", {}, r.parameter)), el("td", { class: "wrap-cell" }, String(r.value)), el("td", {}, stChip(ASM_K[r.status], labels[r.status].split(" — ")[0])), el("td", { class: "wrap-cell" }, r.source), el("td", { class: "wrap-cell" }, r.used_in)]), { cls: "compact register" }) : el("p", { class: "note" }, "No parameters match these filters."));
      btnBox.replaceChildren(dataButtons(() => toCSV(["group", "parameter", "value", "status", "source", "used_in"], rows.map((r) => [r.group, r.parameter, r.value, labels[r.status], r.source, r.used_in])), "parameter_register.csv"));
    },
  };

  /* =====================================================================
     boot
     ===================================================================== */
  const startKey = DATASETS.report ? "report" : DATASETS.demo ? "demo" : "sample";
  const start = DATASETS[startKey];
  const h = (location.hash || "").slice(1).replace(/^view-/, "");
  if (pages[h]) S.tab = h;
  loadDataset(start.rows, start.label, start.example, startKey);
  let lastW = document.documentElement.clientWidth, raf = 0;
  new ResizeObserver(() => {
    const w = document.documentElement.clientWidth;
    if (w === lastW) return;
    lastW = w; cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => pages[S.tab].render());
  }).observe(document.body);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => pages[S.tab].render());
})();
