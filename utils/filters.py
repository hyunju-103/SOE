"""
Top-bar filter. Same widget key on every page keeps the selection in sync
as you move between pages (Streamlit's session_state persists it).
"""

import streamlit as st

from config import fs


def render_filters(df):
    """Renders a compact Sector filter row and returns the filtered df.
    (Our schema has no Country column — Sector is the only cross-cutting
    grouping field, plus a 'data as of' year-range hint.)"""
    st.markdown('<div class="sfp-topbar">', unsafe_allow_html=True)
    c1, c2 = st.columns([3, 1.6])

    sectors = sorted(df["Sector"].dropna().unique().tolist())
    with c1:
        sel_sectors = st.multiselect("Sector", sectors, default=sectors, key="sel_sectors")

    scoped = df[df["Sector"].isin(sel_sectors)] if sel_sectors else df.iloc[0:0]

    with c2:
        years = scoped["Year"].dropna().unique().tolist()
        year_label = "—"
        if years:
            years_sorted = sorted(years)
            year_label = f"{years_sorted[0]:.0f}–{years_sorted[-1]:.0f}" if len(years_sorted) > 1 else f"{years_sorted[0]:.0f}"
        st.markdown(
            f'<div class="sfp-hint" style="margin-top:28px;">Data as of<br>'
            f'<b style="color:#151B2B;font-size:{fs(14)};">{year_label}</b></div>',
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)
    return scoped
