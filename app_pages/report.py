"""
HTML version page — exports the whole tool as one self-contained HTML file
(report.py): every page of this app as a tab (Home, the five-section Report,
KPI Dashboard, Altman Z-EM, Expected Fiscal Cost, Shock Scenarios with Monte
Carlo, Government Support, Early Warning, Assumptions & sources), running in
the browser with the same formulas and config.py values. Recipients need no Python: they can explore, move the
shock sliders, and load their own CSV/Excel file into it.
"""

import datetime as dt

import streamlit as st
import streamlit.components.v1 as components

import config
import report
from utils import theme

theme.header(
    "SHARE",
    "Interactive HTML version",
    "The whole tool — every page, as a tab — in one HTML file that opens in any browser "
    "with no Python or server. The file carries the data loaded here; people you send it to "
    "can explore it, run shock scenarios and Monte Carlo, and load their own data.",
)

if st.session_state.get("soe_df") is None:
    st.markdown(
        '<div class="sfp-alert warn">No data loaded yet — go to the Home page and upload a file '
        'or use the example portfolio.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

df = st.session_state.soe_df
currency = str(df["Currency"].dropna().iloc[0]) if "Currency" in df.columns and df["Currency"].notna().any() else ""

st.markdown('<div class="sfp-card"><div class="sfp-title">Starting values</div>', unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)
with c1:
    lgd_pct = st.slider("LGD (%)", config.LGD_SLIDER_MIN, config.LGD_SLIDER_MAX, config.LGD_SLIDER_DEFAULT,
                        key="report_lgd", help=config.GLOSSARY["LGD"])
with c2:
    use_gdp = st.toggle("Include GDP (EFC as a share of GDP)", value=bool(st.session_state.get("report_use_gdp", False)),
                        key="report_use_gdp")
    base_gdp = None
    if use_gdp:
        base_gdp = st.number_input(
            f"Nominal GDP, latest year ({currency})", min_value=0.0,
            value=float(st.session_state.get("report_gdp_value", 0.0)), step=1e9, format="%.0f",
            key="report_gdp_value",
            help="Same currency and units as the uploaded statements.",
        ) or None
with c3:
    gdp_growth = st.slider("Nominal GDP growth (%/yr)", -5.0, 15.0, config.DEFAULT_GDP_GROWTH * 100, 0.5,
                           key="report_growth", disabled=not use_gdp) / 100.0
title = st.text_input("Title", value=config.REPORT_TITLE, key="report_title")
st.markdown(
    '<p class="sfp-hint">These are only starting values — every control in the file can be changed by '
    "whoever opens it. Thresholds, coefficients and shock defaults come from config.py.</p>",
    unsafe_allow_html=True,
)
st.markdown("</div>", unsafe_allow_html=True)

is_example = bool(st.session_state.get("using_sample"))
data_label = st.session_state.get("sample_label", "Example data") if is_example else "Uploaded data"

with st.spinner("Building the HTML file…"):
    html = report.build_html(
        df, lgd_pct=lgd_pct, base_gdp=base_gdp, gdp_growth=gdp_growth,
        title=title or config.REPORT_TITLE, data_label=data_label, is_example=is_example,
    )

d1, d2 = st.columns([1, 3])
with d1:
    st.download_button(
        "⬇ Download HTML file", html,
        file_name=f"soe_fiscal_risk_tool_{dt.date.today():%Y%m%d}.html",
        mime="text/html", type="primary",
    )
with d2:
    st.markdown(
        f'<p class="sfp-hint" style="margin-top:8px">{len(html) / 1024:,.0f} KB, one file. Works offline; the web '
        f"font and the Excel reader (for .xlsx uploads) load from the internet when available. Preview below.</p>",
        unsafe_allow_html=True,
    )

components.html(html, height=1400, scrolling=True)
