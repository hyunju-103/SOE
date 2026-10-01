import pandas as pd
import streamlit as st

import calculations
import config
from utils import theme

theme.header(
    "GOVERNMENT SUPPORT",
    "Strategic SOEs & Government-Related Entity Uplift",
    "A simplified, editable stand-in for S&P Global Ratings' Government-Related "
    "Entity (GRE) methodology: how important is this SOE to the government "
    "(Role), and how tightly linked (Link)? Together they set a bounded "
    "uplift above the SOE's own Z-EM-derived rating — capped by the "
    "sovereign's own rating, and automatically tightened if the SOE's "
    "rating is falling fast or the sovereign's outlook turns negative.",
)

if st.session_state.get("soe_df") is None:
    st.markdown(
        '<div class="sfp-alert warn">No data loaded yet — go to the Home page and upload a file '
        'or use the example portfolio.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

with st.expander("What do Role, Link, and this uplift mean?"):
    st.markdown(
        '<p class="sfp-hint">This is a simplified, transparent stand-in for S&P Global Ratings\' '
        '"Rating Government-Related Entities" methodology (25-Mar-2015) — not a reproduction of '
        'their actual Role-Link matrix or notching tables, which weren\'t available to transcribe. '
        'It follows the same two-dimensional logic on the same rating scale.</p>',
        unsafe_allow_html=True,
    )
    role_rows = "".join(f"<tr><td style='font-weight:700;white-space:nowrap;'>{r}</td><td>{config.ROLE_CRITERIA[r]}</td></tr>" for r in config.ROLE_LEVELS)
    link_rows = "".join(f"<tr><td style='font-weight:700;white-space:nowrap;'>{l}</td><td>{config.LINK_CRITERIA[l]}</td></tr>" for l in config.LINK_LEVELS)
    st.markdown("**Role** — how important is a default of this SOE to the government?", unsafe_allow_html=True)
    st.markdown(f"<table class='sfp-table sfp-table-wrap'><tbody>{role_rows}</tbody></table>", unsafe_allow_html=True)
    st.markdown("**Link** — how tightly bound is the government to this SOE?", unsafe_allow_html=True)
    st.markdown(f"<table class='sfp-table sfp-table-wrap'><tbody>{link_rows}</tbody></table>", unsafe_allow_html=True)
    st.markdown(
        f'<p class="sfp-hint">Role and Link combine into a likelihood-of-support tier '
        f'({", ".join(config.LIKELIHOOD_TIERS_ASC)}), which sets the maximum notch uplift above '
        f'the SOE\'s own rating — always capped so the uplifted rating stays at or below the '
        f'sovereign\'s own rating. If the SOE\'s rating has fallen by '
        f'{config.DYNAMIC_CAP_TRIGGER_NOTCHES}+ notches across its available years, or the sovereign '
        f'outlook is Negative, the tier is automatically capped at "{config.DYNAMIC_CAP_TIER}" '
        f'regardless of the Role/Link inputs — so an optimistic support assumption can\'t stay frozen '
        f'while the underlying SOE deteriorates.</p>',
        unsafe_allow_html=True,
    )

df = calculations.compute_zem_components(st.session_state.soe_df)
# key figures sit at the top of the page; they are filled in after the per-SOE assessment below
strip_box = st.container()

# --- Sovereign context (single country per session) -----------------------
st.markdown('<div class="sfp-card"><div class="sfp-title">Sovereign context</div>', unsafe_allow_html=True)
st.markdown(
    '<p class="sfp-hint">Set once per session for the country these SOEs sit in — check S&P\'s current '
    'sovereign ratings list rather than relying on a hardcoded table that would go stale. This scopes '
    'the tool to one country at a time; a multi-country portfolio needs a separate pass per country.</p>',
    unsafe_allow_html=True,
)
sc1, sc2 = st.columns(2)
with sc1:
    sovereign_rating = st.selectbox("Sovereign rating (local currency, long-term)", config.SOVEREIGN_RATING_OPTIONS,
                                     index=config.SOVEREIGN_RATING_OPTIONS.index("BB") if "BB" in config.SOVEREIGN_RATING_OPTIONS else 0)
with sc2:
    sovereign_outlook = st.selectbox("Sovereign outlook", config.SOVEREIGN_OUTLOOK_OPTIONS, index=0)
st.markdown("</div>", unsafe_allow_html=True)

sovereign_idx = config.rating_index(sovereign_rating)

# --- Per-SOE Role / Link assessment ---------------------------------------
st.markdown("#### Per-SOE assessment")
entities = sorted(df["Entity"].unique())
results = []

for entity in entities:
    d_entity = df[df["Entity"] == entity].sort_values("Year")
    latest = d_entity.iloc[-1]
    sacp_rating = latest["Rating"]
    sacp_idx = config.rating_index(sacp_rating)

    with st.expander(f"{entity} — {latest.get('Sector', '')} (own rating: {sacp_rating})"):
        rc1, rc2 = st.columns(2)
        with rc1:
            role = st.selectbox("Role", config.ROLE_LEVELS, key=f"role_{entity}",
                                 help=config.ROLE_CRITERIA[config.ROLE_LEVELS[0]])
        with rc2:
            link = st.selectbox("Link", config.LINK_LEVELS, key=f"link_{entity}",
                                 help=config.LINK_CRITERIA[config.LINK_LEVELS[0]])

        tier = config.role_link_to_likelihood(role, link)

        # Dynamic cap checks
        first_rating, last_rating, notch_change = calculations.rating_notch_change(df, entity)
        cap_triggers = []
        if notch_change is not None and notch_change <= -config.DYNAMIC_CAP_TRIGGER_NOTCHES:
            cap_triggers.append(f"rating fell {abs(notch_change)} notches ({first_rating} → {last_rating})")
        if sovereign_outlook == "Negative":
            cap_triggers.append("sovereign outlook is Negative")

        tier_order = config.LIKELIHOOD_TIERS_ASC
        if cap_triggers and tier_order.index(tier) > tier_order.index(config.DYNAMIC_CAP_TIER):
            capped_tier = config.DYNAMIC_CAP_TIER
        else:
            capped_tier = tier

        uplift_spec = config.LIKELIHOOD_UPLIFT[capped_tier]
        max_notches = uplift_spec["max_notches"]
        min_gap = uplift_spec["min_gap_to_sovereign"]

        if sacp_idx is None or sovereign_idx is None:
            uplifted_idx = sacp_idx
        elif max_notches == 0:
            uplifted_idx = sacp_idx
        else:
            ceiling_idx = sovereign_idx - (min_gap or 0)
            target_idx = (sacp_idx + max_notches) if max_notches is not None else ceiling_idx
            uplifted_idx = max(sacp_idx, min(target_idx, ceiling_idx))

        uplifted_rating = config.RATING_SCALE_ASC[uplifted_idx] if uplifted_idx is not None else sacp_rating
        notches_gained = (uplifted_idx - sacp_idx) if (sacp_idx is not None and uplifted_idx is not None) else 0

        s1, s2, s3 = st.columns(3)
        with s1:
            st.markdown(theme.stat_card("📊", "blue", "Likelihood of support", capped_tier,
                                         "capped by dynamic trigger" if capped_tier != tier else "from Role × Link"), unsafe_allow_html=True)
        with s2:
            st.markdown(theme.stat_card("⬆️", "green" if notches_gained > 0 else "muted", "Uplifted rating",
                                         f"{sacp_rating} → {uplifted_rating}", f"+{notches_gained} notch(es)"), unsafe_allow_html=True)
        with s3:
            gap_to_sovereign = (sovereign_idx - uplifted_idx) if (sovereign_idx is not None and uplifted_idx is not None) else None
            st.markdown(theme.stat_card("🏛️", "purple", "Gap to sovereign ceiling",
                                         f"{gap_to_sovereign} notch(es)" if gap_to_sovereign is not None else "—", ""), unsafe_allow_html=True)

        if cap_triggers:
            st.markdown(
                f'<div class="sfp-alert warn">Dynamic cap applied — {", and ".join(cap_triggers)}. '
                f'Likelihood tier capped at "{config.DYNAMIC_CAP_TIER}" regardless of the Role/Link inputs above.</div>',
                unsafe_allow_html=True,
            )

        ceiling_binds = bool(notches_gained > 0 and sovereign_idx is not None and max_notches != 0
                             and uplifted_idx == sovereign_idx - (min_gap or 0))
        results.append({
            "_capped": bool(cap_triggers) and capped_tier != tier, "_ceiling": ceiling_binds,
            "Entity": entity, "Sector": latest.get("Sector", ""), "SACP Rating": sacp_rating,
            "Role": role, "Link": link, "Likelihood Tier": capped_tier,
            "Dynamic Cap Applied": "Yes" if cap_triggers else "No",
            "Uplifted Rating": uplifted_rating, "Notches Gained": notches_gained,
        })

# --- Key figures (top of the page) ------------------------------------------
results_df = pd.DataFrame(results)
if not results_df.empty:
    _n = len(results_df)
    _nn = results_df["Notches Gained"]
    _up = int((_nn > 0).sum())
    theme.stat_strip([
        theme.tile("Sovereign rating", sovereign_rating, "", f"outlook {sovereign_outlook} · local currency, long-term",
                   status="watch" if sovereign_outlook == "Negative" else None, status_text="▲ Negative"),
        theme.tile("SOEs lifted by support", str(_up), f"of {_n}", "rated above their standalone level", status="ok" if _up else None, status_text="● Uplift"),
        theme.tile("Average uplift", f"{_nn.mean():.1f}", "notches", f"range {_nn.min()} to {_nn.max()}"),
        theme.count_tile("Capped by the dynamic trigger", int(results_df["_capped"].sum()), _n, "rating fell fast or sovereign outlook negative", bad="watch"),
        theme.tile("At the sovereign ceiling", str(int(results_df["_ceiling"].sum())), f"of {_n}", "only a higher-rated sovereign would lift them further"),
    ], container=strip_box)
    results_df = results_df.drop(columns=["_capped", "_ceiling"])

# --- Portfolio summary ------------------------------------------------------
st.markdown('<div class="sfp-card"><div class="sfp-title">Portfolio summary</div>', unsafe_allow_html=True)
if not results_df.empty:
    rows_html = "".join(
        f"<tr><td>{r['Entity']}</td><td>{r['Sector']}</td><td>{r['SACP Rating']}</td>"
        f"<td>{r['Role']}</td><td>{r['Link']}</td><td>{r['Likelihood Tier']}</td>"
        f"<td>{r['Dynamic Cap Applied']}</td><td><b>{r['Uplifted Rating']}</b></td><td>+{r['Notches Gained']}</td></tr>"
        for _, r in results_df.iterrows()
    )
    st.markdown(
        "<table class='sfp-table'><thead><tr><th>SOE</th><th>Sector</th><th>Own rating</th>"
        "<th>Role</th><th>Link</th><th>Likelihood</th><th>Dynamic cap?</th>"
        "<th>Uplifted rating</th><th>Notches</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table>",
        unsafe_allow_html=True,
    )
    st.download_button("⬇ Download underlying data", results_df.to_csv(index=False), file_name="gre_uplift_summary.csv")
st.markdown("</div>", unsafe_allow_html=True)

st.markdown(
    """
    <div class="sfp-footnote">
    <p><b>Simplified proxy, not S&P's methodology.</b> The Role × Link → likelihood mapping and the
    notch-uplift ranges here are a transparent, editable stand-in (see config.py) built to the same
    logic as S&P's GRE criteria — not a reproduction of their actual Role-Link matrix or notching
    tables. Uplift only ever raises a rating, never lowers it below the SOE's own Z-EM-derived
    rating, and never exceeds the sovereign's own rating.</p>
    </div>
    """,
    unsafe_allow_html=True,
)
