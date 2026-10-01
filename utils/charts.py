"""Small shared helpers for chart labels and chart/data download buttons."""

import math
import textwrap

import plotly.graph_objects as go
import streamlit as st

import config


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


# ---------------------------------------------------------------------------
# Smooth line charts — the same curve as templates/app.js smoothPath
# ---------------------------------------------------------------------------
def _segment_curve(pts, tension, steps):
    """Dense points of the cardinal spline through pts [(x, y), ...]."""
    n = len(pts)
    if n <= 2:
        return [p[0] for p in pts], [p[1] for p in pts]
    h = [pts[i + 1][0] - pts[i][0] for i in range(n - 1)]
    m = [(pts[i + 1][1] - pts[i][1]) / h[i] if h[i] else 0.0 for i in range(n - 1)]
    t = [0.0] * n
    for i in range(1, n - 1):
        dx = pts[i + 1][0] - pts[i - 1][0]
        t[i] = tension * (pts[i + 1][1] - pts[i - 1][1]) / dx if dx else 0.0
    t[0] = (3 * m[0] - t[1]) / 2
    t[n - 1] = (3 * m[n - 2] - t[n - 2]) / 2
    xs, ys = [pts[0][0]], [pts[0][1]]
    for i in range(n - 1):
        (x0, y0), (x1, y1), k = pts[i], pts[i + 1], h[i] / 3
        c1, c2 = y0 + k * t[i], y1 - k * t[i + 1]
        for j in range(1, steps + 1):
            u = j / steps
            xs.append(x0 + h[i] * u)  # control points are evenly spaced in x, so x is linear in u
            ys.append((1 - u) ** 3 * y0 + 3 * (1 - u) ** 2 * u * c1 + 3 * (1 - u) * u ** 2 * c2 + u ** 3 * y1)
    return xs, ys


def smooth_xy(x, y, tension=None, steps=16):
    """x, y → dense x, y of a smooth curve through every point. Missing values
    (None/NaN) break the line: the result has None between the pieces, which
    Plotly draws as a gap."""
    tension = config.LINE_SMOOTH_TENSION if tension is None else tension
    out_x, out_y, seg = [], [], []

    def flush():
        if seg:
            if out_x:
                out_x.append(None)
                out_y.append(None)
            sx, sy = _segment_curve(seg, tension, steps)
            out_x.extend(sx)
            out_y.extend(sy)

    for xv, yv in zip(x, y):
        ok = yv is not None and not (isinstance(yv, float) and math.isnan(yv))
        if ok:
            seg.append((float(xv), float(yv)))
        else:
            flush()
            seg = []
    flush()
    return out_x, out_y


def add_smooth_line(fig, x, y, color, width=2.2, name=None, dash=None, marker_color=None, marker_size=7,
                    highlight_last=False, last_color=None, hovertemplate=None, markers=True):
    """A smooth line (drawn from smooth_xy) plus markers at the real data points,
    which carry the hover. x must be numeric (years)."""
    x, y = list(x), [None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v) for v in y]
    dx, dy = smooth_xy(x, y)
    fig.add_trace(go.Scatter(x=dx, y=dy, mode="lines", line=dict(color=color, width=width, dash=dash),
                             hoverinfo="skip", name=name, legendgroup=name, showlegend=bool(name), connectgaps=False))
    if markers:
        idx = [i for i, v in enumerate(y) if v is not None]
        last = idx[-1] if idx else None
        many = len(idx) > 15
        sizes = [(marker_size + 2 if (highlight_last and i == last) else (0 if many else marker_size)) for i in idx]
        colors = [(last_color or color) if (highlight_last and i == last) else (marker_color or color) for i in idx]
        fig.add_trace(go.Scatter(x=[x[i] for i in idx], y=[y[i] for i in idx], mode="markers",
                                 marker=dict(size=sizes, color=colors, line=dict(color="white", width=1.5)),
                                 name=name, legendgroup=name, showlegend=False,
                                 hovertemplate=hovertemplate or "%{x}: %{y:.2f}<extra></extra>"))
    return fig


def band_trace(x, lo, hi, fillcolor, name=None):
    """Filled band between two smooth edges (Monte Carlo percentile fans)."""
    tx, ty = smooth_xy(x, hi)
    bx, by = smooth_xy(x, lo)
    return go.Scatter(x=tx + bx[::-1], y=ty + by[::-1], fill="toself", fillcolor=fillcolor,
                      line=dict(color="rgba(0,0,0,0)"), hoverinfo="skip", name=name, showlegend=bool(name))


def year_axis(fig, years, labels=None, max_ticks=8, right_pad=None):
    """Numeric year axis showing every step-th year counted back from the latest.
    right_pad (in years) leaves room for an end-of-line value label."""
    years = [int(v) for v in years]
    n = len(years)
    step = max(1, math.ceil(n / max_ticks))
    keep = [i for i in range(n) if (n - 1 - i) % step == 0]
    pad = 0.35 if n > 1 else 0.5
    fig.update_xaxes(tickmode="array", tickvals=[years[i] for i in keep],
                     ticktext=[(labels[i] if labels else str(years[i])) for i in keep], showgrid=False,
                     tickangle=0, range=[min(years) - pad, max(years) + (pad if right_pad is None else right_pad)] if years else None)
    return fig
