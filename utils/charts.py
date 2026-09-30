"""Small shared helpers for chart labels and chart/data download buttons."""

import textwrap

import streamlit as st


def wrap_label(s, width=12):
    """Insert <br> line breaks so a long category label wraps under a bar
    instead of needing rotation."""
    return "<br>".join(textwrap.wrap(str(s), width=width)) or str(s)


MINIMAL_MODEBAR_CONFIG = {
    "displayModeBar": True,
    "displaylogo": False,
    "modeBarButtonsToRemove": [
        "zoom2d", "pan2d", "select2d", "lasso2d", "zoomIn2d", "zoomOut2d",
        "autoScale2d", "resetScale2d", "hoverClosestCartesian", "hoverCompareCartesian",
        "toggleSpikelines",
    ],
    "toImageButtonOptions": {"format": "png", "scale": 2},
}


def _fig_to_png_bytes(fig, scale=2):
    """Best-effort PNG export. Returns None (never raises) if the chart
    image-export backend (kaleido) isn't available — callers skip the
    download button in that case rather than show a broken one."""
    try:
        return fig.to_image(format="png", scale=scale)
    except Exception:
        return None


def download_row(csv_data, csv_filename, fig=None, chart_filename=None, key_prefix=""):
    """Renders a 'Download data' button, and — when a figure is given and
    PNG export succeeds — a 'Download chart' button next to it."""
    png_bytes = _fig_to_png_bytes(fig) if fig is not None else None
    if png_bytes is not None:
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("⬇ Data", csv_data, file_name=csv_filename, key=f"{key_prefix}_data")
        with c2:
            st.download_button(
                "🖼 Chart", png_bytes, file_name=chart_filename or "chart.png",
                mime="image/png", key=f"{key_prefix}_chart",
            )
    else:
        st.download_button("⬇ Data", csv_data, file_name=csv_filename, key=f"{key_prefix}_data")
