import plotly.graph_objects as go
import streamlit as st

import calculations
import narrative
import config as cfg
from config import BAR_CORNER_RADIUS, CHART_LAYOUT, GLOSSARY, LINE_SHAPE, LINE_SMOOTHING, THEME, ZONE_COLORS
from utils import theme, summary
from utils.charts import MINIMAL_MODEBAR_CONFIG, download_row, wrap_label
from utils.filters import render_filters

theme.header(
    "FINANCIAL DISTRESS SIGNAL",
    "Altman Z-EM Score",
    "The four components behind the Altman Z''-EM score, the score itself, "
    "and where each SOE sits in the distress / grey / safe distribution. "
    "Hover the ⓘ icons for plain-language definitions.",
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

df = calculations.compute_zem_components(df)
has_years = df["Year"].nunique() > 1


def _mini_layout(fig, y_title=""):
    fig.update_layout(**CHART_LAYOUT)
    fig.update_xaxes(showgrid=False, showline=False, type="category")
    fig.update_yaxes(showgrid=True, gridcolor=THEME["border"], zeroline=False, title=y_title)
    return fig


COMPONENTS = [
    ("X1", "X1: Working capital / assets"),
    ("X2", "X2: Retained earnings / assets"),
    ("X3", "X3: EBIT / assets"),
    ("X4", "X4: Equity / liabilities"),
    ("Z_EM", "Z-EM score"),
]
COMPONENT_GLOSSARY_KEY = {"X1": "X1", "X2": "X2", "X3": "X3", "X4": "X4", "Z_EM": "Z-EM score"}

# ==================================================================== #
# Component matrix — one SOE at a time
# ==================================================================== #

st.markdown("#### Altman Z-EM components")
soe_choice = st.selectbox("SOE", sorted(df["Entity"].unique()), key="z_matrix_soe")
d_full = df[df["Entity"] == soe_choice].sort_values("Year")

if len(d_full) < 2:
    st.markdown(f'<p class="sfp-hint">Only one year of data for {soe_choice} — need at least two to plot a trend.</p>', unsafe_allow_html=True)
else:
    soe_years = sorted(d_full["Year"].unique().tolist())
    if len(soe_years) > 2:
        year_range = st.select_slider("Year range", options=soe_years, value=(soe_years[0], soe_years[-1]), key="z_matrix_year_range")
        lo, hi = soe_years.index(year_range[0]), soe_years.index(year_range[1])
        d = d_full[d_full["Year"].isin(set(soe_years[lo:hi + 1]))]
    else:
        d = d_full

    def _draw_component(key, label):
        info = theme.info_icon(GLOSSARY.get(COMPONENT_GLOSSARY_KEY.get(key, ""), ""))
        st.markdown(f'<div class="sfp-card-compact"><div class="sfp-compact-title">{label} {info}</div>', unsafe_allow_html=True)
        dd = d.dropna(subset=[key])
        if dd.empty:
            st.markdown('<p class="sfp-kpi-desc">No data for this component.</p>', unsafe_allow_html=True)
        else:
            marker_color = THEME["gold"] if key == "Z_EM" else THEME["chart_navy"]
            fig = go.Figure(go.Scatter(
                x=dd["Year"].astype(int).astype(str), y=dd[key], mode="lines+markers",
                line=dict(color=THEME["chart_navy"], width=2.2, shape=LINE_SHAPE, smoothing=LINE_SMOOTHING),
                marker=dict(size=6, color=marker_color),
            ))
            if key == "Z_EM":
                fig.add_hline(y=1.1, line_dash="dash", line_width=1.3, line_color=THEME["red"])
                fig.add_hline(y=2.6, line_dash="dash", line_width=1.3, line_color=THEME["chart_cyan"])
            _mini_layout(fig)
            st.plotly_chart(fig, use_container_width=True, config=MINIMAL_MODEBAR_CONFIG, key=f"comp_{key}")
        st.markdown("</div>", unsafe_allow_html=True)

    row1, row2 = COMPONENTS[:3], COMPONENTS[3:]
    cols1 = st.columns(3)
    for (key, label), col in zip(row1, cols1):
        with col:
            _draw_component(key, label)

    cols2 = st.columns(3)
    for (key, label), col in zip(row2, cols2[:2]):
        with col:
            _draw_component(key, label)
    with cols2[2]:
        st.markdown('<div class="sfp-card-compact">', unsafe_allow_html=True)
        theme.summary_box(summary.summarize_z_trend(d, soe_choice))
        st.download_button(
            "⬇ Download underlying data",
            d[["Entity", "Sector", "Year", "X1", "X2", "X3", "X4", "Z_EM", "Zone"]].round(3).to_csv(index=False),
            file_name=f"{soe_choice}_z_components.csv",
        )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="sfp-card">', unsafe_allow_html=True)
    theme.summary_box(narrative.single_soe_narrative(d_full.iloc[-1]))
    st.markdown("</div>", unsafe_allow_html=True)

# ==================================================================== #
# Portfolio view — shared period control
# ==================================================================== #

st.markdown("#### Portfolio view")

if has_years:
    years = sorted(df["Year"].unique().tolist())
    view_mode = st.selectbox("Period", ["Most recent year", "Specific year", "Average across years"], key="fr_view_mode")
    if view_mode == "Most recent year":
        period_df = df.sort_values("Year").groupby("Entity", as_index=False).last()
        period_label = "most recent year per SOE"
    elif view_mode == "Specific year":
        year_choice = st.select_slider("Year", options=years, value=years[-1], key="fr_year_slider")
        period_df = df[df["Year"] == year_choice].copy()
        period_label = f"{year_choice:.0f}"
    else:
        a_from, a_to = st.select_slider("Years to average", options=years, value=(years[0], years[-1]), key="fr_avg_years")
        sel_years = [y for y in years if a_from <= y <= a_to]
        period_df = df[df["Year"].isin(sel_years)].groupby(["Entity", "Sector"], as_index=False)["Z_EM"].mean()
        period_df["Year"] = None
        period_label = f"average of {', '.join(f'{y:.0f}' for y in sel_years)}" if sel_years else "average (no years selected)"
else:
    period_df = df.copy()
    period_label = "all data"

period_df["Zone"] = period_df["Z_EM"].apply(calculations.classify_zone)
period_df["Rating"] = period_df["Z_EM"].apply(cfg.z_rating)
period_df = period_df.sort_values("Z_EM")

st.markdown(f'<p class="sfp-hint">Showing: <b>{period_label}</b></p>', unsafe_allow_html=True)

bc1, bc2, bc3 = st.columns([5, 5, 3])

with bc1:
    st.markdown('<div class="sfp-card"><div class="sfp-title">Benchmark across SOEs</div>', unsafe_allow_html=True)
    labels = period_df["Entity"]
    fig2 = go.Figure(go.Bar(
        y=labels, x=period_df["Z_EM"], orientation="h",
        marker=dict(color=period_df["Zone"].map(ZONE_COLORS), cornerradius=BAR_CORNER_RADIUS),
        showlegend=False,
    ))
    fig2.add_vline(x=1.1, line_dash="dash", line_width=1.5, line_color=THEME["red"])
    fig2.add_vline(x=2.6, line_dash="dash", line_width=1.5, line_color=THEME["chart_navy"])
    fig2.add_trace(go.Scatter(x=[None], y=[None], mode="lines", line=dict(color=THEME["red"], dash="dash", width=1.5), name="Distress threshold (1.1)", showlegend=True))
    fig2.add_trace(go.Scatter(x=[None], y=[None], mode="lines", line=dict(color=THEME["chart_navy"], dash="dash", width=1.5), name="Safe threshold (2.6)", showlegend=True))
    fig2.update_layout(**{**CHART_LAYOUT, "height": max(320, 22 * len(period_df) + 90), "showlegend": True, "margin": dict(l=6, r=6, t=6, b=40)})
    fig2.update_layout(legend=dict(orientation="h", y=-0.28, x=0, font=dict(size=round(10 * 1.2, 1))))
    fig2.update_xaxes(showgrid=True, gridcolor=THEME["border"], zeroline=False, title="Z-EM score")
    fig2.update_yaxes(showgrid=False, showline=False, automargin=True, tickfont=dict(size=round(10 * 1.2, 1)))
    st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
    download_row(period_df.to_csv(index=False), "altman_z_benchmark.csv", fig2, "altman_z_benchmark.png", key_prefix="bench")
    st.markdown("</div>", unsafe_allow_html=True)

with bc2:
    st.markdown('<div class="sfp-card"><div class="sfp-title">Portfolio distribution</div>', unsafe_allow_html=True)
    counts = period_df["Zone"].value_counts()
    fig3 = go.Figure(go.Pie(
        labels=counts.index, values=counts.values,
        marker=dict(colors=[ZONE_COLORS.get(z, THEME["muted"]) for z in counts.index]),
        hole=0.55, textinfo="percent", textposition="inside", texttemplate="%{percent}",
    ))
    fig3.update_layout(**{**CHART_LAYOUT, "height": 320, "showlegend": True, "margin": dict(l=10, r=10, t=10, b=30)})
    fig3.update_layout(legend=dict(orientation="h", y=-0.12, x=0, font=dict(size=round(10 * 1.2, 1))))
    st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})
    download_row(counts.rename("Count").to_csv(), "zone_distribution.csv", fig3, "zone_distribution.png", key_prefix="zone_dist")
    st.markdown("</div>", unsafe_allow_html=True)

with bc3:
    st.markdown('<div class="sfp-card"><div class="sfp-title">Summary</div>', unsafe_allow_html=True)
    theme.summary_box(summary.summarize_zone_distribution(period_df))
    st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------- Scorecard ------------------------------- #

st.markdown('<div class="sfp-card"><div class="sfp-title">Scorecard</div>', unsafe_allow_html=True)
zone_info = theme.info_icon(GLOSSARY["Zone"])
rating_info = theme.info_icon(GLOSSARY["Rating"])
rows_html = []
for _, r in period_df.iterrows():
    color = ZONE_COLORS.get(r["Zone"], THEME["muted"])
    year_display = f"{r['Year']:.0f}" if r.get("Year") == r.get("Year") and r.get("Year") is not None else "Avg"
    rows_html.append(
        f"<tr><td>{r['Entity']}</td><td>{r['Sector']}</td>"
        f"<td>{year_display}</td><td>{r['Z_EM']:.2f}</td>"
        f"<td><span class='sfp-dot' style='background:{color}'></span>{r['Zone']}</td>"
        f"<td>{r['Rating']}</td></tr>"
    )
st.markdown(
    "<table class='sfp-table'><thead><tr><th>SOE</th><th>Sector</th>"
    f"<th>Year</th><th>Z-EM</th><th>Zone {zone_info}</th><th>Rating {rating_info}</th></tr></thead><tbody>{''.join(rows_html)}</tbody></table>",
    unsafe_allow_html=True,
)
st.download_button("⬇ Download underlying data", period_df.to_csv(index=False), file_name="altman_z_scorecard.csv")
st.markdown("</div>", unsafe_allow_html=True)

st.markdown(
    """
    <div class="sfp-footnote">
    <p><b>Z-EM score.</b> Altman Z''-EM (Emerging Market, Altman et al. 2005):
    Z = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4 (no constant — Eidelman convention, matching config.ZEM_CONSTANT = 0).
    Z ≤ 1.1 = distress, 1.1–2.6 = grey zone, &gt; 2.6 = safe. Rating is an indicative
    credit-rating cohort mapping for the Z-EM score, for reference only.</p>
    </div>
    """,
    unsafe_allow_html=True,
)
