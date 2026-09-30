"""
Classic entry point: the Python-rendered multipage version of the tool
(Plotly charts, Excel template download, the HTML-version export page).

    streamlit run classic.py

The main entry point, Home.py, shows the interactive tool itself — the same
screens as the HTML version.
"""

import streamlit as st

from utils import theme

st.set_page_config(page_title="SOE Fiscal Risk Tool", layout="wide", page_icon="🏛️")
theme.inject()

home_page = st.Page("app_pages/home.py", title="Home", icon="🏠", default=True)
kpi_page = st.Page("app_pages/kpi_dashboard.py", title="KPI Dashboard", icon="📊")
altman_page = st.Page("app_pages/altman_z.py", title="Altman Z-EM", icon="📉")
efc_page = st.Page("app_pages/efc.py", title="Expected Fiscal Cost", icon="💰")
shock_page = st.Page("app_pages/shock_scenarios.py", title="Shock Scenarios", icon="⚡")
gre_page = st.Page("app_pages/strategic_soe.py", title="Government Support", icon="🏛️")
report_page = st.Page("app_pages/report.py", title="HTML version", icon="📄")
assumptions_page = st.Page("app_pages/assumptions.py", title="Assumptions & sources", icon="📚")

# The HTML version sits next to Home so it stays visible when narrower
# screens fold the later pages into the nav's "more" menu.
pg = st.navigation([home_page, report_page, kpi_page, altman_page, efc_page, shock_page, gre_page, assumptions_page], position="top")
pg.run()
