"""
Key figures shared by the pages' top rows (the same numbers the HTML
version shows in its key-figure strips): number formatting, KPI status with
suppressed ratios counted as alerts, the standard stress test run through
each SOE's own exposures, and the portfolio overview on Home.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

import calculations
import config
import shocks
from utils.portfolio import latest_per_entity

ZONE_RANK = {"Distress": 0, "Grey": 1, "Safe": 2}
ZONE_STATUS = {"Distress": "alert", "Grey": "watch", "Safe": "ok"}
ZONE_TEXT = {"Distress": "■ Distress", "Grey": "▲ Grey zone", "Safe": "● Safe"}
RAG_STATUS = {"Red": "alert", "Amber": "watch", "Green": "ok"}
MAGNITUDES = ["fuel_shock_pct", "fx_shock_pct", "rate_shock_bps", "revenue_shock_std_devs",
              "refinancing_spread_bps", "arrears_pct_of_revenue"]
# ratios the calculation layer sets to NaN when the denominator is not positive; read as an alert
SUPPRESSED = {"roe": "Equity", "debt_to_equity": "Equity", "debt_to_ebitda": "EBITDA",
              "depreciation_to_ebitda": "EBITDA", "effective_tax_rate": "Operating Profits (EBIT)"}


# ---------------------------------------------------------------------------
# formatting
# ---------------------------------------------------------------------------
def ok(v) -> bool:
    try:
        return v is not None and not (isinstance(v, float) and math.isnan(v)) and math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def unit_scale(df: pd.DataFrame) -> float:
    u = str(df["Units"].dropna().iloc[0]).lower() if "Units" in df.columns and df["Units"].notna().any() else ""
    return 1e9 if "billion" in u else 1e6 if "million" in u else 1e3 if "thousand" in u else 1.0


def currency(df: pd.DataFrame) -> str:
    return str(df["Currency"].dropna().iloc[0]) if "Currency" in df.columns and df["Currency"].notna().any() else ""


def money(v, scale: float = 1.0) -> str:
    """1.2 tn / 82.3 bn / 52.1 m / 891,502 — the HTML version's money()."""
    if not ok(v):
        return "—"
    x = float(v) * scale
    a = abs(x)
    if a >= 1e12:
        s = f"{x / 1e12:.2f} tn"
    elif a >= 1e9:
        s = f"{x / 1e9:.1f} bn"
    elif a >= 1e6:
        s = f"{x / 1e6:.1f} m"
    else:
        s = f"{x:,.0f}"
    return s.replace("-", "−")


def pct(v, d: int = 1) -> str:
    return "—" if not ok(v) else f"{v * 100:.{d}f}%".replace("-", "−")


def pct_small(v) -> str:
    if not ok(v):
        return "—"
    if v and abs(v) < 0.00005:
        return "< 0.01%" if v > 0 else "> −0.01%"
    return pct(v, 2)


def signed(v, d: int = 0) -> str:
    return "—" if not ok(v) else (f"+{v:.{d}f}" if v > 0 else f"{v:.{d}f}".replace("-", "−"))


def kpi_fmt(key: str, v) -> str:
    if not ok(v):
        return "n/a"
    if config.KPI_THRESHOLDS[key]["unit"] == "%":
        return f"{v * 100:.{0 if abs(v) >= 1 else 1}f}%".replace("-", "−")
    return (f"{v:.0f}×" if abs(v) >= 100 else f"{v:.1f}×" if abs(v) >= 10 else f"{v:.2f}×").replace("-", "−")


def cut_text(key: str) -> str:
    sp = config.KPI_THRESHOLDS[key]
    f = (lambda v: f"{v * 100:.0f}%") if sp["unit"] == "%" else (lambda v: f"{v:.1f}×")
    if sp["direction"] == "higher_is_better":
        return f"alert < {f(sp['red_cut'])}, good ≥ {f(sp['green_cut'])}"
    return f"alert > {f(sp['red_cut'])}, good ≤ {f(sp['green_cut'])}"


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


# ---------------------------------------------------------------------------
# KPI status
# ---------------------------------------------------------------------------
def kpi_status(row, key: str):
    """'alert' / 'watch' / 'ok' / None. A suppressed ratio (negative equity,
    EBITDA or EBIT) counts as an alert, as the guidance note recommends."""
    v = row.get(key)
    label, _ = calculations.classify(v, key)
    if not ok(v) and key in SUPPRESSED:
        d = row.get(SUPPRESSED[key])
        if ok(d) and d <= 0:
            return "alert"
    return RAG_STATUS.get(label)


# ---------------------------------------------------------------------------
# standard stress (DSA/DSF convention) through each SOE's own exposures
# ---------------------------------------------------------------------------
def _params(row, df_all, mags, duration, horizon, overrides=None):
    p = dict(config.DEFAULT_SHOCK_PARAMS)
    p.update({k: v for k, (v, _src) in calculations.soe_exposures(row).items()})
    if overrides:
        p.update(overrides)
    p.update(mags)
    sigma = calculations.historical_revenue_volatility(df_all, row["Entity"])
    if not ok(sigma):
        sector = row.get("Sector", "Other")
        sigma = config.SECTOR_REVENUE_VOLATILITY.get(sector, config.SECTOR_REVENUE_VOLATILITY["Other"])
    p["revenue_sigma"] = sigma
    p["revenue_shock_pct"] = p["revenue_shock_std_devs"] * sigma
    p["shock_duration_years"] = min(duration, horizon)
    return p


def _cost(path, lgd_pct, ead_share, gdp_series=None):
    path = path.copy()
    path["PD"] = path["Rating"].apply(calculations.compute_pd_from_rating)
    path["EAD"] = path["Total Liabilities"] * ead_share
    path["EFC"] = path["PD"] * path["EAD"] * (lgd_pct / 100.0)
    if gdp_series is not None:
        path["EFC_GDP"] = path["EFC"] / pd.Series(gdp_series[: len(path)], index=path.index)
    return path


def stress_all(df_all: pd.DataFrame, lgd_pct=config.LGD_SLIDER_DEFAULT, ead_share=config.EAD_SHARE_DEFAULT,
               mags=None, duration=None, horizon=None, overrides=None):
    """Latest year of every SOE under the given shock magnitudes (default: the
    standard stress) against its own no-shock path. Returns a list of dicts:
    row, base (path), stress (path), drop (fell at least one zone below the
    no-shock path in some projection year)."""
    horizon = horizon or config.MC_HORIZON_YEARS
    duration = duration or config.DEFAULT_SHOCK_PARAMS["shock_duration_years"]
    mags = mags or {k: config.DEFAULT_SHOCK_PARAMS[k] for k in MAGNITUDES}
    zero = {k: 0.0 for k in MAGNITUDES}
    out = []
    for _, r in latest_per_entity(df_all).iterrows():
        base = _cost(shocks.run_scenario(r, _params(r, df_all, zero, duration, horizon, overrides), horizon), lgd_pct, ead_share)
        stress = _cost(shocks.run_scenario(r, _params(r, df_all, mags, duration, horizon, overrides), horizon), lgd_pct, ead_share)
        drop = any(ZONE_RANK.get(s, 9) < ZONE_RANK.get(b, 9) for s, b in zip(stress["Zone"].iloc[1:], base["Zone"].iloc[1:]))
        out.append({"row": r, "base": base, "stress": stress, "drop": bool(drop)})
    return out


# ---------------------------------------------------------------------------
# Home: portfolio overview
# ---------------------------------------------------------------------------
def portfolio_overview(df_z: pd.DataFrame, lgd_pct=config.LGD_SLIDER_DEFAULT, ead_share=config.EAD_SHARE_DEFAULT, gdp=None):
    """df_z: the panel after compute_zem_components. The same five blocks the
    HTML version's Home shows: zone shares, portfolio EFC, the largest
    exposure, SOEs that drop a zone under standard stress, the fastest
    deterioration."""
    latest = latest_per_entity(df_z)
    n = len(latest)
    zc = {z: int((latest["Zone"] == z).sum()) for z in ["Distress", "Grey", "Safe"]}
    efc = calculations.compute_efc(latest, lgd_pct, ead_share=ead_share)
    total = float(efc["EFC"].sum())
    top = efc.sort_values("EFC", ascending=False).iloc[0] if n else None
    st = stress_all(df_z, lgd_pct, ead_share)
    drops = [x["row"]["Entity"] for x in st if x["drop"]]
    e_base = sum(float(x["base"]["EFC"].iloc[-1]) for x in st)
    e_str = sum(float(x["stress"]["EFC"].iloc[-1]) for x in st)
    first = df_z.sort_values("Year").groupby("Entity").first()
    moved = []
    for _, r in latest.iterrows():
        f = first.loc[r["Entity"]]
        if int(f["Year"]) != int(r["Year"]) and ok(r["Z_EM"]) and ok(f["Z_EM"]):
            moved.append((r["Z_EM"] - f["Z_EM"], r, f))
    worst = min(moved, key=lambda m: m[0]) if moved else None
    return {"n": n, "zones": zc, "mean_z": float(latest["Z_EM"].mean()) if n else float("nan"), "efc_total": total,
            "top": top, "drops": drops, "efc_base": e_base, "efc_stress": e_str, "worst": worst, "n_moved": len(moved),
            "latest": latest, "gdp": gdp}


def efc_gdp_status(share):
    if not ok(share):
        return None
    return "alert" if share >= config.REPORT_EFC_GDP_ALERT else "watch" if share >= config.REPORT_EFC_GDP_WATCH else "ok"
