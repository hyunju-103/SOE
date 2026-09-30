"""
SOE Fiscal Risk Tool — main entry point.

    streamlit run Home.py

Shows the interactive tool full-window, exactly as the HTML version looks:
Home, Report, KPI Dashboard, Altman Z-EM, Expected Fiscal Cost, Shock
Scenarios, Government Support, Early Warning and Assumptions & sources, with
the demo portfolio loaded and an upload box for your own CSV/Excel file.

The page is built by report.py from templates/ (app.html, app.css, app.js,
engine.js) and every number in config.py; the calculations run in the
viewer's browser with the same formulas as calculations.py / shocks.py
(checked by tests/check_engine_parity.py). Uploaded files are read in the
browser and are not sent to the server.

The Python-rendered multipage version is still available:
    streamlit run classic.py
"""

import streamlit as st
import streamlit.components.v1 as components

import config
import data_loader
import report

st.set_page_config(page_title=config.REPORT_TITLE, page_icon="🏛️", layout="wide", initial_sidebar_state="collapsed")

# Hide Streamlit's own chrome and let the tool fill the window; it scrolls inside its frame.
st.markdown(
    """
    <style>
      header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
      [data-testid="stStatusWidget"], #MainMenu, footer { display: none !important; }
      html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] { overflow: hidden !important; }
      .block-container, [data-testid="stMainBlockContainer"] { padding: 0 !important; max-width: 100% !important; }
      [data-testid="stVerticalBlock"] { gap: 0 !important; }
      [data-testid="stElementContainer"]:has(iframe), .element-container:has(iframe) { height: 100vh !important; }
      iframe { display: block; border: 0; width: 100% !important; height: 100vh !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def tool_page() -> str:
    app = report.build_app_data(
        data_loader.demo_portfolio(),
        data_label="Illustrative demo portfolio: 8 invented SOEs",
        is_example=True,
        allow_download=True,  # the Streamlit frame permits downloads and printing
    )
    return report.render_html(app, standalone=True)


components.html(tool_page(), height=900, scrolling=True)
