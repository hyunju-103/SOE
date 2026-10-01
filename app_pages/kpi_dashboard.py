import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import calculations
from config import BAR_CORNER_RADIUS, CATEGORY_LABELS, CATEGORY_ORDER, CHART_LAYOUT, KPI_CATEGORIES, KPI_THRESHOLDS, THEME
from utils import overview as ov
from utils import theme
from utils.portfolio import latest_per_entity
from utils.charts import MINIMAL_MODEBAR_CONFIG, add_smooth_line, year_axis
from utils.filters import render_filters

theme.header(
    "PERFORMANCE MONITORING",
    "KPI Dashboard",
    "Profitability, liquidity, solvency, and fiscal-dependency ratios. Pick a "
    "ratio from each column's dropdown — thresholds are illustrative, pending "
    "recalibration.",
)

if st.session_state.get("soe_df") is None:
    st.markdown(
        '<div class="sfp-alert warn">No data loaded yet — go to the Home page and upload a file '
        'or use the example portfolio.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

df = render_filters(st.session_state.soe_df)
if df.empty:
    st.markdown('<div class="sfp-alert warn">No rows match the current filter.</div>', unsafe_allow_html=True)
    st.stop()

years_all = df["Year"].dropna()
has_years = df["Year"].nunique() > 1
# Long panels (10–20+ years): a from–to range instead of one chip per year.
# Trends are the same smooth line chart for any number of years.
if has_years:
    year_options = sorted(int(y) for y in df["Year"].unique().tolist())
    yr_from, yr_to = st.select_slider("Years", options=year_options, value=(year_options[0], year_options[-1]), key="kpi_year_range")
    df = df[(df["Year"] >= yr_from) & (df["Year"] <= yr_to)]
    if df.empty:
        st.markdown('<div class="sfp-alert warn">No rows for the selected years.</div>', unsafe_allow_html=True)
        st.stop()

df = calculations.compute_zem_components(df)
df = calculations.compute_kpis(df)
all_available = calculations.available_kpis(df)

if not all_available:
    st.markdown(
        '<div class="sfp-alert warn">None of the KPI input fields were found in your upload. '
        "Check the required columns on the Home page.</div>",
        unsafe_allow_html=True,
    )
    st.stop()


# ------------------------------------------------------------------ #
# Key figures (latest year per SOE within the filters and years)
# ------------------------------------------------------------------ #
_latest = latest_per_entity(df)
_n = len(_latest)
_many = sum(1 for _, r in _latest.iterrows()
            if sum(ov.kpi_status(r, k) == "alert" for k in all_available) >= -(-len(all_available) // 2))


def _median_tile(key, label):
    if key not in all_available:
        return None
    vals = _latest[key].dropna()
    if vals.empty:
        return theme.tile(label, "n/a", "", "no SOE has this ratio")
    v = float(vals.median())
    status = ov.RAG_STATUS.get(calculations.classify(v, key)[0])
    na = _n - len(vals)
    return theme.tile(label, ov.kpi_fmt(key, v), "", f"median of {ov.plural(len(vals), 'SOE')}{f' ({na} n/a)' if na else ''} · {ov.cut_text(key)}", status=status)


_grants = None
if "grants_to_revenue" in all_available:
    _grants = int((_latest["grants_to_revenue"] > KPI_THRESHOLDS["grants_to_revenue"]["red_cut"]).sum())
theme.stat_strip([
    theme.count_tile("SOEs with most KPIs in alert", _many, _n, f"half or more of the {len(all_available)} ratios in alert · latest year"),
    _median_tile("operating_margin", "Median operating margin"),
    _median_tile("current_ratio", "Median current ratio"),
    _median_tile("debt_to_ebitda", "Median debt / EBITDA"),
    None if _grants is None else theme.count_tile("Grant-dependent SOEs", _grants, _n,
                                                  f"grants above {KPI_THRESHOLDS['grants_to_revenue']['red_cut'] * 100:.0f}% of revenue", bad="watch"),
])


def _kpi_title(spec):
    unit_label = {"%": "%", "x": "x"}.get(spec["unit"], spec["unit"])
    return f'{spec["label"]} ({unit_label})'


def _mini_layout(fig, y_title=""):
    fig.update_layout(**CHART_LAYOUT)
    fig.update_xaxes(showgrid=False, showline=False, type="category")
    fig.update_yaxes(showgrid=True, gridcolor=THEME["border"], zeroline=False, title=y_title)
    return fig


def _format_value(value, unit):
    if pd.isna(value):
        return "—"
    return f"{value:.2f}" if unit == "x" else f"{value * 100:.1f}%"


# ------------------------------------------------------------------ #
# Section 1 — trend for one SOE
# ------------------------------------------------------------------ #

st.markdown("#### Trend for one SOE")
soe_choice = st.selectbox("SOE", sorted(df["Entity"].unique()), key="kpi_trend_soe")
d = df[df["Entity"] == soe_choice].sort_values("Year")
d_has_years = d["Year"].nunique() > 1

trend_cols = st.columns(len(CATEGORY_ORDER))
for i, cat in enumerate(CATEGORY_ORDER):
    cat_kpis = [k for k in KPI_CATEGORIES[cat] if k in all_available]
    with trend_cols[i]:
        st.markdown(f'<div class="sfp-card-compact"><div class="sfp-compact-title">{CATEGORY_LABELS[cat]}</div>', unsafe_allow_html=True)
        if not cat_kpis:
            st.markdown('<p class="sfp-kpi-desc">No ratios available in this category for the current data.</p>', unsafe_allow_html=True)
        elif not d_has_years:
            st.markdown(f'<p class="sfp-kpi-desc">Only one year of data for {soe_choice} — need at least two to plot a trend.</p>', unsafe_allow_html=True)
        else:
            chosen = st.selectbox("Ratio", cat_kpis, format_func=lambda k: _kpi_title(KPI_THRESHOLDS[k]), key=f"trend_{cat}")
            spec = KPI_THRESHOLDS[chosen]
            dd = d.dropna(subset=[chosen])
            if dd.empty:
                st.markdown('<p class="sfp-kpi-desc">No data for this ratio.</p>', unsafe_allow_html=True)
            else:
                # every year in the range on the axis (gaps where the ratio is n/a), latest point highlighted,
                # dashed lines at the alert (red) and good (green) cutoffs — as in the HTML version
                scale = 100 if spec["unit"] == "%" else 1
                years = d["Year"].astype(int).tolist()
                values = [None if pd.isna(v) else v * scale for v in d[chosen]]
                fig = go.Figure()
                fig.add_hline(y=spec["red_cut"] * scale, line_dash="dash", line_width=1.3, line_color=THEME["red"])
                fig.add_hline(y=spec["green_cut"] * scale, line_dash="dash", line_width=1.3, line_color=THEME["green"])
                fmt = "%{y:.1f}%" if spec["unit"] == "%" else "%{y:.2f}×"
                add_smooth_line(fig, years, values, color=THEME["chart_navy"], highlight_last=True, last_color=THEME["accent"],
                                hovertemplate=f"%{{x}}: {fmt}<extra></extra>")
                last_v = dd[chosen].iloc[-1] * scale
                fig.add_annotation(x=int(dd["Year"].iloc[-1]), y=last_v, text=(f"{last_v:.1f}%" if spec["unit"] == "%" else f"{last_v:.2f}×"),
                                   showarrow=False, xanchor="left", xshift=8, font=dict(size=12, color=THEME["text"]))
                _mini_layout(fig, spec["unit"])
                fig.update_xaxes(type="linear")
                year_axis(fig, years, max_ticks=3, right_pad=max(0.9, 0.28 * len(years)))  # room for the value label
                st.plotly_chart(fig, use_container_width=True, config=MINIMAL_MODEBAR_CONFIG, key=f"trendchart_{cat}")
                st.markdown(f'<p class="sfp-kpi-desc">{spec["description"]}</p>', unsafe_allow_html=True)
                st.download_button(
                    "⬇ Data", dd[["Entity", "Sector", "Year", chosen]].to_csv(index=False),
                    file_name=f"{soe_choice}_{chosen}_trend.csv", key=f"trend_dl_{cat}",
                )
        st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------ #
# Section 2 — compare across SOEs
# ------------------------------------------------------------------ #

st.markdown("#### Compare across SOEs")

if has_years:
    period_mode = st.selectbox("Period", ["Most recent year", "Specific year", "Average across years"], key="kpi_period_mode")
    if period_mode == "Most recent year":
        base = df.sort_values("Year").groupby("Entity", as_index=False).last()
    elif period_mode == "Specific year":
        years = sorted(df["Year"].unique())
        year_choice = st.selectbox("Year", years, index=len(years) - 1, key="kpi_year_choice")
        base = df[df["Year"] == year_choice]
    else:
        years = sorted(int(y) for y in df["Year"].unique())
        if len(years) > 1:
            a_from, a_to = st.select_slider("Years to average", options=years, value=(years[0], years[-1]), key="kpi_avg_years")
        else:
            a_from = a_to = years[0]
        base = df[(df["Year"] >= a_from) & (df["Year"] <= a_to)]
else:
    base = df.copy()

cmp_cols = st.columns(len(CATEGORY_ORDER))
for i, cat in enumerate(CATEGORY_ORDER):
    cat_kpis = [k for k in KPI_CATEGORIES[cat] if k in all_available]
    with cmp_cols[i]:
        st.markdown(f'<div class="sfp-card-compact"><div class="sfp-compact-title">{CATEGORY_LABELS[cat]}</div>', unsafe_allow_html=True)
        if not cat_kpis:
            st.markdown('<p class="sfp-kpi-desc">No ratios available in this category for the current data.</p>', unsafe_allow_html=True)
        else:
            chosen = st.selectbox("Ratio", cat_kpis, format_func=lambda k: _kpi_title(KPI_THRESHOLDS[k]), key=f"cmp_{cat}")
            spec = KPI_THRESHOLDS[chosen]
            agg = base.groupby(["Entity", "Sector"], as_index=False)[chosen].mean()
            plot_df = agg.dropna(subset=[chosen]).copy()
            if plot_df.empty:
                st.markdown('<p class="sfp-kpi-desc">No data for this ratio in the current selection.</p>', unsafe_allow_html=True)
            else:
                plot_df["_flag"] = plot_df[chosen].apply(lambda v: calculations.classify(v, chosen)[0])
                color_map = {"Red": THEME["red"], "Amber": THEME["amber"], "Green": THEME["chart_navy"], "No data": THEME["muted"]}
                plot_df["_color"] = plot_df["_flag"].map(color_map)
                plot_df = plot_df.sort_values(chosen)
                values = plot_df[chosen] * 100 if spec["unit"] == "%" else plot_df[chosen]

                fig = go.Figure(go.Bar(x=values, y=plot_df["Entity"], orientation="h", marker=dict(color=plot_df["_color"], cornerradius=BAR_CORNER_RADIUS)))
                fig.update_layout(**{**CHART_LAYOUT, "height": max(CHART_LAYOUT["height"], 22 * len(plot_df) + 40)})
                fig.update_xaxes(showgrid=True, gridcolor=THEME["border"], zeroline=False, title=spec["unit"])
                fig.update_yaxes(showgrid=False, showline=False, automargin=True)
                st.plotly_chart(fig, use_container_width=True, config=MINIMAL_MODEBAR_CONFIG, key=f"cmpchart_{cat}")
                st.markdown(f'<p class="sfp-kpi-desc">{spec["description"]}</p>', unsafe_allow_html=True)
                st.download_button(
                    "⬇ Data", plot_df[["Entity", "Sector", chosen]].to_csv(index=False),
                    file_name=f"{chosen}_by_soe.csv", key=f"cmp_dl_{cat}",
                )
        st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------ #
# Full scorecard
# ------------------------------------------------------------------ #

with st.expander("Full SOE scorecard (all ratios, latest year)"):
    sel_cats = st.multiselect(
        "Show categories", CATEGORY_ORDER, default=CATEGORY_ORDER,
        format_func=lambda c: CATEGORY_LABELS[c], key="scorecard_cats",
    )
    table_kpis = [k for c in sel_cats for k in KPI_CATEGORIES[c] if k in all_available]
    latest = df.sort_values("Year").groupby("Entity", as_index=False).last() if df["Year"].nunique() > 1 else df
    table_rows = []
    for _, r in latest.iterrows():
        row_html = [f"<td>{r['Entity']}</td><td>{r['Sector']}</td>"]
        for key in table_kpis:
            spec = KPI_THRESHOLDS[key]
            value = r.get(key)
            _, cls = calculations.classify(value, key)
            row_html.append(f"<td><span class='sfp-chip {cls}'>{_format_value(value, spec['unit'])}</span></td>")
        table_rows.append("<tr>" + "".join(row_html) + "</tr>")
    header_cells = "<th>SOE</th><th>Sector</th>" + "".join(f"<th>{_kpi_title(KPI_THRESHOLDS[k])}</th>" for k in table_kpis)
    st.markdown(
        f"<table class='sfp-table'><thead><tr>{header_cells}</tr></thead><tbody>{''.join(table_rows)}</tbody></table>",
        unsafe_allow_html=True,
    )
    st.download_button(
        "⬇ Download underlying data",
        latest[["Entity", "Sector", "Year"] + table_kpis].to_csv(index=False),
        file_name="kpi_scorecard.csv",
    )

st.markdown(
    """
    <div class="sfp-footnote">
    <p><b>Thresholds.</b> Illustrative IMF SOE Health Check Tool-style red/amber/green cuts —
    provisional starting points, not calibrated to a specific country sample yet.</p>
    <p><b>Suppressed ratios.</b> ROE, Debt/Equity, and Debt/EBITDA show "No data" when equity or
    EBITDA is negative — the ratio's sign flips in that case and would otherwise misleadingly
    read as "Green".</p>
    </div>
    """,
    unsafe_allow_html=True,
)
