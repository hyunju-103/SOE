import pandas as pd
import streamlit as st

import calculations
import config
import data_loader
from utils import overview as ov
from utils import summary, theme

THEME_HEADING = config.THEME["heading"]

if "soe_df" not in st.session_state:
    st.session_state.soe_df = None
    st.session_state.using_sample = False

_meta = None
if st.session_state.soe_df is not None:
    _d = st.session_state.soe_df
    _years = sorted(_d["Year"].dropna().unique().tolist())
    _meta = [
        ("Portfolio", f"{_d['Entity'].nunique()} SOEs · {_d['Sector'].nunique() if 'Sector' in _d.columns else 0} sectors"),
        ("Statements", f"{_years[0]:.0f}–{_years[-1]:.0f}" if len(_years) > 1 else f"{_years[0]:.0f}"),
    ]
    if st.session_state.get("using_sample"):
        _meta.append(("flag", st.session_state.get("sample_label", "Example data")))

theme.header(
    "SOE FISCAL RISK TOOL",
    "SOE Fiscal Risk Dashboard",
    "A layered framework for state-owned enterprises: financial diagnostics "
    "(KPI Dashboard), distress signal (Altman Z-EM), fiscal exposure to the "
    "sovereign (Expected Fiscal Cost), dynamic shock simulation (Shock Scenarios) "
    "and government support. The HTML version page exports the whole tool as one shareable file.",
    meta=_meta,
)

# ------------------------------------------------------------------ #
# Top row: load data (left half) | portfolio overview (right half)
# ------------------------------------------------------------------ #
BUILTIN = {
    "sample": ("Example", "SOE A and B · 2020–2024", data_loader.sample_dataset, "Built-in sample: SOE A (Energy), SOE B (Transport)"),
    "demo": ("Demo portfolio", "8 SOEs · 7 sectors", data_loader.demo_portfolio, "Illustrative demo portfolio: 8 invented SOEs"),
    "long": ("Long panel", "30 SOEs · 20 years", data_loader.long_panel_demo, data_loader.LONG_PANEL_LABEL),
}


def _load_builtin(key):
    _name, _sub, make, label = BUILTIN[key]
    st.session_state.soe_df = make()
    st.session_state.using_sample = True
    st.session_state.sample_label = label
    st.session_state.column_mapping = None
    st.session_state.upload_note = None


col_load, col_over = st.columns(2, gap="medium")

with col_load:
    st.markdown('<div class="sfp-title" style="margin-bottom:6px;">Load data</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader(
        "Drop a CSV or Excel file here", type=["csv", "xlsx", "xls", "txt"],
        help="One row per SOE-year. Column names are matched to the standard schema, numbers such as "
             "1,234 · (1,234) · 35% are read, and title rows above the table are skipped.",
    )
    # read a file once, when it arrives — not again on every rerun (so a built-in dataset can replace it)
    if uploaded is not None and st.session_state.get("last_upload_id") != uploaded.file_id:
        st.session_state.last_upload_id = uploaded.file_id
        try:
            df_up, mapping = data_loader.load_and_standardize(uploaded)
            validation = data_loader.validate_schema(df_up)
            st.session_state.column_mapping = mapping
            if validation["missing_required"]:
                st.session_state.upload_note = ("warn", "Missing required column(s): " + ", ".join(validation["missing_required"])
                                                + ". Check the column mapping below, rename or add these columns, and upload again.")
            else:
                df_up = data_loader.coerce_numeric(df_up)
                issues = data_loader.numeric_issues(df_up)
                st.session_state.soe_df = df_up
                st.session_state.using_sample = False
                st.session_state.sample_label = uploaded.name
                note = f"✓ Loaded {df_up['Entity'].nunique()} SOE(s), {len(df_up)} SOE-year rows from {uploaded.name}."
                if not issues.empty:
                    note += f" {len(issues)} row(s) have non-numeric or missing required values — check the data preview below."
                st.session_state.upload_note = ("ok", note)
                st.rerun()
        except Exception as e:  # noqa: BLE001 — show the reader's message to the user
            st.session_state.upload_note = ("warn", f"Couldn't read that file: {e}")
    note = st.session_state.get("upload_note")
    if note:
        st.markdown(f'<div class="sfp-alert {note[0]}">{note[1]}</div>', unsafe_allow_html=True)

    d0 = st.session_state.soe_df
    if d0 is not None:
        yrs = sorted(d0["Year"].dropna().unique().tolist())
        st.markdown(
            f'<div class="sfp-hint" style="margin-top:6px"><b>Now showing:</b> {st.session_state.get("sample_label", "Loaded data")} · '
            f'{d0["Entity"].nunique()} SOEs · {len(d0)} SOE-year rows · {yrs[0]:.0f}–{yrs[-1]:.0f}</div>',
            unsafe_allow_html=True,
        )
    st.markdown('<div class="sfp-hint" style="margin:10px 0 4px"><b>Or try built-in data</b></div>', unsafe_allow_html=True)
    b_cols = st.columns(3)
    for (key, (name, sub, _make, label)), bc in zip(BUILTIN.items(), b_cols):
        with bc:
            if st.button(name, key=f"ds_{key}", help=sub, use_container_width=True,
                         type="primary" if st.session_state.get("sample_label") == label else "secondary"):
                _load_builtin(key)
                st.rerun()
            st.caption(sub)
    st.markdown('<div class="sfp-hint" style="margin:6px 0 4px"><b>Standard template</b></div>', unsafe_allow_html=True)
    t1, t2 = st.columns(2)
    with t1:
        st.download_button("⬇ Excel template (with dictionary)", data_loader.template_excel_bytes(), file_name="soe_toolkit_template.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    with t2:
        st.download_button("⬇ CSV template", data_loader.TEMPLATE_CSV, file_name="soe_tool_template.csv", use_container_width=True)

with col_over:
    st.markdown('<div class="sfp-title" style="margin-bottom:6px;">Portfolio overview</div>', unsafe_allow_html=True)
    d0 = st.session_state.soe_df
    if d0 is None:
        st.markdown('<div class="sfp-alert info">No data loaded yet. Upload a file, or try one of the built-in datasets.</div>',
                    unsafe_allow_html=True)
    else:
        dz = calculations.compute_zem_components(data_loader.coerce_numeric(d0))
        o = ov.portfolio_overview(dz)
        n, zc = o["n"], o["zones"]
        scale, cur = ov.unit_scale(d0), ov.currency(d0)
        share = (zc["Distress"] + zc["Grey"]) / n if n else float("nan")
        bar = "".join(
            f'<div style="width:{zc[z] / n * 100:.4f}%;background:{col}"></div>'
            for z, col in [("Safe", config.THEME["green"]), ("Grey", config.THEME["amber"]), ("Distress", config.THEME["red"])] if zc[z]
        )
        legend = "".join(
            f"{theme.status_chip(c, z_label)} <b>{zc[z]}</b> ({int(zc[z] / n * 100 + 0.5)}%)"
            for z, c, z_label in [("Safe", "green", "Safe"), ("Grey", "amber", "Grey zone"), ("Distress", "red", "Distress")]
        )
        st.markdown(
            f'<div class="sfp-hero"><div class="sfp-hero-label">SOEs in distress or the grey zone</div>'
            f'<div class="sfp-hero-value">{int(share * 100 + 0.5)}%<small>{zc["Distress"] + zc["Grey"]} of {ov.plural(n, "SOE")} · average Z″ {o["mean_z"]:.2f}</small></div>'
            f'<div class="sfp-zonebar">{bar}</div><div class="sfp-zonelegend">{legend}</div>'
            f'<div class="sfp-hint" style="margin:0">{summary.summarize_zone_distribution(o["latest"].sort_values("Z_EM", ascending=False))}</div></div>',
            unsafe_allow_html=True,
        )
        top, total = o["top"], o["efc_total"]
        up = (o["efc_stress"] / o["efc_base"] - 1) * 100 if o["efc_base"] else float("nan")
        drops = o["drops"]
        drop_txt = ", ".join(drops[:4]) + (f" and {len(drops) - 4} more" if len(drops) > 4 else "")
        tiles = [
            theme.tile("Expected fiscal cost, portfolio", ov.money(total, scale), cur,
                       f"PD × EAD × LGD, latest year · LGD {config.LGD_SLIDER_DEFAULT}% · EAD {config.EAD_SHARE_DEFAULT:.0%} of liabilities"),
            theme.tile("Largest single exposure", ov.money(top["EFC"], scale), cur,
                       f"{top['Entity']} · {top['EFC'] / total * 100 if total else 0:.0f}% of portfolio EFC · rated {top['Rating']}, PD {ov.pct(top['PD'], 1)}",
                       status=ov.ZONE_STATUS.get(top["Zone"]), status_text=ov.ZONE_TEXT.get(top["Zone"])) if top is not None else None,
            theme.tile("Drop a zone under standard stress", str(len(drops)), f"of {n} SOEs",
                       (drop_txt + " · " if drops else "") + f"portfolio EFC {ov.signed(up)}% against no shock in year {config.MC_HORIZON_YEARS} · each SOE's own exposures",
                       status="alert" if drops else "ok"),
        ]
        w = o["worst"]
        if w and w[0] < 0:
            dzv, r, f = w
            tiles.append(theme.tile("Fastest deterioration", f"{dzv:+.2f}".replace("-", "−"), "Z″ points",
                                    f"{r['Entity']}: {f['Z_EM']:.2f} in {int(f['Year'])} to {r['Z_EM']:.2f} in {int(r['Year'])} · {f['Rating']} to {r['Rating']}",
                                    status=ov.ZONE_STATUS.get(r["Zone"]), status_text=ov.ZONE_TEXT.get(r["Zone"])))
        else:
            tiles.append(theme.tile("Fastest deterioration", "None", "", "No SOE's Z″ fell over the period" if o["n_moved"] else "Needs at least two years per SOE", status="ok"))
        st.markdown(f'<div class="sfp-2col">{"".join(theme.tile_html(**t) for t in tiles if t)}</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------ #
# Details of the data on screen (full width, collapsed)
# ------------------------------------------------------------------ #
mapping = st.session_state.get("column_mapping")
if mapping is not None and len(mapping):
    renamed = mapping[(mapping["Mapped to"] != "") & (mapping["Uploaded column"] != mapping["Mapped to"])]
    review = mapping[mapping["Confidence"].isin(["LOW"]) | mapping["Method"].isin(["unmatched", "duplicate"])]
    with st.expander(f"Column mapping — {len(renamed)} renamed to the standard schema, {len(review)} to review", expanded=len(review) > 0):
        st.dataframe(mapping, use_container_width=True, hide_index=True)
        st.caption("HIGH = exact name, MEDIUM = known synonym, LOW = close spelling (check it). Unmatched columns are kept but not used.")
with st.expander("Required and optional columns"):
    st.markdown(f"**Required:** {', '.join(config.REQUIRED_COLUMNS)}.")
    st.markdown("**Optional, used when present:** Short Term Debt, FX Debt, Fuel Cost and the exposure shares "
                "(bottom-up shock exposures); Government Guaranteed Debt (observed EAD); Source File, Source Page, "
                "Audit Status, Extraction Method and Data Quality Flag (provenance). Missing ones fall back to "
                "sector or generic defaults. The full list with synonyms is on the Assumptions & sources page.")
if st.session_state.soe_df is not None:
    with st.expander(f"Data preview ({len(st.session_state.soe_df)} rows)"):
        st.dataframe(st.session_state.soe_df, use_container_width=True, height=280)
    dq = data_loader.data_quality_summary(st.session_state.soe_df)
    if not dq.empty:
        with st.expander("Data quality and provenance"):
            st.dataframe(dq, use_container_width=True, hide_index=True)
            st.caption("From the provenance columns of the upload: Observed vs Proxy vs User assumption, audit status and extraction method.")
st.markdown("<br>", unsafe_allow_html=True)

# ------------------------------------------------------------------ #
# Toolkit map — where this tool sits in the SOE fiscal-risk toolkit
# ------------------------------------------------------------------ #
MODULES = [
    ("Country Analysis", "This tool", "green", "Upload a country's SOE statements: KPIs, Altman Z-EM, expected fiscal cost, shocks, government support, early warning, report."),
    ("Global Monitoring", "Prototype", "amber", "Cross-country SOE benchmarking (Pacific monitor first) — needs the standardised multi-country repository."),
    ("Hidden Subsidies", "Planned", "muted", "Financing advantage over comparable private firms × SOE base; formula and variables to confirm from the reference note."),
    ("PSO Analysis", "Planned", "muted", "Public service obligations — separating PSO costs from inefficiency; builds on the viability assessment here."),
    ("Energy Fiscal Risk", "Separate model", "muted", "Tariffs, cost recovery and subsidies in the power sector (Ghana model, other team)."),
]
_cards = "".join(
    f'<div class="sfp-stat" style="padding:12px 14px"><div class="sfp-stat-top" style="margin-bottom:6px">'
    f'<div class="sfp-stat-label" style="color:{THEME_HEADING};font-weight:700">{name}</div>{theme.status_chip(color, status)}</div>'
    f'<div class="sfp-stat-caption" style="margin:0">{text}</div></div>'
    for name, status, color, text in MODULES
)
st.markdown(f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-bottom:18px">{_cards}</div>',
            unsafe_allow_html=True)

# ------------------------------------------------------------------ #
# About
# ------------------------------------------------------------------ #

with st.expander("About this tool", expanded=st.session_state.soe_df is None):
    st.markdown(
        """
**How it works**

1. **Upload** — a portfolio of SOEs, one row per SOE-year, with raw financial
   statement fields. The tool computes the Altman Z''-EM components, the
   score, and every KPI ratio itself from the raw numbers.
2. **KPI Dashboard** — profitability, liquidity, solvency, and
   fiscal-dependency ratios, benchmarked against illustrative thresholds.
3. **Altman Z-EM** — the four Z''-EM components, the score itself,
   cross-SOE benchmarking, and a distress/grey/safe distribution with an
   indicative credit-rating cohort.
4. **Expected Fiscal Cost** — PD × EAD × LGD, PD from each SOE's Z-EM rating band,
   EAD proxied by Total Liabilities, LGD set by you.
5. **Shock Scenarios** — fuel, FX, interest rate, revenue, refinancing and
   government arrears shocks flow through each SOE's own balance-sheet
   exposures (bottom-up) and compound over a multi-year horizon, with a
   correlated Monte Carlo option and an Expected Fiscal Cost / GDP path.
6. **Government Support** — Role × Link support tier and a bounded rating
   uplift, capped by the sovereign.
7. **HTML version** — the whole tool, every page, as one HTML file that
   runs in any browser with no Python: share it, and recipients can run
   shocks, Monte Carlo and upload their own data.

Every chart in the tool can export its underlying data, and comes with an
automated plain-language summary generated directly from the numbers on
screen (not a live AI call).

**Scope.** Test build. Every coefficient and threshold is listed on the
**Assumptions & sources** page as literature / data-based, user-set, a
proxy, or a placeholder that still needs a source.
        """
    )

with st.expander("Glossary — what the terms mean"):
    st.markdown('<p class="sfp-hint">Plain-language definitions for the terms used throughout this tool.</p>', unsafe_allow_html=True)
    rows = "".join(f"<tr><td style='font-weight:700;white-space:nowrap;'>{term}</td><td>{definition}</td></tr>" for term, definition in config.GLOSSARY.items())
    st.markdown(f"<table class='sfp-table sfp-table-wrap'><tbody>{rows}</tbody></table>", unsafe_allow_html=True)
