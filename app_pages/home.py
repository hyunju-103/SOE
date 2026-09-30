import pandas as pd
import streamlit as st

import calculations
import config
import data_loader
from utils import theme
from utils.portfolio import latest_per_entity

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
    "A four-layer framework for state-owned enterprises: financial diagnostics "
    "(KPI Dashboard), distress signal (Altman Z-EM), fiscal exposure to the "
    "sovereign (Expected Fiscal Cost), and dynamic shock simulation "
    "(Shock Scenarios). The HTML version page exports the whole tool as one shareable file.",
    meta=_meta,
)

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
# Overview stat row
# ------------------------------------------------------------------ #

if st.session_state.soe_df is not None:
    full = calculations.compute_zem_components(st.session_state.soe_df)
    d = latest_per_entity(full)
    n_soe = d["Entity"].nunique()
    n_sectors = d["Sector"].nunique() if "Sector" in d.columns else 0
    distress_n = int((d["Zone"] == "Distress").sum())
    avg_z = d["Z_EM"].mean() if n_soe else float("nan")

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.markdown(theme.stat_card("🏛️", "blue", "Total SOEs", n_soe, f"Across {n_sectors} sector(s)"), unsafe_allow_html=True)
    with s2:
        st.markdown(theme.stat_card("📊", "purple", "Average Z-EM", f"{avg_z:.2f}", "Portfolio-wide, latest year"), unsafe_allow_html=True)
    with s3:
        pct = (distress_n / n_soe * 100) if n_soe else 0
        st.markdown(
            theme.stat_card("⚠️", "red", "SOEs in distress", f"{distress_n} / {n_soe}", f"{pct:.0f}% of portfolio (Z-EM ≤ 1.1)"),
            unsafe_allow_html=True,
        )
    with s4:
        st.markdown(theme.stat_card("🌍", "green", "Coverage", "Multi-sector", "Filter by sector on any page"), unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

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

# ------------------------------------------------------------------ #
# Data upload
# ------------------------------------------------------------------ #

st.markdown('<div class="sfp-card">', unsafe_allow_html=True)
up_label, up_widget = st.columns([1, 2])
with up_label:
    st.markdown(
        '<div class="sfp-title" style="margin-bottom:6px;">Upload your data</div>'
        '<p class="sfp-hint">CSV or Excel, one row per SOE-year.</p>',
        unsafe_allow_html=True,
    )
with up_widget:
    uploaded = st.file_uploader("Drop a CSV or Excel file", type=["csv", "xlsx", "xls"], label_visibility="collapsed")

if uploaded is not None:
    try:
        df, mapping = data_loader.load_and_standardize(uploaded)
        validation = data_loader.validate_schema(df)
        st.session_state.column_mapping = mapping
        if validation["missing_required"]:
            st.markdown(
                f'<div class="sfp-alert warn">Missing required column(s): '
                f'{", ".join(validation["missing_required"])}. Please add these and re-upload.</div>',
                unsafe_allow_html=True,
            )
        else:
            df = data_loader.coerce_numeric(df)
            issues = data_loader.numeric_issues(df)
            st.session_state.soe_df = df
            st.session_state.using_sample = False
            st.session_state.sample_label = uploaded.name
            note = f"Loaded {df['Entity'].nunique()} SOE(s), {len(df)} SOE-year rows."
            if not issues.empty:
                note += f" {len(issues)} row(s) have non-numeric or missing required values."
            st.markdown(f'<div class="sfp-alert ok">✓ {note}</div>', unsafe_allow_html=True)
            if validation["missing_optional"]:
                with st.expander("Optional shock-module fields not present (not required for this build)"):
                    st.write(", ".join(validation["missing_optional"]))
            renamed = mapping[(mapping["Mapped to"] != "") & (mapping["Uploaded column"] != mapping["Mapped to"])]
            review = mapping[mapping["Confidence"].isin(["LOW"]) | mapping["Method"].isin(["unmatched", "duplicate"])]
            with st.expander(f"Column mapping — {len(renamed)} renamed to the standard schema, {len(review)} to review"):
                st.dataframe(mapping, use_container_width=True, hide_index=True)
                st.caption("HIGH = exact name, MEDIUM = known synonym, LOW = close spelling (check it). Unmatched columns are kept but not used.")
    except Exception as e:
        st.markdown(f'<div class="sfp-alert warn">Couldn\'t read that file: {e}</div>', unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------ #
# Try it with example data
# ------------------------------------------------------------------ #

st.markdown('<div class="sfp-card"><div class="sfp-title">Try it with example data</div>', unsafe_allow_html=True)
ex1, ex2 = st.columns(2)
with ex1:
    if st.button("Use example data (SOE A — Energy, SOE B — Transport)"):
        st.session_state.soe_df = data_loader.sample_dataset()
        st.session_state.using_sample = True
        st.session_state.sample_label = "Built-in sample: SOE A (Energy), SOE B (Transport)"
        st.rerun()
    st.caption("Two SOEs, five years of full statements (2020–2024) — Z-EM and every ratio computed live.")
with ex2:
    if st.button("Use demo portfolio (8 SOEs, 7 sectors)"):
        st.session_state.soe_df = data_loader.demo_portfolio()
        st.session_state.using_sample = True
        st.session_state.sample_label = "Illustrative demo portfolio: 8 invented SOEs"
        st.rerun()
    st.caption("The two sample SOEs plus six invented ones spanning safe, grey and distress — for demos.")
st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------ #
# Template
# ------------------------------------------------------------------ #

st.markdown('<div class="sfp-card"><div class="sfp-title">Template</div>', unsafe_allow_html=True)
tc1, tc2 = st.columns(2)
with tc1:
    st.download_button("Template: standard schema (Excel, with dictionary)", data_loader.template_excel_bytes(),
                       file_name="soe_toolkit_template.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
with tc2:
    st.download_button("Template: raw financials (CSV, tool column names)", data_loader.TEMPLATE_CSV, file_name="soe_tool_template.csv")
st.markdown(
    '<p class="sfp-hint">The Excel template is the standard SOE × year schema — the target format for the PDF → Excel '
    'extraction pipeline. Its Dictionary sheet lists every variable, the statement it comes from and the label variants the '
    'upload recognises (e.g. "Operating Costs", "OPEX" → operating_expense); provenance columns (source_file, source_page, '
    'audit_status, extraction_method, data_quality_flag) keep the audit trail.</p>',
    unsafe_allow_html=True,
)
st.markdown(
    f'<p class="sfp-hint">Required columns: {", ".join(config.REQUIRED_COLUMNS)}. '
    f"Optional shock-module fields ({', '.join(config.OPTIONAL_SHOCK_COLUMNS)}) unlock more "
    f"precision on the Shock Scenarios page — missing ones simply fall back to sector defaults.</p>",
    unsafe_allow_html=True,
)
st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------ #
# Data preview
# ------------------------------------------------------------------ #

if st.session_state.soe_df is None:
    st.markdown(
        '<div class="sfp-alert info">No data loaded yet. Upload a file above, or try the example portfolio.</div>',
        unsafe_allow_html=True,
    )
else:
    if st.session_state.using_sample:
        st.markdown(
            '<div class="sfp-alert info">Showing example data. Upload your own file above to replace it.</div>',
            unsafe_allow_html=True,
        )
    with st.expander("Data preview"):
        st.dataframe(st.session_state.soe_df, use_container_width=True, height=240)
    dq = data_loader.data_quality_summary(st.session_state.soe_df)
    if not dq.empty:
        with st.expander("Data quality and provenance"):
            st.dataframe(dq, use_container_width=True, hide_index=True)
            st.caption("From the provenance columns of the upload: Observed vs Proxy vs User assumption, audit status and extraction method.")
    st.markdown(
        '<p class="sfp-hint">Use the pages in the top nav — KPI Dashboard, Altman Z-EM, Expected Fiscal '
        "Cost, Shock Scenarios — to explore this data.</p>",
        unsafe_allow_html=True,
    )
