"""
Interactive HTML version of the SOE Fiscal Risk Tool.

Builds one self-contained .html file that works like the Streamlit app, one
tab per page: Home (overview, toolkit modules, data upload with column
mapping, data quality), Report (five sections: executive summary, financial
performance, distress and fiscal risk, stress tests, policy implications —
prints to PDF), KPI Dashboard, Altman Z-EM, Expected Fiscal Cost, Shock
Scenarios (bottom-up exposures, fuel subsidy, single scenario, correlated
Monte Carlo, all SOEs), Government Support, Early Warning and Assumptions &
sources (parameter register, data dictionary). It opens in any browser and
needs no Python or server; people can load their own CSV/Excel file into it.

How it fits together
  templates/app.html   page skeleton (tabs, placeholders)
  templates/app.css    styles (same palette as the Streamlit theme)
  templates/engine.js  JavaScript port of calculations.py, shocks.py,
                       narrative.py, utils/summary.py, the GRE uplift and
                       schema.py's column matching
  templates/app.js     the tabs, controls and SVG charts
This module embeds the statement rows and every config.py number the engine
needs, then inlines the four files into a single page.

Keeping the two engines in step
  config.py values flow into the page automatically. If you change a FORMULA
  in calculations.py / shocks.py / narrative.py, make the same change in
  templates/engine.js and run `python tests/check_engine_parity.py`, which
  compares both implementations on the demo portfolio.

Use it three ways:
  * the "HTML version" page in the Streamlit app (preview + download button)
  * from Python:  html = report.build_html(df, lgd_pct=70)
  * from a shell: python report.py --demo --out soe_tool.html
                  python report.py --input my_soes.xlsx --lgd 70 --gdp 9.5e12
"""

from __future__ import annotations

import argparse
import datetime as dt
import html as html_lib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

import config
import data_loader
import schema

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

# --------------------------------------------------------------------------
# payloads for the interactive app (config numbers + raw statement rows)
# --------------------------------------------------------------------------
def _json_safe(obj):
    """Recursively replace ±inf/NaN with None and numpy scalars with Python
    ones so the structure serialises as strict JSON."""
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else f
    return obj


def config_payload() -> dict:
    """Every config.py number and label the in-browser engine needs. Zone and
    rating bounds use None for ±infinity."""
    names = [
        "ZEM_COEFFICIENTS", "ZEM_CONSTANT", "ZEM_LABELS", "ZEM_DESCRIPTORS", "ZEM_COMPONENT_STRONG_THRESHOLD",
        "SINGLE_DRIVER_SHARE_THRESHOLD", "ZONES", "Z_DISTRESS_CUTOFF", "Z_SAFE_CUTOFF", "Z_RATING_TABLE", "PD_BY_ZONE",
        "LGD_SLIDER_MIN", "LGD_SLIDER_MAX", "LGD_SLIDER_DEFAULT", "SECTOR_RECOVERY_DATA", "KPI_THRESHOLDS",
        "KPI_CATEGORIES", "CATEGORY_LABELS", "CATEGORY_ORDER", "SECTOR_FUEL_COST_SHARE", "SECTOR_REVENUE_VOLATILITY",
        "DEFAULT_SHOCK_PARAMS", "MC_DEFAULT_SIMULATIONS", "MC_DEFAULT_FUEL_STD", "MC_DEFAULT_FX_STD",
        "MC_DEFAULT_CORRELATION", "MC_HORIZON_YEARS", "DEFAULT_GDP_GROWTH", "REQUIRED_COLUMNS", "OPTIONAL_SHOCK_COLUMNS",
        "GLOSSARY", "RATING_SCALE_ASC", "SOVEREIGN_OUTLOOK_OPTIONS", "ROLE_LEVELS", "ROLE_SCORE", "ROLE_CRITERIA",
        "LINK_LEVELS", "LINK_SCORE", "LINK_CRITERIA", "LIKELIHOOD_TIERS_ASC", "LIKELIHOOD_UPLIFT",
        "DYNAMIC_CAP_TRIGGER_NOTCHES", "DYNAMIC_CAP_TIER", "TRIGGER_RULES", "REPORT_HEADLINE_KPIS",
        "REPORT_STRESS_CHANNELS", "REPORT_EFC_GDP_WATCH", "REPORT_EFC_GDP_ALERT",
        "DEFAULT_EXPOSURES", "EAD_SHARE_DEFAULT", "EAD_SHARE_PRESETS", "MC_DEFAULT_RATE_STD_BPS",
        "MC_DEFAULT_REVENUE_STD_SD", "MC_DEFAULT_CORRELATIONS", "PARAMETER_REGISTER", "PARAMETER_STATUS_LABELS",
    ]
    out = {n: getattr(config, n) for n in names}
    out["ROLE_LINK_TO_TIER"] = config._ROLE_LINK_SCORE_TO_TIER
    out["NUMERIC_COLUMNS"] = data_loader.NUMERIC_COLUMNS
    out["ALL_NUMERIC_COLUMNS"] = data_loader.NUMERIC_COLUMNS + data_loader.OPTIONAL_NUMERIC_COLUMNS
    out["TEXT_COLUMNS"] = ROW_TEXT_COLUMNS
    out["PROVENANCE_COLUMNS"] = schema.PROVENANCE_COLUMNS
    out["SCHEMA"] = schema.payload()
    return _json_safe(out)


# identifier and provenance text columns carried into the page (numbers: every numeric schema column)
ROW_TEXT_COLUMNS = ["Entity", "Sector", "Country", "Currency", "Units"] + schema.PROVENANCE_COLUMNS


def rows_payload(raw_df: pd.DataFrame) -> list:
    """Raw statement rows (every column in the standard schema), numbers
    coerced the same way data_loader.coerce_numeric does, blanks as None.
    Headers are matched to the schema first (synonyms, close spellings)."""
    df, _mapping = schema.standardize_columns(raw_df)
    df = data_loader.coerce_numeric(df)
    df = df.dropna(subset=["Entity", "Year"]).copy()
    df["Year"] = df["Year"].astype(int)
    if "Sector" not in df.columns:
        df["Sector"] = "Other"
    df["Sector"] = df["Sector"].fillna("Other")
    keep = [c for c in dict.fromkeys(ROW_TEXT_COLUMNS + data_loader.NUMERIC_COLUMNS + data_loader.OPTIONAL_NUMERIC_COLUMNS) if c in df.columns]
    recs = []
    for _, r in df[keep].iterrows():
        rec = {}
        for c in keep:
            v = r[c]
            if c in ROW_TEXT_COLUMNS:
                rec[c] = None if pd.isna(v) else str(v)
            else:
                rec[c] = v
        recs.append(rec)
    return _json_safe(recs)


# --------------------------------------------------------------------------
# app builder
# --------------------------------------------------------------------------
def _pack(recs: list) -> dict:
    """Rows as {cols, data}: column names once, then one list of values per
    row — about half the size of repeating every key (app.js unpacks it)."""
    cols = list(dict.fromkeys(k for r in recs for k in r))
    return {"cols": cols, "data": [[r.get(c) for c in cols] for r in recs]}


def build_app_data(
    raw_df: pd.DataFrame,
    lgd_pct: float = config.LGD_SLIDER_DEFAULT,
    base_gdp: float | None = None,
    gdp_growth: float = config.DEFAULT_GDP_GROWTH,
    title: str = config.REPORT_TITLE,
    data_label: str = "",
    is_example: bool = False,
    allow_download: bool = False,
) -> dict:
    """Everything the page needs: config numbers, the statement rows to open
    with, and the built-in sample and demo datasets (so the page can switch to
    them or take a new upload without Python)."""
    rows = rows_payload(raw_df)
    if not rows:
        raise ValueError("No usable rows: every row needs at least an Entity and a Year.")
    meta = {
        "title": title, "generated": dt.date.today().isoformat(),
        "lgd_pct": float(lgd_pct), "gdp": float(base_gdp) if base_gdp else None, "gdp_growth": float(gdp_growth),
        # set by a host frame that permits downloads and printing (the Streamlit app); a bare viewer frame hides them
        "allow_download": bool(allow_download),
    }
    datasets = {
        "report": dict(_pack(rows), label=data_label or "Report data", example=bool(is_example)),
        "sample": dict(_pack(rows_payload(data_loader.sample_dataset())), label="Built-in sample: SOE A (Energy), SOE B (Transport)", example=True),
        "demo": dict(_pack(rows_payload(data_loader.demo_portfolio())), label="Illustrative demo portfolio: 8 invented SOEs", example=True),
        # 30 invented SOEs x 20 years, to see how long histories and large portfolios are drawn
        "long": dict(_pack(rows_payload(data_loader.long_panel_demo())), label=data_loader.LONG_PANEL_LABEL, example=True),
    }
    return {"config": config_payload(), "data": {"meta": meta, "datasets": datasets}}


def _json_script(obj) -> str:
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return text.replace("</", "<\\/")  # never close the <script> element early


def render_html(app: dict, standalone: bool = True) -> str:
    """Assemble templates/app.html + app.css + engine.js + app.js with the
    data. standalone=True returns a complete HTML document (for download);
    False returns the page body only (for hosts that add their own
    <html>/<head> skeleton)."""
    tpl = (TEMPLATE_DIR / "app.html").read_text(encoding="utf-8")
    css = (TEMPLATE_DIR / "app.css").read_text(encoding="utf-8")
    engine = (TEMPLATE_DIR / "engine.js").read_text(encoding="utf-8")
    app_js = (TEMPLATE_DIR / "app.js").read_text(encoding="utf-8")
    title = html_lib.escape(app["data"]["meta"]["title"])
    body = (
        tpl.replace("__APP_TITLE__", title)
        .replace("/*__APP_CSS__*/", css)
        .replace("/*__APP_CONFIG__*/{}", _json_script(app["config"]))
        .replace("/*__APP_DATA__*/{}", _json_script(app["data"]))
        .replace("/*__ENGINE_JS__*/", engine.replace("</script", "<\\/script"))
        .replace("/*__APP_JS__*/", app_js.replace("</script", "<\\/script"))
    )
    if not standalone:
        return body
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        "</head>\n<body>\n" + body + "\n</body>\n</html>\n"
    )


def build_html(raw_df: pd.DataFrame, standalone: bool = True, **kwargs) -> str:
    return render_html(build_app_data(raw_df, **kwargs), standalone=standalone)


# --------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------
def _main():
    ap = argparse.ArgumentParser(description="Generate the interactive HTML version of the SOE Fiscal Risk Tool.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", help="CSV or Excel file in the tool's upload format")
    src.add_argument("--sample", action="store_true", help="use the built-in 2-SOE sample")
    src.add_argument("--demo", action="store_true", help="use the illustrative 8-SOE demo portfolio")
    ap.add_argument("--lgd", type=float, default=config.LGD_SLIDER_DEFAULT, help="LGD in percent (default 70)")
    ap.add_argument("--gdp", type=float, default=None, help="base-year nominal GDP, same currency and units as the data")
    ap.add_argument("--growth", type=float, default=config.DEFAULT_GDP_GROWTH, help="nominal GDP growth, decimal (default 0.03)")
    ap.add_argument("--title", default=config.REPORT_TITLE)
    ap.add_argument("--out", default="soe_fiscal_risk_tool.html")
    ap.add_argument("--fragment", action="store_true", help="write the page body only, without <html>/<head>")
    args = ap.parse_args()

    if args.input:
        raw = pd.read_csv(args.input) if args.input.lower().endswith(".csv") else pd.read_excel(args.input)
        raw, _mapping = schema.standardize_columns(raw)
        check = data_loader.validate_schema(raw)
        if check["missing_required"]:
            raise SystemExit("Missing required column(s): " + ", ".join(check["missing_required"]))
        label, example = "", False
    elif args.sample:
        raw, label, example = data_loader.sample_dataset(), "Built-in sample: SOE A (Energy), SOE B (Transport)", True
    else:
        raw, label, example = data_loader.demo_portfolio(), "Illustrative demo portfolio: 8 invented SOEs", True

    out = build_html(raw, standalone=not args.fragment, lgd_pct=args.lgd, base_gdp=args.gdp,
                     gdp_growth=args.growth, title=args.title, data_label=label, is_example=example)
    Path(args.out).write_text(out, encoding="utf-8")
    print(f"Wrote {args.out} ({len(out) / 1024:.0f} KB)")


if __name__ == "__main__":
    _main()
