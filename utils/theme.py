"""
Shared look and feel for every page: navy top nav bar (logo, links with a
blue underline on the active page — no sidebar), a navy title band per page,
square-cornered cards and stat tiles, and status chips that pair a glyph
(● ▲ ■) with the color. Same visual system as the one-page HTML report. Colors come from config.THEME — change them there,
not here. Every font-size below is wrapped in fs(...), so config.FONT_SCALE
controls all of them from one place.
"""

from pathlib import Path

import streamlit as st

from config import BASE_ROOT_PX, FONT_SCALE, THEME, fs

_LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo.png"


def inject():
    if _LOGO_PATH.exists():
        st.logo(str(_LOGO_PATH))

    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;600;700&display=swap');
        html {{ font-size: {round(BASE_ROOT_PX * FONT_SCALE, 2)}px; }}
        html, body, [class*="css"], .stApp, .stMarkdown, button, input, select, textarea {{
            font-family: "Open Sans", "Segoe UI", system-ui, -apple-system, sans-serif;
        }}
        .stApp {{ background: {THEME['bg']}; }}
        #MainMenu {{visibility: hidden;}}
        div[data-testid="stAppDeployButton"] {{ display: none !important; }}
        .block-container {{ padding-top: 84px; max-width: 1240px; }}
        h1, h2, h3, h4, h5 {{ color: {THEME['heading']}; }}

        /* ---------------- Top nav bar (navy band, blue underline on the active page) ---------------- */
        header[data-testid="stHeader"] {{
            background: {THEME['sidebar_bg']} !important;
            height: 60px;
        }}
        [data-testid="stHeaderLogo"] {{ height: 34px !important; width: auto !important; }}
        [data-testid="stTopNavLink"] {{
            color: {THEME['sidebar_text']} !important;
            border-radius: 0 !important;
            padding: 7px 10px 5px !important;
            border-bottom: 3px solid transparent;
            font-size: {fs(13.5)};
            font-weight: 600;
            background: transparent !important;
        }}
        [data-testid="stTopNavLink"] * {{ color: {THEME['sidebar_text']} !important; }}
        [data-testid="stTopNavLink"] p, [data-testid="stTopNavSection"] p {{ font-size: {fs(12.5)} !important; font-weight: 600; }}
        [data-testid="stTopNavSection"], [data-testid="stTopNavSection"] * {{ color: {THEME['sidebar_text']} !important; }}
        [data-testid="stTopNavSection"]:hover * {{ color: #FFFFFF !important; }}
        [data-testid="stTopNavLink"]:hover {{ border-bottom-color: rgba(255,255,255,.35); }}
        [data-testid="stTopNavLink"]:hover * {{ color: {THEME['sidebar_text_active']} !important; }}
        [data-testid="stTopNavLink"][aria-current="page"] {{ border-bottom-color: {THEME['accent']}; }}
        [data-testid="stTopNavLink"][aria-current="page"] * {{ color: #FFFFFF !important; }}
        span[data-testid="stMainMenu"] {{ visibility: visible !important; }}
        span[data-testid="stMainMenu"] svg {{ fill: {THEME['sidebar_text']} !important; }}

        /* ---------------- Page title band ---------------- */
        .sfp-band {{
            background: {THEME['heading']}; color: #FFFFFF; border-radius: 4px;
            padding: 22px 26px 20px; margin: 0 0 22px;
        }}
        .sfp-eyebrow {{
            color: {THEME['accent']}; font-size: {fs(11)}; font-weight: 700;
            letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 6px;
        }}
        .sfp-page-title {{ font-size: {fs(25)}; font-weight: 700; color: #FFFFFF; margin: 0 0 6px; letter-spacing: -0.01em; line-height: 1.2; }}
        .sfp-page-subtitle {{
            font-size: {fs(13.5)}; color: rgba(255,255,255,.78); margin: 0; max-width: 80ch; line-height: 1.55;
        }}
        .sfp-meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
        .sfp-meta span {{ font-size: {fs(11)}; color: rgba(255,255,255,.78); background: rgba(255,255,255,.10); border-radius: 2px; padding: 3px 9px; }}
        .sfp-meta span b {{ color: #FFFFFF; font-weight: 600; }}
        .sfp-meta span.flag {{ background: {THEME['amber']}; color: {THEME['text']}; font-weight: 600; }}

        /* ---------------- Cards ---------------- */
        .sfp-card {{
            background: {THEME['card']}; border: 1px solid rgba(0,34,68,.10); border-radius: 4px;
            padding: 16px 18px; margin-bottom: 14px;
        }}
        .sfp-title {{
            font-size: {fs(15)} !important; font-weight: 700 !important; color: {THEME['heading']} !important;
            margin: 0 0 8px !important; line-height: 1.25 !important; display: block;
        }}
        .sfp-card-compact {{
            background: {THEME['card']}; border: 1px solid rgba(0,34,68,.10); border-radius: 4px;
            border-top: 3px solid {THEME['heading']};
            padding: 8px 10px; margin-bottom: 6px;
        }}
        .sfp-compact-title {{
            font-size: {fs(13.5)} !important; font-weight: 700 !important; color: {THEME['heading']} !important;
            margin: 0 0 4px !important; line-height: 1.25 !important; display: block;
        }}
        .sfp-kpi-desc {{
            font-size: {fs(10.45)} !important; color: {THEME['muted']} !important; line-height: 1.42 !important;
            margin: 5px 0 0 !important; min-height: 92px; display: block;
        }}

        /* ---------------- Stat tiles ---------------- */
        .sfp-stat {{
            background: rgba(0,159,218,.10); border: 0; border-radius: 4px; padding: 16px 18px; height: 100%;
        }}
        .sfp-stat.alert {{ background: rgba(208,59,59,.09); }} .sfp-stat.watch {{ background: rgba(247,184,65,.13); }} .sfp-stat.ok {{ background: rgba(0,169,150,.10); }}
        .sfp-stat-top {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 10px; }}
        .sfp-stat-icon {{ display: none; }}
        .sfp-stat-label {{ font-size: {fs(12.5)}; font-weight: 600; color: {THEME['ink2']}; }}
        .sfp-stat-value {{ font-size: {fs(25)}; font-weight: 700; color: {THEME['heading']}; line-height: 1.15; letter-spacing: -0.01em; }}
        .sfp-stat-caption {{ font-size: {fs(11.5)}; color: {THEME['muted']}; margin-top: 6px; line-height: 1.45; }}
        .sfp-stat-caption b.up {{ color: {THEME['green_ink']}; }}
        .sfp-stat-caption b.down {{ color: {THEME['red_ink']}; }}

        /* ---------------- Key figures (top of every page) ---------------- */
        /* boxes take a light, see-through wash of their status colour, no outline; the status
           shows as coloured text so a box never carries two coloured shapes (as the HTML version) */
        .sfp-strip {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 4px 0 18px; }}
        .sfp-tile {{ border-radius: 4px; padding: 14px 16px; display: grid; gap: 5px; align-content: start; background: rgba(0,159,218,.10); }}
        .sfp-tile.alert {{ background: rgba(208,59,59,.09); }}
        .sfp-tile.watch {{ background: rgba(247,184,65,.13); }}
        .sfp-tile.ok {{ background: rgba(0,169,150,.10); }}
        .sfp-tile-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }}
        .sfp-tile-label {{ font-size: {fs(12.5)}; font-weight: 600; color: {THEME['ink2']}; line-height: 1.3; }}
        .sfp-tile-st {{ font-size: {fs(11.5)}; font-weight: 700; white-space: nowrap; }}
        .sfp-tile-st.alert {{ color: {THEME['red_ink']}; }} .sfp-tile-st.watch {{ color: {THEME['amber_ink']}; }} .sfp-tile-st.ok {{ color: {THEME['green_ink']}; }}
        .sfp-tile-value {{ font-size: {fs(25)}; font-weight: 700; color: {THEME['heading']}; line-height: 1.15; letter-spacing: -0.01em; overflow-wrap: anywhere; }}
        .sfp-tile-value small {{ font-size: {fs(12.5)}; font-weight: 400; color: {THEME['ink2']}; margin-left: 4px; letter-spacing: 0; }}
        .sfp-tile-sub {{ font-size: {fs(11.5)}; color: {THEME['muted']}; line-height: 1.45; }}
        @media (max-width: 560px) {{ .sfp-strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }} .sfp-tile-value {{ font-size: {fs(20)}; }} }}
        .sfp-hero {{ background: {THEME['card']}; border-radius: 4px; padding: 16px 18px; border: 1px solid rgba(0,34,68,.10); margin-bottom: 12px; }}
        .sfp-hero-label {{ font-size: {fs(12.5)}; font-weight: 600; color: {THEME['ink2']}; }}
        .sfp-hero-value {{ font-size: {fs(42)}; font-weight: 700; color: {THEME['heading']}; line-height: 1.05; letter-spacing: -0.02em; margin: 6px 0 10px; }}
        .sfp-hero-value small {{ font-size: {fs(13)}; font-weight: 400; color: {THEME['ink2']}; letter-spacing: 0; margin-left: 8px; }}
        .sfp-zonebar {{ display: flex; height: 12px; border-radius: 2px; overflow: hidden; gap: 2px; margin-bottom: 8px; }}
        .sfp-zonelegend {{ display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: {fs(12)}; color: {THEME['ink2']}; margin-bottom: 8px; }}
        .sfp-2col {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
        @media (max-width: 560px) {{ .sfp-2col {{ grid-template-columns: minmax(0, 1fr); }} }}

        /* ---------------- Top filter bar ---------------- */
        .sfp-topbar {{
            background: {THEME['card']}; border: 1px solid rgba(0,34,68,.10); border-radius: 4px;
            padding: 10px 16px; margin-bottom: 18px;
        }}
        .sfp-topbar:empty, .sfp-card:empty {{ display: none; }}
        span[data-tag] {{ background-color: {THEME['heading']} !important; border-radius: 2px !important; }}
        span[data-tag] span[title] {{ color: #FFFFFF !important; }}
        span[data-tag] button {{ color: #FFFFFF !important; }}
        span[data-tag] button svg {{ stroke: #FFFFFF !important; }}

        /* ---------------- Alerts ---------------- */
        .sfp-alert {{ font-size: {fs(12.5)}; padding: 9px 12px; border-radius: 3px; margin-top: 10px; line-height: 1.45; color: {THEME['text']}; }}
        .sfp-alert.ok {{ background: {THEME['green_bg']}; box-shadow: inset 3px 0 0 {THEME['green']}; }}
        .sfp-alert.info {{ background: {THEME['blue_bg']}; box-shadow: inset 3px 0 0 {THEME['accent']}; }}
        .sfp-alert.warn {{ background: {THEME['red_bg']}; box-shadow: inset 3px 0 0 {THEME['red']}; }}

        .sfp-hint {{ font-size: {fs(12)}; color: {THEME['muted']}; line-height: 1.5; }}
        .sfp-summary {{
            background: {THEME['blue_bg']}; border-left: 3px solid {THEME['accent']}; border-radius: 3px;
            padding: 11px 13px; font-size: {fs(12.5)}; line-height: 1.5; color: {THEME['text']}; margin-top: 10px;
        }}
        .sfp-summary .tag {{ font-size: {fs(10)}; color: {THEME['muted']}; display: block; margin-bottom: 3px; }}

        /* ---------------- Tables ---------------- */
        table.sfp-table {{ border-collapse: collapse; width: 100%; font-size: {fs(12.5)}; font-variant-numeric: tabular-nums; }}
        table.sfp-table th {{
            text-align: left; font-size: {fs(11)}; color: {THEME['heading']}; font-weight: 700;
            padding: 8px 10px; border-bottom: 2px solid {THEME['heading']}; white-space: nowrap;
        }}
        table.sfp-table td {{ padding: 9px 10px; border-bottom: 1px solid {THEME['border']}; white-space: nowrap; }}
        table.sfp-table tbody tr:last-child td {{ border-bottom: none; }}
        /* Wrap variant — for tables holding paragraph-length text (glossary
           definitions, criteria descriptions), where nowrap runs long text
           off the edge instead of wrapping it. Scorecard tables (short
           values, ratings) keep the default nowrap above. */
        table.sfp-table-wrap td {{ white-space: normal; word-wrap: break-word; vertical-align: top; }}
        table.sfp-table-wrap th {{ white-space: normal; }}
        .sfp-dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }}

        /* Status chips: a glyph as well as a color, so state never relies on color alone */
        .sfp-chip {{ display:inline-flex; align-items:center; gap:5px; padding: 2px 8px 2px 7px; border-radius: 2px;
                     font-size: {fs(11.5)}; font-weight: 600; color: {THEME['text']}; white-space: nowrap; }}
        .sfp-chip::before {{ font-size: 9px; line-height: 1; }}
        .sfp-chip.red {{ background:{THEME['red_bg']}; }}
        .sfp-chip.red::before {{ content: "■"; color:{THEME['red_ink']}; }}
        .sfp-chip.amber {{ background:{THEME['amber_bg']}; }}
        .sfp-chip.amber::before {{ content: "▲"; color:{THEME['amber_ink']}; }}
        .sfp-chip.green {{ background:{THEME['green_bg']}; }}
        .sfp-chip.green::before {{ content: "●"; color:{THEME['green_ink']}; }}
        .sfp-chip.muted {{ background:#EEF1F4; color:{THEME['muted']}; font-weight: 400; }}

        .sfp-footnote {{ font-size: {fs(11.5)}; color: {THEME['muted']}; line-height: 1.6; border-top: 2px solid {THEME['heading']}; padding-top: 10px; margin-top: 18px; }}

        /* ---------------- Info tooltip icon ---------------- */
        .sfp-info {{
            display: inline-block; cursor: help; color: {THEME['muted']}; font-size: {fs(12)};
            margin-left: 4px; border-bottom: 1px dotted {THEME['muted']};
        }}
        .sfp-info:hover {{ color: {THEME['blue']}; }}

        /* ---------------- Widgets ---------------- */
        .stButton>button, .stDownloadButton>button {{ border-radius: 2px; font-weight: 600; }}
        .stDownloadButton button[data-testid="stBaseButton-secondary"] {{ border-color: {THEME['border']}; color: {THEME['blue']}; }}
        .stTabs [data-baseweb="tab"] {{ font-weight: 600; }}
        div[data-testid="stExpander"] details {{ border-radius: 4px; border-color: rgba(0,34,68,.12); background: {THEME['card']}; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def info_icon(text):
    """A small (?) icon that shows `text` as a native browser tooltip on
    hover — use inline next to a label or title, e.g.:
    st.markdown(f'Z-EM score {theme.info_icon(config.GLOSSARY["Z-EM score"])}', unsafe_allow_html=True)"""
    return f'<span class="sfp-info" title="{text}">ⓘ</span>'


def header(eyebrow, title, subtitle, meta=None):
    """Navy title band at the top of a page. `meta` is an optional list of
    (label, value) pairs shown as small chips under the subtitle; a pair
    whose label is "flag" renders as the amber example-data flag."""
    chips = ""
    if meta:
        parts = []
        for label, value in meta:
            if label == "flag":
                parts.append(f'<span class="flag">▲ {value}</span>')
            else:
                parts.append(f"<span>{label} <b>{value}</b></span>")
        chips = f'<div class="sfp-meta">{"".join(parts)}</div>'
    st.markdown(
        f"""
        <div class="sfp-band">
        <div class="sfp-eyebrow">{eyebrow}</div>
        <div class="sfp-page-title">{title}</div>
        <div class="sfp-page-subtitle">{subtitle}</div>
        {chips}
        </div>
        """,
        unsafe_allow_html=True,
    )


_STATUS_OF_COLOR = {"red": "alert", "amber": "watch", "green": "ok"}
STATUS_TEXT = {"alert": "■ Alert", "watch": "▲ Watch", "ok": "● Good"}


def stat_card(icon, color_key, label, value, caption=""):
    """color_key: 'red' / 'amber' / 'green' give the box a light wash of that
    status colour, anything else a light blue wash. `icon` is kept for
    compatibility but no longer drawn. Returns an HTML string — wrap the call
    in st.markdown(..., unsafe_allow_html=True)."""
    bg = THEME.get(f"{color_key}_bg", THEME["blue_bg"])
    fg = THEME.get(f"{color_key}_ink", THEME.get(color_key, THEME["blue"]))
    status = _STATUS_OF_COLOR.get(color_key, "")
    return (
        f'<div class="sfp-stat {status}">'
        f'<div class="sfp-stat-top">'
        f'<div class="sfp-stat-label">{label}</div>'
        f'<div class="sfp-stat-icon" style="background:{bg};color:{fg}">{icon}</div>'
        f"</div>"
        f'<div class="sfp-stat-value">{value}</div>'
        f'<div class="sfp-stat-caption">{caption}</div>'
        f"</div>"
    )


def status_chip(level, text):
    """Inline status chip with glyph: level is 'red' / 'amber' / 'green' /
    'muted' (same keys calculations.classify returns)."""
    return f"<span class='sfp-chip {level}'>{text}</span>"


def summary_box(text):
    st.markdown(
        f'<div class="sfp-summary"><span class="tag">Automated summary — generated from the data on screen, '
        f'not written by a person</span>{text}</div>',
        unsafe_allow_html=True,
    )


def tile_html(label, value, small="", sub="", status=None, status_text=None):
    """One key-figure box. status: 'alert' / 'watch' / 'ok' / None (neutral)."""
    st_html = f'<span class="sfp-tile-st {status}">{status_text or STATUS_TEXT.get(status, "")}</span>' if status else ""
    small_html = f"<small>{small}</small>" if small else ""
    return (
        f'<div class="sfp-tile {status or ""}"><div class="sfp-tile-top"><span class="sfp-tile-label">{label}</span>{st_html}</div>'
        f'<div class="sfp-tile-value">{value}{small_html}</div><div class="sfp-tile-sub">{sub}</div></div>'
    )


def stat_strip(tiles, container=None):
    """The row of key figures at the top of a page. tiles: dicts with keys
    label, value, small, sub, status, status_text (None entries are skipped).
    container: an st.container() made earlier, so the row can sit at the top
    of the page while its numbers are computed further down."""
    html = "".join(tile_html(**t) for t in tiles if t)
    target = container if container is not None else st
    target.markdown(f'<div class="sfp-strip">{html}</div>', unsafe_allow_html=True)


def tile(label, value, small="", sub="", status=None, status_text=None):
    """Shorthand for one stat_strip entry."""
    return dict(label=label, value=value, small=small, sub=sub, status=status, status_text=status_text)


def count_tile(label, n, of, sub="", bad="alert"):
    """A count with 'Alert' (or 'Watch') when it is above zero, 'Good' when zero."""
    return tile(label, str(n), f"of {of}", sub, status=bad if n else "ok")
