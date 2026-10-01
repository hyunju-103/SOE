import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import calculations
import config
import shocks
from utils import theme
from utils.charts import MINIMAL_MODEBAR_CONFIG, download_row, add_smooth_line, band_trace, year_axis

theme.header(
    "DYNAMIC SIMULATION",
    "Shock Scenarios & Fiscal Risk",
    "Shocks hit balance-sheet and income-statement lines directly and "
    "compound over a multi-year horizon. Toggle between a single "
    "deterministic scenario and a Monte Carlo distribution. Hover the ⓘ "
    "icons and slider labels for plain-language definitions.",
)

if st.session_state.get("soe_df") is None:
    st.markdown(
        '<div class="sfp-alert warn">No data loaded yet — go to the Home page and upload a file '
        'or use the example portfolio.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

with st.expander("What do these shocks mean?"):
    rows = "".join(
        f"<tr><td style='font-weight:700;white-space:nowrap;'>{term}</td><td>{config.GLOSSARY[term]}</td></tr>"
        for term in ["Fuel shock", "Tariff pass-through", "FX shock", "Interest rate shock",
                     "Revenue shock", "Refinancing shock", "Government arrears", "Monte Carlo simulation", "Fiscal-at-risk"]
    )
    st.markdown(f"<table class='sfp-table sfp-table-wrap'><tbody>{rows}</tbody></table>", unsafe_allow_html=True)
    st.markdown(
        '<p class="sfp-hint">Refinancing shock: the added interest cost of rolling over debt maturing soon '
        'at a stressed spread — separate from the interest-rate shock above, which repricess debt already '
        'on a floating rate. Revenue shock: rather than a flat percentage, this is expressed in standard '
        'deviations of the SOE\'s own historical revenue growth (or a sector default if it has under 3 years '
        'of data) — the standard debt-sustainability-analysis (DSA/DSF) convention.</p>',
        unsafe_allow_html=True,
    )

df = calculations.compute_zem_components(st.session_state.soe_df)

col1, col2 = st.columns(2)
with col1:
    sel_entity = st.selectbox("SOE", sorted(df["Entity"].unique()))
with col2:
    entity_years = sorted(df[df["Entity"] == sel_entity]["Year"].unique())
    sel_base_year = st.selectbox("Base year", entity_years, index=len(entity_years) - 1)

base_row = df[(df["Entity"] == sel_entity) & (df["Year"] == sel_base_year)].iloc[0]
sector = base_row.get("Sector", "Other")
# Bottom-up exposures: this SOE's own shares where its data carry them
# (observed or derived from reported amounts), else sector / generic defaults.
expo = calculations.soe_exposures(base_row)
default_fuel_share = expo["fuel_cost_share"][0]


def _src(name):
    """Caption naming where a slider's starting value came from."""
    value, source = expo[name]
    return f"Starts at {value:.0%} — {source}" if name != "revenue_elasticity" else f"Starts at {value:.1f} — {source}"

# Revenue volatility: SOE's own history if it has >=3 years, else sector default
sigma_revenue = calculations.historical_revenue_volatility(df, sel_entity)
using_sector_vol = sigma_revenue != sigma_revenue  # NaN check
if using_sector_vol:
    sigma_revenue = config.SECTOR_REVENUE_VOLATILITY.get(sector, config.SECTOR_REVENUE_VOLATILITY["Other"])
vol_source_label = "sector default" if using_sector_vol else "computed from this SOE's own history"

# --- Shock parameter calibration ----------------------------------------
st.markdown('<div class="sfp-card"><div class="sfp-title">Shock parameters</div>', unsafe_allow_html=True)
st.markdown(
    f'<p class="sfp-hint"><b>Bottom-up exposures.</b> Exposure sliders start from this SOE\'s own data where the upload '
    f'carries them (fuel, FX, floating-rate and short-term debt shares), otherwise from sector or generic defaults — the '
    f'caption under each slider says which. Revenue volatility: {sigma_revenue:.1%} ({vol_source_label}). All shock sliders '
    f'can run negative — a favorable move (cheaper fuel, a stronger currency, a rate cut, arrears clearing) as well as an adverse one.</p>',
    unsafe_allow_html=True,
)

t1, t2, t3, t4 = st.tabs(["Fuel", "FX", "Interest rate, revenue & refinancing", "Arrears & horizon"])

with t1:
    c1, c2 = st.columns(2)
    with c1:
        fuel_cost_share = st.slider("Fuel cost share of OpEx", 0.0, 0.60, float(min(0.60, default_fuel_share)), 0.01,
                                     help="What share of this SOE's operating costs is spent on fuel. Higher share = more exposed to a fuel price shock.")
        st.caption(_src("fuel_cost_share"))
        fuel_shock_pct = st.slider("Fuel price shock (%)", -50, 100, 0, 1,
                                    help=config.GLOSSARY["Fuel shock"] + " Negative means fuel gets cheaper. 0 = no shock.") / 100.0
    with c2:
        tariff_passthrough = st.slider("Tariff pass-through rate", 0.0, 1.0, float(expo["tariff_passthrough"][0]), 0.05,
                                        help=config.GLOSSARY["Tariff pass-through"] + " Case B: the cost increase reaches customers through tariffs.")
        st.caption(_src("tariff_passthrough"))
        fuel_subsidy_share = st.slider("Government subsidy share of the fuel-cost change", 0.0, 1.0, 0.0, 0.05,
                                        help="Case C: the share of the fuel-cost increase the government absorbs through a subsidy. "
                                             "It does not hit the SOE's EBIT, but it is a direct budget outlay, reported next to EFC. 0 = off.")
        if tariff_passthrough + fuel_subsidy_share > 1:
            st.markdown('<div class="sfp-alert warn">Pass-through plus subsidy exceed 100% of the cost increase — the SOE is treated as absorbing none of it.</div>', unsafe_allow_html=True)

with t2:
    c1, c2 = st.columns(2)
    with c1:
        fx_shock_pct = st.slider("FX shock (%)", -30, 60, 0, 1,
                                  help=config.GLOSSARY["FX shock"] + " Negative means the local currency strengthens. 0 = no shock.") / 100.0
        fx_cost_share = st.slider("FX share of operating costs", 0.0, 1.0, float(expo["fx_cost_share"][0]), 0.05,
                                   help="What share of this SOE's costs are paid in a foreign currency (e.g. imported fuel or equipment).")
        st.caption(_src("fx_cost_share"))
    with c2:
        fx_revenue_share = st.slider("FX share of revenue", 0.0, 1.0, float(expo["fx_revenue_share"][0]), 0.05,
                                      help="What share of this SOE's revenue is earned in a foreign currency. If this is lower than the FX cost share, a weaker local currency hurts profit.")
        st.caption(_src("fx_revenue_share"))
        fx_debt_share = st.slider("FX share of total liabilities", 0.0, 1.0, float(expo["fx_debt_share"][0]), 0.05,
                                   help="What share of this SOE's debt is denominated in a foreign currency. A weaker local currency makes this debt more expensive to repay.")
        st.caption(_src("fx_debt_share"))

with t3:
    c1, c2 = st.columns(2)
    with c1:
        floating_debt_share = st.slider("Floating-rate share of debt", 0.0, 1.0, float(expo["floating_debt_share"][0]), 0.05,
                                         help="What share of this SOE's debt has an interest rate that moves with market rates, rather than being fixed.")
        st.caption(_src("floating_debt_share"))
        rate_shock_bps = st.slider("Interest rate shock (bps)", -500, 1000, 0, 25,
                                    help=config.GLOSSARY["Interest rate shock"] + " Negative means rates fall. 0 = no shock.")
        revenue_shock_std_devs = st.slider("Revenue shock (standard deviations)", -3.0, 3.0, 0.0, 0.25,
                                            help=f"0 = no shock. The standard DSA/DSF stress-test convention is -1 std dev. "
                                                 f"This SOE's revenue volatility is {sigma_revenue:.1%} ({vol_source_label}).")
    with c2:
        revenue_elasticity = st.slider("EBIT elasticity to revenue shock", 0.0, 2.0, float(expo["revenue_elasticity"][0]), 0.10,
                                        help="How much EBIT moves for a given revenue change. 1.0 means EBIT moves 1-for-1 with revenue.")
        st.caption(_src("revenue_elasticity"))
        near_term_maturity_share = st.slider("Near-term maturity share of debt", 0.0, 1.0, float(expo["near_term_maturity_share"][0]), 0.05,
                                              help="What share of total liabilities is coming due soon and needs refinancing.")
        st.caption(_src("near_term_maturity_share"))
        refinancing_spread_bps = st.slider("Refinancing stress spread (bps)", -300, 1000, 0, 25,
                                            help="0 = no shock. The extra cost (on top of the interest-rate shock) of rolling over near-term debt in stressed conditions — rollover risk, distinct from floating-rate repricing.")

with t4:
    c1, c2 = st.columns(2)
    with c1:
        arrears_pct_of_revenue = st.slider("Government arrears accumulation (% of revenue/yr)", -0.30, 0.30, 0.0, 0.01,
                                            help=config.GLOSSARY["Government arrears"] + " Negative means the government clears existing arrears. 0 = no shock.")
    with c2:
        horizon_years = st.slider("Projection horizon (years)", 1, 7, 3,
                                   help="How many years into the future to project.")
        shock_duration_years = st.slider("Shock active duration (years)", 1, horizon_years, min(2, horizon_years),
                                          help="How many of those years the shock is actively applied. After this, the shock stops, but its effects on debt and equity built up so far carry forward.")

revenue_shock_pct = revenue_shock_std_devs * sigma_revenue

params = {
    "fuel_cost_share": fuel_cost_share, "fuel_shock_pct": fuel_shock_pct, "tariff_passthrough": tariff_passthrough,
    "fx_shock_pct": fx_shock_pct, "fx_cost_share": fx_cost_share, "fx_revenue_share": fx_revenue_share,
    "fx_debt_share": fx_debt_share, "floating_debt_share": floating_debt_share, "rate_shock_bps": rate_shock_bps,
    "revenue_shock_pct": revenue_shock_pct, "revenue_elasticity": revenue_elasticity,
    "near_term_maturity_share": near_term_maturity_share, "refinancing_spread_bps": refinancing_spread_bps,
    "arrears_pct_of_revenue": arrears_pct_of_revenue, "shock_duration_years": shock_duration_years,
    "fuel_subsidy_share": fuel_subsidy_share, "revenue_shock_std_devs": revenue_shock_std_devs,
    "revenue_sigma": sigma_revenue,
}
st.markdown("</div>", unsafe_allow_html=True)

view_mode = st.radio("View", ["Single scenario", "Distribution (Monte Carlo)"], horizontal=True)

st.markdown(f'<div class="sfp-card"><div class="sfp-title">LGD & fiscal (GDP) context {theme.info_icon(config.GLOSSARY["LGD"])}</div>', unsafe_allow_html=True)
gc1, gc2, gc3 = st.columns(3)
with gc1:
    lgd_pct = st.slider("LGD (%)", config.LGD_SLIDER_MIN, config.LGD_SLIDER_MAX, config.LGD_SLIDER_DEFAULT, help=config.GLOSSARY["LGD"])
    ead_share = st.select_slider("EAD: share of total liabilities", options=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
                                 value=config.EAD_SHARE_DEFAULT, format_func=lambda v: f"{v:.0%}", key="shock_ead_share",
                                 help="Proxy for the part of the balance sheet the government would stand behind. 100% = the original assumption; 60% / 80% are sensitivity cases.")
with gc2:
    default_gdp = float(base_row["Total Liabilities"]) * 10
    base_gdp = st.number_input(
        f"Country GDP, base year ({base_row.get('Currency', '')})",
        min_value=0.0, value=st.session_state.get("shared_base_gdp", default_gdp),
        step=default_gdp / 100 if default_gdp else 1.0,
        key="shared_base_gdp",
        help="Enter the country's actual nominal GDP for the base year — the default shown is only a placeholder scaffold. Shared with the same field on the Expected Fiscal Cost page.",
    )
with gc3:
    gdp_growth = st.slider("Assumed nominal GDP growth (%/yr)", -5.0, 15.0, config.DEFAULT_GDP_GROWTH * 100, 0.5) / 100.0
st.markdown("</div>", unsafe_allow_html=True)

# ===========================================================================
# SINGLE SCENARIO VIEW
# ===========================================================================
if view_mode == "Single scenario":
    scenario = shocks.run_scenario(base_row, params, horizon_years)
    scenario["PD"] = scenario["Rating"].apply(calculations.compute_pd_from_rating)
    scenario["EAD"] = scenario["Total Liabilities"] * ead_share
    scenario["LGD"] = lgd_pct / 100.0
    scenario["EFC"] = scenario["PD"] * scenario["EAD"] * scenario["LGD"]
    scenario["GDP"] = shocks.gdp_path(base_gdp, gdp_growth, horizon_years) if base_gdp else float("nan")
    scenario["EFC_pct_GDP"] = scenario["EFC"] / scenario["GDP"] if base_gdp else float("nan")

    base = scenario.iloc[0]
    final = scenario.iloc[-1]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(theme.stat_card("📉", "blue", "Z-EM: base → final", f"{base['Z_EM']:.2f} → {final['Z_EM']:.2f}", f"{final['Zone']} in year {horizon_years}"), unsafe_allow_html=True)
    with c2:
        st.markdown(theme.stat_card("💰", "red", "Final-year EFC", f"{final['EFC']:,.0f}"), unsafe_allow_html=True)
    with c3:
        migrated = base["Zone"] != final["Zone"]
        st.markdown(theme.stat_card("→", "amber" if migrated else "green", "Zone migration", "Yes" if migrated else "No", f"{base['Zone']} → {final['Zone']}"), unsafe_allow_html=True)
    with c4:
        efc_gdp_final = final["EFC_pct_GDP"]
        st.markdown(theme.stat_card("%", "purple", "Final-year EFC / GDP", f"{efc_gdp_final:.2%}" if efc_gdp_final == efc_gdp_final else "—", "enter GDP above to populate"), unsafe_allow_html=True)
    total_subsidy = scenario["Direct Fuel Subsidy"].sum()
    if total_subsidy:
        st.markdown(
            f'<div class="sfp-alert info">Direct fuel subsidy (Case C) over the horizon: <b>{total_subsidy:,.0f}</b> — a budget outlay '
            f'on top of the expected fiscal cost, because the government absorbs {fuel_subsidy_share:.0%} of the fuel-cost change.</div>',
            unsafe_allow_html=True,
        )
    st.markdown("<br>", unsafe_allow_html=True)

    shock_summary = shocks.describe_active_shocks(params)

    col_z, col_gdp = st.columns(2)
    with col_z:
        st.markdown('<div class="sfp-card"><div class="sfp-title">Z-EM trajectory</div>', unsafe_allow_html=True)
        fig = go.Figure()
        add_smooth_line(fig, scenario["Calendar Year"].astype(int), scenario["Z_EM"], color=config.THEME["chart_navy"],
                        marker_color=config.THEME["gold"], marker_size=8, hovertemplate="%{x}: Z″ %{y:.2f}<extra></extra>")
        year_axis(fig, scenario["Calendar Year"].astype(int))
        fig.add_hline(y=2.6, line_dash="dot", line_color=config.THEME["green"], annotation_text="Safe")
        fig.add_hline(y=1.1, line_dash="dot", line_color=config.THEME["red"], annotation_text="Distress")
        fig.update_layout(**{**config.CHART_LAYOUT, "height": 290, "margin": {**config.CHART_LAYOUT["margin"], "t": 28}})
        fig.update_layout(title=dict(text=shock_summary, x=0, xanchor="left",
                                      font=dict(size=round(9.5 * config.FONT_SCALE, 1), color=config.THEME["muted"])))
        fig.update_xaxes(title_text="Year", showgrid=False)
        fig.update_yaxes(title_text="Z-EM score", showgrid=True, gridcolor=config.THEME["border"])
        st.plotly_chart(fig, use_container_width=True, config=MINIMAL_MODEBAR_CONFIG)
        download_row(scenario.to_csv(index=False), f"scenario_{sel_entity}.csv", fig, "z_trajectory.png", key_prefix="ztraj")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_gdp:
        if base_gdp:
            st.markdown('<div class="sfp-card"><div class="sfp-title">Expected Fiscal Cost / GDP — path over time</div>', unsafe_allow_html=True)
            fig_gdp = go.Figure()
            add_smooth_line(fig_gdp, scenario["Calendar Year"].astype(int), scenario["EFC_pct_GDP"], color=config.THEME["red"],
                            marker_color=config.THEME["gold"], marker_size=8, hovertemplate="%{x}: %{y:.2%}<extra></extra>")
            year_axis(fig_gdp, scenario["Calendar Year"].astype(int))
            fig_gdp.update_layout(**{**config.CHART_LAYOUT, "height": 290, "margin": {**config.CHART_LAYOUT["margin"], "t": 28}})
            fig_gdp.update_layout(title=dict(text=shock_summary, x=0, xanchor="left",
                                              font=dict(size=round(9.5 * config.FONT_SCALE, 1), color=config.THEME["muted"])))
            fig_gdp.update_xaxes(title_text="Year", showgrid=False)
            fig_gdp.update_yaxes(title_text="EFC / GDP", tickformat=".1%", showgrid=True, gridcolor=config.THEME["border"])
            st.plotly_chart(fig_gdp, use_container_width=True, config=MINIMAL_MODEBAR_CONFIG)
            st.markdown(f'<p class="sfp-hint">GDP projected forward at {gdp_growth:.1%}/yr nominal growth. Triage-level ratio, not a budget forecast.</p>', unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown('<div class="sfp-alert info">Enter a base-year GDP figure above to see the EFC-as-%-of-GDP path.</div>', unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown('<div class="sfp-card"><div class="sfp-title">KPI impact (base → final year)</div>', unsafe_allow_html=True)
        impact = shocks.kpi_impact_table(scenario)
        st.dataframe(impact.style.format({"Base value": "{:.3f}", "Final value": "{:.3f}", "Change": "{:.3f}", "Weighted contribution to ΔZ": "{:.3f}"}), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_b:
        st.markdown('<div class="sfp-card"><div class="sfp-title">Tornado — driver of Z-EM change</div>', unsafe_allow_html=True)
        impact_sorted = impact.reindex(impact["Weighted contribution to ΔZ"].abs().sort_values().index)
        fig_tornado = go.Figure(go.Bar(
            x=impact_sorted["Weighted contribution to ΔZ"], y=impact_sorted["Component"], orientation="h",
            marker=dict(color=[config.THEME["red"] if v < 0 else config.THEME["chart_navy"] for v in impact_sorted["Weighted contribution to ΔZ"]], cornerradius=config.BAR_CORNER_RADIUS),
        ))
        fig_tornado.update_layout(**{**config.CHART_LAYOUT, "height": 280})
        fig_tornado.update_xaxes(title_text="Weighted contribution to ΔZ-EM", showgrid=True, gridcolor=config.THEME["border"])
        fig_tornado.update_yaxes(title_text="")
        st.plotly_chart(fig_tornado, use_container_width=True, config=MINIMAL_MODEBAR_CONFIG)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="sfp-card"><div class="sfp-title">Full projection</div>', unsafe_allow_html=True)
    display_cols = ["Calendar Year", "EBIT", "Equity", "Total Liabilities", "Z_EM", "Zone", "PD", "EFC"]
    fmt = {"EBIT": "{:,.0f}", "Equity": "{:,.0f}", "Total Liabilities": "{:,.0f}", "Z_EM": "{:.2f}", "PD": "{:.2%}", "EFC": "{:,.0f}"}
    if total_subsidy:
        display_cols.append("Direct Fuel Subsidy")
        fmt["Direct Fuel Subsidy"] = "{:,.0f}"
    if base_gdp:
        display_cols += ["GDP", "EFC_pct_GDP"]
        fmt["GDP"] = "{:,.0f}"
    display_df_proj = scenario[display_cols].rename(columns={"EFC_pct_GDP": "EFC / GDP"})
    if base_gdp:
        fmt["EFC / GDP"] = "{:.2%}"
    st.dataframe(display_df_proj.style.format(fmt), use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        """
        <div class="sfp-footnote">
        <p><b>Simplifications.</b> Tax Expense and Current Liabilities held flat across the horizon;
        Net Income carries the reported figure plus the shock's effect on EBIT and interest; losses assumed debt-financed. See
        shocks.py for full documentation.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ===========================================================================
# DISTRIBUTION (MONTE CARLO) VIEW
# ===========================================================================
else:
    st.markdown(f'<div class="sfp-card"><div class="sfp-title">Monte Carlo settings {theme.info_icon(config.GLOSSARY["Monte Carlo simulation"])}</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        n_sims = st.slider("Simulations", 100, 5000, config.MC_DEFAULT_SIMULATIONS, 100,
                            help="How many random shock draws to run. More simulations give a smoother distribution but take longer to compute.")
    with c2:
        fuel_std = st.slider("Fuel shock std. dev.", 0.01, 0.30, config.MC_DEFAULT_FUEL_STD, 0.01,
                              help="How much the fuel shock varies across simulations, centered on the Fuel tab's slider value. Higher = wider range of scenarios tested.")
    with c3:
        fx_std = st.slider("FX shock std. dev.", 0.01, 0.30, config.MC_DEFAULT_FX_STD, 0.01,
                            help="How much the FX shock varies across simulations, centered on the FX tab's slider value.")
    c4, c5 = st.columns(2)
    with c4:
        rate_std = st.slider("Interest-rate shock std. dev. (bps)", 0, 500, int(config.MC_DEFAULT_RATE_STD_BPS), 25,
                             help="0 = the rate shock stays at the slider value in every simulation. Above 0, it is drawn too, centred on the slider value.")
    with c5:
        revenue_std = st.slider("Revenue shock std. dev. (standard deviations)", 0.0, 2.0, float(config.MC_DEFAULT_REVENUE_STD_SD), 0.1,
                                help="0 = the revenue shock stays at the slider value. Above 0, it is drawn too, in units of this SOE's revenue-growth volatility.")
    names = ["fuel", "fx"] + (["rate"] if rate_std > 0 else []) + (["revenue"] if revenue_std > 0 else [])
    nice_name = {"fuel": "Fuel", "fx": "FX", "rate": "Interest rate", "revenue": "Revenue"}
    pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
    st.markdown('<p class="sfp-hint" style="margin-bottom:0"><b>Correlations between the drawn shocks</b> — placeholders until estimated from country data '
                '(e.g. oil price ↑ → FX pressure → depreciation → rates ↑).</p>', unsafe_allow_html=True)
    correlations = {}
    corr_cols = st.columns(min(3, len(pairs)))
    for k, (a, b) in enumerate(pairs):
        with corr_cols[k % len(corr_cols)]:
            correlations[f"{a}|{b}"] = st.slider(f"{nice_name[a]}–{nice_name[b]}", -1.0, 1.0,
                                                  float(config.MC_DEFAULT_CORRELATIONS.get(f"{a}|{b}", 0.0)), 0.05, key=f"corr_{a}_{b}")
    correlation = correlations["fuel|fx"]
    st.markdown(
        f'<p class="sfp-hint">Draws are centered on the shock sliders above '
        f'(mean fuel shock = {fuel_shock_pct:.0%}, mean FX shock = {fx_shock_pct:.0%}'
        + (f", mean rate shock = {rate_shock_bps:+.0f} bps" if rate_std > 0 else "")
        + (f", mean revenue shock = {revenue_shock_std_devs:+.2f} s.d." if revenue_std > 0 else "")
        + ') with the standard deviations set here; every other parameter stays at its slider value.</p>', unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    try:
        with st.spinner(f"Running {n_sims} simulations..."):
            mc = shocks.run_monte_carlo(base_row, params, n_sims=n_sims, fuel_std=fuel_std, fx_std=fx_std,
                                         correlation=correlation, horizon_years=horizon_years, lgd_pct=lgd_pct,
                                         rate_std_bps=rate_std, revenue_std_sd=revenue_std, correlations=correlations,
                                         ead_share=ead_share)
    except ValueError as e:
        st.markdown(f'<div class="sfp-alert warn">{e}</div>', unsafe_allow_html=True)
        st.stop()

    mc_final = mc[mc["Projection Year"] == horizon_years]
    p50_efc = mc_final["EFC"].quantile(0.50)
    p95_efc = mc_final["EFC"].quantile(0.95)
    pct_distress = (mc_final["Zone"] == "Distress").mean()
    gdp_final = shocks.gdp_path(base_gdp, gdp_growth, horizon_years)[-1] if base_gdp else None

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(theme.stat_card("~", "blue", f"Median EFC (year {horizon_years})", f"{p50_efc:,.0f}"), unsafe_allow_html=True)
    with c2:
        st.markdown(theme.stat_card("⚠️", "red", "Fiscal-at-risk (95th pct.)", f"{p95_efc:,.0f}", config.GLOSSARY["Fiscal-at-risk"]), unsafe_allow_html=True)
    with c3:
        st.markdown(theme.stat_card("%", "amber", "Simulations ending in Distress", f"{pct_distress:.0%}"), unsafe_allow_html=True)
    with c4:
        st.markdown(theme.stat_card("%", "purple", "Fiscal-at-risk / GDP", f"{(p95_efc/gdp_final):.2%}" if gdp_final else "—", "enter GDP above"), unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown('<div class="sfp-card"><div class="sfp-title">Z-EM distribution (final year)</div>', unsafe_allow_html=True)
        fig_hist = px.histogram(mc_final, x="Z_EM", nbins=40, color_discrete_sequence=[config.THEME["chart_navy"]])
        fig_hist.add_vline(x=2.6, line_dash="dot", line_color=config.THEME["green"])
        fig_hist.add_vline(x=1.1, line_dash="dot", line_color=config.THEME["red"])
        fig_hist.update_layout(**{**config.CHART_LAYOUT, "height": 280})
        fig_hist.update_xaxes(title_text="Z-EM score (final year)")
        fig_hist.update_yaxes(title_text="Simulations")
        st.plotly_chart(fig_hist, use_container_width=True, config=MINIMAL_MODEBAR_CONFIG)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_b:
        st.markdown('<div class="sfp-card"><div class="sfp-title">Zone distribution across simulations</div>', unsafe_allow_html=True)
        zc = mc_final["Zone"].value_counts().reset_index()
        zc.columns = ["Zone", "Count"]
        fig_pie = px.pie(zc, names="Zone", values="Count", color="Zone", color_discrete_map=config.ZONE_COLORS, hole=0.55)
        fig_pie.update_layout(**{**config.CHART_LAYOUT, "height": 280, "showlegend": True})
        st.plotly_chart(fig_pie, use_container_width=True, config=MINIMAL_MODEBAR_CONFIG)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="sfp-card"><div class="sfp-title">Expected Fiscal Cost distribution (final year)</div>', unsafe_allow_html=True)
    fig_efc = px.histogram(mc_final, x="EFC", nbins=40, color_discrete_sequence=[config.THEME["chart_cyan"]])
    fig_efc.add_vline(x=p95_efc, line_dash="dash", line_color=config.THEME["red"], annotation_text="95th pct. (fiscal-at-risk)")
    fig_efc.update_layout(**{**config.CHART_LAYOUT, "height": 280})
    fig_efc.update_xaxes(title_text=f"Expected Fiscal Cost ({base_row.get('Currency', '')})")
    fig_efc.update_yaxes(title_text="Simulations")
    st.plotly_chart(fig_efc, use_container_width=True, config=MINIMAL_MODEBAR_CONFIG)
    download_row(mc.to_csv(index=False), f"monte_carlo_{sel_entity}.csv", fig_efc, "efc_distribution.png", key_prefix="efcdist")
    st.markdown("</div>", unsafe_allow_html=True)

    if base_gdp:
        st.markdown('<div class="sfp-card"><div class="sfp-title">Expected Fiscal Cost / GDP — percentile path over time</div>', unsafe_allow_html=True)
        efc_path = shocks.mc_percentile_path(mc, "EFC")
        gdp_series = shocks.gdp_path(base_gdp, gdp_growth, horizon_years)
        for col in ["p5", "p25", "p50", "p75", "p95"]:
            efc_path[col] = efc_path[col] / efc_path["Projection Year"].map(lambda t: gdp_series[t])

        fixed_params = dict(params)
        fixed_params["fuel_shock_pct"] = 0.0
        fixed_params["fx_shock_pct"] = 0.0
        fixed_summary = shocks.describe_active_shocks(fixed_params)
        mc_summary = (
            f"Fuel ~N({fuel_shock_pct*100:+.0f}%, {fuel_std*100:.0f}%), FX ~N({fx_shock_pct*100:+.0f}%, {fx_std*100:.0f}%), "
            f"corr={correlation:.2f}"
            + ("" if fixed_summary == "No shock applied (baseline)" else f" | fixed: {fixed_summary}")
        )

        fig_fan = go.Figure()
        fan_years = efc_path["Calendar Year"].astype(int).tolist()
        fig_fan.add_trace(band_trace(fan_years, efc_path["p5"].tolist(), efc_path["p95"].tolist(), config.THEME["chart_cyan_bg"], name="5th–95th pct."))
        add_smooth_line(fig_fan, fan_years, efc_path["p50"], color=config.THEME["red"], marker_color=config.THEME["gold"], marker_size=7,
                        name="Median", hovertemplate="%{x}: median %{y:.2%}<extra></extra>")
        year_axis(fig_fan, fan_years)
        fig_fan.update_layout(**{**config.CHART_LAYOUT, "height": 310, "showlegend": True, "margin": {**config.CHART_LAYOUT["margin"], "t": 28}})
        fig_fan.update_layout(title=dict(text=mc_summary, x=0, xanchor="left",
                                          font=dict(size=round(9.5 * config.FONT_SCALE, 1), color=config.THEME["muted"])))
        fig_fan.update_xaxes(title_text="Year")
        fig_fan.update_yaxes(title_text="EFC / GDP", tickformat=".1%")
        st.plotly_chart(fig_fan, use_container_width=True, config=MINIMAL_MODEBAR_CONFIG)
        st.markdown(f'<p class="sfp-hint">Band shows the 5th–95th percentile of simulated EFC/GDP by year; GDP projected at {gdp_growth:.1%}/yr.</p>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown('<div class="sfp-alert info">Enter a base-year GDP figure above to see the EFC-as-%-of-GDP percentile path.</div>', unsafe_allow_html=True)

    st.markdown('<div class="sfp-card"><div class="sfp-title">Percentile summary (final year)</div>', unsafe_allow_html=True)
    pctiles = mc_final[["Z_EM", "EFC"]].quantile([0.05, 0.25, 0.50, 0.75, 0.95]).rename(
        index={0.05: "5th", 0.25: "25th", 0.50: "Median", 0.75: "75th", 0.95: "95th"}
    )
    st.dataframe(pctiles.style.format({"Z_EM": "{:.2f}", "EFC": "{:,.0f}"}), use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        """
        <div class="sfp-footnote">
        <p><b>Draws.</b> Fuel and FX shock magnitudes — and the interest-rate and revenue shocks when their
        standard deviations are above zero — are drawn from a correlated normal distribution; all other
        parameters (tariff pass-through, subsidy share, exposure shares, arrears) are held fixed at the values
        set in the Shock Parameters panel above. Shocks follow a step profile: full size while active, then off.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
