import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import calculations
import config as cfg
from config import BAR_CORNER_RADIUS, CHART_LAYOUT, GLOSSARY, LGD_SLIDER_DEFAULT, LGD_SLIDER_MAX, LGD_SLIDER_MIN, SECTOR_LGD_REFERENCE, THEME, ZONE_COLORS
from utils import theme
from utils.charts import MINIMAL_MODEBAR_CONFIG, download_row
from utils.charts import wrap_label as charts_wrap_label
from utils.filters import render_filters

theme.header(
    "FISCAL EXPOSURE",
    "Expected Fiscal Cost",
    "EFC = PD × EAD × LGD — PD from each SOE's own Z-EM-derived rating "
    "(20-band cohort table), EAD proxied by Total Liabilities, LGD set by "
    "you below. Hover the ⓘ icons for plain-language definitions.",
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

years = sorted(df["Year"].unique().tolist()) if has_years else [df["Year"].iloc[0]]
sel_year = st.selectbox("Year", years, index=len(years) - 1)
view = df[df["Year"] == sel_year].copy() if has_years else df.copy()

st.markdown(
    f'<div class="sfp-card"><div class="sfp-title">LGD calibration {theme.info_icon(GLOSSARY["LGD"])}</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p class="sfp-hint">Sector reference LGD (government), from GEMs public-lending recovery data '
    '1994–2024 — lender recovery rate is taken directly as government LGD, on the reasoning that a '
    'high lender recovery reflects a large government backstop, not a small government loss:</p>',
    unsafe_allow_html=True,
)
ref_rows = "".join(
    f"<tr><td>{s}</td><td>{cfg.SECTOR_RECOVERY_DATA[s]['average']*100:.1f}%</td>"
    f"<td>{lo*100:.0f}%–{hi*100:.0f}%</td><td>{cfg.SECTOR_RECOVERY_DATA[s]['n_defaults']}</td>"
    f"<td>{cfg.SECTOR_RECOVERY_DATA[s]['gems_source']}</td></tr>"
    for s, (lo, hi) in SECTOR_LGD_REFERENCE.items()
)
st.markdown(
    f"<table class='sfp-table'><thead><tr><th>Sector</th><th>Average LGD</th><th>10th–90th pct. range</th>"
    f"<th>Defaults (n)</th><th>GEMs source</th></tr></thead>"
    f"<tbody>{ref_rows}</tbody></table>",
    unsafe_allow_html=True,
)
st.markdown(f'<div class="sfp-title" style="margin-top:14px">Exposure at default {theme.info_icon(GLOSSARY["EAD"])}</div>', unsafe_allow_html=True)
has_guarantees = "Government Guaranteed Debt" in view.columns and pd.to_numeric(view["Government Guaranteed Debt"], errors="coerce").notna().any()
eb1, eb2 = st.columns(2)
with eb1:
    ead_choice = st.radio(
        "EAD basis",
        ["Share of total liabilities (proxy)", "Government-guaranteed debt (observed where available)"],
        help="Guaranteed debt is used for the SOEs whose data carry it; the others fall back to the proxy. Every row's source is shown in the results table.",
    )
with eb2:
    ead_share = st.select_slider("Share of total liabilities", options=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0], value=cfg.EAD_SHARE_DEFAULT,
                                 format_func=lambda v: f"{v:.0%}", key="efc_ead_share",
                                 help="100% reproduces the original EAD = total liabilities. 60% / 80% are the sensitivity cases for SOEs without guarantee data.")
ead_basis = "guaranteed_debt" if ead_choice.startswith("Government") else "total_liabilities"
if ead_basis == "guaranteed_debt" and not has_guarantees:
    st.markdown('<div class="sfp-alert info">No Government Guaranteed Debt column in this data — every SOE uses the proxy.</div>', unsafe_allow_html=True)

lgd_mode = st.radio("LGD input mode", ["Single LGD for all SOEs", "Per-SOE LGD"], horizontal=True)

if lgd_mode == "Single LGD for all SOEs":
    lgd_pct = st.slider("LGD (%)", LGD_SLIDER_MIN, LGD_SLIDER_MAX, LGD_SLIDER_DEFAULT, help=GLOSSARY["LGD"])
    result = calculations.compute_efc(view, lgd_pct, ead_share=ead_share, ead_basis=ead_basis)
else:
    lgd_values = {}
    cols = st.columns(min(4, len(view["Entity"].unique())) or 1)
    for i, entity in enumerate(sorted(view["Entity"].unique())):
        with cols[i % len(cols)]:
            lgd_values[entity] = st.slider(f"{entity} LGD (%)", LGD_SLIDER_MIN, LGD_SLIDER_MAX, LGD_SLIDER_DEFAULT, key=f"lgd_{entity}", help=GLOSSARY["LGD"])
    result = calculations.compute_efc(view, LGD_SLIDER_DEFAULT, ead_share=ead_share, ead_basis=ead_basis)
    result["LGD"] = result["Entity"].map(lgd_values) / 100.0
    result["EFC"] = result["PD"] * result["EAD"] * result["LGD"]
st.markdown("</div>", unsafe_allow_html=True)

total_efc = result["EFC"].sum()
currency = df["Currency"].iloc[0] if "Currency" in df.columns else ""
n_distress = (result["Zone"] == "Distress").sum()

s1, s2, s3 = st.columns(3)
with s1:
    st.markdown(theme.stat_card("💰", "red", f"Aggregate EFC ({currency})", f"{total_efc:,.0f}", GLOSSARY["EFC"]), unsafe_allow_html=True)
with s2:
    st.markdown(theme.stat_card("⚠️", "amber", "SOEs in Distress zone", f"{n_distress}", GLOSSARY["Zone"]), unsafe_allow_html=True)
with s3:
    st.markdown(theme.stat_card("Σ", "blue", "SOEs assessed", f"{result['Entity'].nunique()}"), unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

# --- Optional GDP context, shared with the Shock Scenarios page's GDP field ---
st.markdown('<div class="sfp-card"><div class="sfp-title">Fiscal (GDP) context — optional</div>', unsafe_allow_html=True)
default_gdp = float(view["Total Liabilities"].sum()) * 5
base_gdp = st.number_input(
    f"Country GDP, {sel_year} ({currency})", min_value=0.0,
    value=st.session_state.get("shared_base_gdp", default_gdp), step=default_gdp / 100 if default_gdp else 1.0,
    key="shared_base_gdp",
    help="Enter the country's actual nominal GDP to express EFC as a % of GDP below. Shared with the same field on the Shock Scenarios page.",
)
st.markdown("</div>", unsafe_allow_html=True)

unit_label = "% of GDP" if base_gdp else f"EFC ({currency})"

col_bench, col_sens = st.columns(2)

with col_bench:
    st.markdown('<div class="sfp-card"><div class="sfp-title">EFC by SOE</div>', unsafe_allow_html=True)
    plot_df = result.sort_values("EFC", ascending=False)
    y_vals = (plot_df["EFC"] / base_gdp) if base_gdp else plot_df["EFC"]
    fig = go.Figure(go.Bar(
        x=plot_df["Entity"], y=y_vals,
        marker=dict(color=plot_df["Zone"].map(ZONE_COLORS), cornerradius=BAR_CORNER_RADIUS),
    ))
    fig.update_layout(**{**CHART_LAYOUT, "height": 300})
    fig.update_xaxes(showgrid=False, showline=False)
    fig.update_yaxes(showgrid=True, gridcolor=THEME["border"], zeroline=False, title=unit_label,
                      tickformat=".1%" if base_gdp else None)
    st.plotly_chart(fig, use_container_width=True, config=MINIMAL_MODEBAR_CONFIG)
    download_row(result.to_csv(index=False), f"efc_{sel_year}.csv", fig, "efc_by_soe.png", key_prefix="efc")
    st.markdown('<p class="sfp-hint">Benchmarks every SOE against each other at its own current LGD assumption.</p>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with col_sens:
    sens_tooltip = (
        "How much the EFC estimate for one SOE depends on the government backstop intensity "
        "assumption — how much of similar lenders' losses the government has historically had to "
        "absorb for this sector — holding PD at two reference levels: the SOE's own current PD, "
        "and the worst-case (Distress-zone) PD."
    )
    st.markdown(
        f'<div class="sfp-card"><div class="sfp-title">Government backstop sensitivity — one SOE '
        f'{theme.info_icon(sens_tooltip)}</div>',
        unsafe_allow_html=True,
    )
    sens_entity = st.selectbox("SOE", sorted(view["Entity"].unique()), key="sens_soe")
    sens_row = view[view["Entity"] == sens_entity].iloc[0]
    scenarios = calculations.recovery_rate_scenarios(sens_row.get("Sector", "Other"))

    ead = result.loc[result["Entity"] == sens_entity, "EAD"].iloc[0]
    pd_avg = calculations.compute_pd_from_rating(sens_row["Rating"])
    pd_max = cfg.worst_pd_in_zone(sens_row["Zone"])
    is_floor_rating = sens_row["Rating"] == "D"

    # This SOE's actual current baseline (whatever LGD is active for it above
    # — single slider or its own per-SOE slider), so the two charts can be
    # read against each other directly.
    baseline_row = result[result["Entity"] == sens_entity].iloc[0]
    baseline_lgd_pct = baseline_row["LGD"] * 100
    baseline_efc = baseline_row["EFC"] / base_gdp if base_gdp else baseline_row["EFC"]

    labels_raw = [s[0] for s in scenarios]
    labels = [charts_wrap_label(l, 10) for l in labels_raw]
    efc_avg = [pd_avg * ead * lgd for _, lgd in scenarios]
    efc_max = [pd_max * ead * lgd for _, lgd in scenarios]
    if base_gdp:
        efc_avg = [v / base_gdp for v in efc_avg]
        efc_max = [v / base_gdp for v in efc_max]

    val_fmt = (lambda v: f"{v:.2%}") if base_gdp else (lambda v: f"{v:,.2f}")

    fig_sens = go.Figure()
    fig_sens.add_trace(go.Bar(
        x=labels, y=efc_avg, name=f"Average PD ({sens_row['Rating']} rating, {pd_avg:.2%})",
        marker=dict(color=THEME["chart_navy"], cornerradius=BAR_CORNER_RADIUS),
        text=[val_fmt(v) for v in efc_avg], textposition="outside",
    ))
    if not is_floor_rating:
        fig_sens.add_trace(go.Scatter(
            x=labels, y=efc_max, name=f"Maximum PD (worst rating in {sens_row['Zone']} zone, {pd_max:.2%})", mode="markers+text",
            marker=dict(symbol="diamond", size=13, color=THEME["red"]),
            text=[val_fmt(v) for v in efc_max], textposition="top center",
        ))
    fig_sens.add_hline(
        y=baseline_efc, line_dash="dash", line_color=THEME["gold"], line_width=2,
        annotation_text=f"Current baseline (LGD={baseline_lgd_pct:.0f}%)", annotation_position="top left",
        annotation_font=dict(size=round(9.5 * 1.2, 1), color=THEME["gold"]),
    )
    fig_sens.update_layout(**{**CHART_LAYOUT, "height": 340, "margin": dict(l=6, r=6, t=50, b=70), "showlegend": True})
    fig_sens.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=round(9.5 * 1.2, 1))))
    fig_sens.update_xaxes(title_text="Government backstop intensity", title_standoff=15, showgrid=False, tickfont=dict(size=round(10 * 1.2, 1)))
    fig_sens.update_yaxes(title_text=unit_label, showgrid=True, gridcolor=THEME["border"], zeroline=False,
                           tickformat=".1%" if base_gdp else None)
    st.plotly_chart(fig_sens, use_container_width=True, config=MINIMAL_MODEBAR_CONFIG)
    sens_df = pd.DataFrame({"Scenario": labels_raw, "LGD": [lgd for _, lgd in scenarios],
                             "EFC (avg PD)": efc_avg, "EFC (max PD)": efc_max})
    download_row(sens_df.to_csv(index=False), f"recovery_sensitivity_{sens_entity}.csv", fig_sens,
                 f"recovery_sensitivity_{sens_entity}.png", key_prefix="sens")
    sector_n = cfg.SECTOR_RECOVERY_DATA.get(sens_row.get("Sector", "Other"), cfg.SECTOR_RECOVERY_DATA["Other"])["n_defaults"]
    max_pd_note = (
        "Maximum PD is omitted here — this SOE is already rated D, the worst possible rating, "
        "so Average and Maximum PD would coincide and the diamond would just sit on the bar."
        if is_floor_rating else
        "<b>Maximum PD</b> is an interim placeholder — the worst PD among all ratings that fall "
        "within this SOE's current zone — pending a dedicated maximum-PD reference table."
    )
    st.markdown(
        f'<p class="sfp-hint">From GEMs\' actual 10th/25th/average/90th-percentile recovery-rate '
        f'distribution for {sens_row.get("Sector","Other")} (n={sector_n} defaults) — real distribution '
        f'points, not an interpolation. Lender recovery rate is taken directly as government LGD: '
        f'<b>High</b> backstop intensity means the government has historically had to absorb more for '
        f'this sector, not less — so EFC rises from Low to High here, the opposite of what "recovery '
        f'rate" language alone would suggest. <b>Average PD</b> is this SOE\'s own rating-specific 1-yr PD '
        f'from the Z-EM rating cohort table. The gold dashed line is this SOE\'s current baseline EFC '
        f'from the card on the left — it won\'t generally land on one of the four bars, since the '
        f'baseline uses whatever LGD you set above, not necessarily one of these four calibrated points. '
        f'{max_pd_note} This is a static what-if on the backstop assumption, not the dynamic shock module.</p>',
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown('<div class="sfp-card"><div class="sfp-title">EFC results</div>', unsafe_allow_html=True)
st.markdown(
    f'<p class="sfp-hint">PD {theme.info_icon(GLOSSARY["PD"])} · EAD {theme.info_icon(GLOSSARY["EAD"])} · '
    f'LGD {theme.info_icon(GLOSSARY["LGD"])} · EFC {theme.info_icon(GLOSSARY["EFC"])}</p>',
    unsafe_allow_html=True,
)
display_cols = ["Entity", "Sector", "Zone", "Z_EM", "PD", "EAD", "EAD_source", "LGD", "EFC"]
st.dataframe(
    result[display_cols].style.format({"Z_EM": "{:.2f}", "PD": "{:.2%}", "EAD": "{:,.0f}", "LGD": "{:.0%}", "EFC": "{:,.0f}"}),
    use_container_width=True,
)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown(
    """
    <div class="sfp-footnote">
    <p><b>Triage-level estimate, not a budget forecast.</b> PD is each SOE's own 1-yr PD from the
    Z-EM rating cohort table (20 rating bands, AAA...D), not a flat zone value — a placeholder
    pending probit-estimated probabilities from panel data. EAD is either observed government-guaranteed
    debt (where the data carry it) or a share of total liabilities — a proxy, with 60% / 80% / 100% as
    sensitivity cases. The EAD_source column says which applies to each SOE.</p>
    </div>
    """,
    unsafe_allow_html=True,
)
