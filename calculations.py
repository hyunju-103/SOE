"""
Calculation layer: Z''-EM, supplementary KPIs, red/amber/green classification,
and Expected Fiscal Cost. Pure functions operating on a pandas DataFrame in
the long-format schema defined in config.REQUIRED_COLUMNS.
"""

import numpy as np
import pandas as pd

import config


def compute_zem_components(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["X1"] = (out["Current Assets"] - out["Current Liabilities"]) / out["Total Assets"]
    out["X2"] = out["Retained Earnings"] / out["Total Assets"]
    out["X3"] = out["Operating Profits (EBIT)"] / out["Total Assets"]
    out["X4"] = out["Equity"] / out["Total Liabilities"]

    for comp, beta in config.ZEM_COEFFICIENTS.items():
        out[f"{comp}_contrib"] = out[comp] * beta

    out["Z_EM"] = sum(out[f"{c}_contrib"] for c in config.ZEM_COEFFICIENTS) + config.ZEM_CONSTANT
    out["Zone"] = out["Z_EM"].apply(classify_zone)
    out["Rating"] = out["Z_EM"].apply(config.z_rating)
    return out


def classify_zone(z_score: float) -> str:
    if pd.isna(z_score):
        return "Unknown"
    for zone, lower, upper in config.ZONES:
        if lower < z_score <= upper:
            return zone
    return "Unknown"


def classify_zem_from_values(working_capital, total_assets, retained_earnings,
                               ebit, equity, total_liabilities):
    """Scalar version, for the dynamic shock projection loop."""
    x1 = working_capital / total_assets if total_assets else np.nan
    x2 = retained_earnings / total_assets if total_assets else np.nan
    x3 = ebit / total_assets if total_assets else np.nan
    x4 = equity / total_liabilities if total_liabilities else np.nan
    z = (
        config.ZEM_COEFFICIENTS["X1"] * x1 + config.ZEM_COEFFICIENTS["X2"] * x2
        + config.ZEM_COEFFICIENTS["X3"] * x3 + config.ZEM_COEFFICIENTS["X4"] * x4
        + config.ZEM_CONSTANT
    )
    return x1, x2, x3, x4, z, classify_zone(z)


def _safe_div(numerator, denominator):
    with np.errstate(divide="ignore", invalid="ignore"):
        result = numerator / denominator
    return result.replace([np.inf, -np.inf], np.nan)


def compute_kpis(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    revenue = out["Revenues"]
    ebit = out["Operating Profits (EBIT)"]

    out["operating_margin"] = _safe_div(ebit, revenue)
    out["net_margin"] = _safe_div(out["Net Income"], revenue)
    out["ebitda_margin"] = _safe_div(out["EBITDA"], revenue)
    out["roa"] = _safe_div(out["Net Income"], out["Total Assets"])
    # ROE/Debt-Equity/Debt-EBITDA flip sign under negative equity/EBITDA —
    # suppressed (NaN) rather than shown as a false "good" reading.
    out["roe"] = _safe_div(out["Net Income"], out["Equity"]).where(out["Equity"] > 0)

    out["current_ratio"] = _safe_div(out["Current Assets"], out["Current Liabilities"])
    out["working_capital_ratio"] = out.get("X1", _safe_div(
        out["Current Assets"] - out["Current Liabilities"], out["Total Assets"]
    ))

    out["debt_to_ebitda"] = _safe_div(out["Total Liabilities"], out["EBITDA"]).where(out["EBITDA"] > 0)
    out["liabilities_to_assets"] = _safe_div(out["Total Liabilities"], out["Total Assets"])
    out["interest_coverage"] = _safe_div(ebit, out["Interest Expense"])
    out["debt_to_equity"] = _safe_div(out["Total Liabilities"], out["Equity"]).where(out["Equity"] > 0)

    out["asset_turnover"] = _safe_div(revenue, out["Total Assets"])
    out["depreciation_to_ebitda"] = _safe_div(out["Depreciation"], out["EBITDA"]).where(out["EBITDA"] > 0)

    out["grants_to_revenue"] = _safe_div(out["Government Grants"], revenue)
    out["grants_to_expense"] = _safe_div(out["Government Grants"], out["Total Expense"])
    out["effective_tax_rate"] = _safe_div(out["Tax Expense"], ebit).where(ebit > 0)

    out["negative_equity_flag"] = out["Equity"] <= 0
    out["negative_ebitda_flag"] = out["EBITDA"] <= 0
    return out


def available_kpis(df: pd.DataFrame, category=None):
    """Which KPIs have all required raw columns present and non-null
    somewhere in df. Pass a category key to filter, or omit for all."""
    keys = config.KPI_CATEGORIES[category] if category else list(config.KPI_THRESHOLDS.keys())
    available = []
    for key in keys:
        spec = config.KPI_THRESHOLDS[key]
        if all(c in df.columns and df[c].notna().any() for c in spec["requires"]):
            available.append(key)
    return available


def classify(value, kpi_key):
    """Returns (label, color_key) — 'Red'/'Amber'/'Green'/'No data'."""
    if pd.isna(value):
        return "No data", "muted"
    spec = config.KPI_THRESHOLDS[kpi_key]
    red_cut, green_cut = spec["red_cut"], spec["green_cut"]
    if spec["direction"] == "higher_is_better":
        if value < red_cut:
            return "Red", "red"
        if value >= green_cut:
            return "Green", "green"
        return "Amber", "amber"
    else:
        if value > red_cut:
            return "Red", "red"
        if value <= green_cut:
            return "Green", "green"
        return "Amber", "amber"


def compute_pd(zone: str) -> float:
    """Coarse 3-bucket fallback. Prefer compute_pd_from_rating() — this
    stays only for a missing/unrecognized rating."""
    return config.PD_BY_ZONE.get(zone, np.nan)


def compute_pd_from_rating(rating: str) -> float:
    """Per-rating PD from the uploaded rating cohort table
    (config.PD_BY_RATING) — the primary PD calibration, differentiating
    within a zone rather than collapsing it to one flat value."""
    pd_val = config.pd_by_rating(rating)
    return pd_val if pd_val == pd_val else np.nan  # NaN-safe passthrough


def compute_efc(df: pd.DataFrame, lgd_pct: float, ead_share: float = config.EAD_SHARE_DEFAULT,
                ead_basis: str = "total_liabilities") -> pd.DataFrame:
    """EFC = PD × EAD × LGD.
    EAD basis:
      "total_liabilities" — ead_share × Total Liabilities (a proxy; 1.0 is the
                            original assumption, 0.6 / 0.8 sensitivity cases)
      "guaranteed_debt"   — observed Government Guaranteed Debt where the data
                            carry it, falling back to the proxy row by row.
    EAD_source records which one each row used."""
    out = df.copy()
    out["PD"] = out["Rating"].apply(compute_pd_from_rating)
    proxy = out["Total Liabilities"] * ead_share
    if ead_basis == "guaranteed_debt" and "Government Guaranteed Debt" in out.columns:
        observed = pd.to_numeric(out["Government Guaranteed Debt"], errors="coerce")
        out["EAD"] = observed.where(observed.notna(), proxy)
        out["EAD_source"] = np.where(observed.notna(), "Observed: guaranteed debt", f"Proxy: {ead_share:.0%} of total liabilities")
    else:
        out["EAD"] = proxy
        out["EAD_source"] = f"Proxy: {ead_share:.0%} of total liabilities"
    out["LGD"] = lgd_pct / 100.0
    out["EFC"] = out["PD"] * out["EAD"] * out["LGD"]
    return out


def _share(row, col):
    v = row.get(col) if hasattr(row, "get") else None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def soe_exposures(row: pd.Series) -> dict:
    """Bottom-up shock exposures for one SOE-year. For each exposure the first
    available of: the share reported in the data (observed), a share derived
    from reported amounts (derived), the sector default (fuel only), or the
    generic default in config.DEFAULT_EXPOSURES (placeholder).
    Returns {name: (value, source_label)}, values clipped to 0–1 (elasticity
    and pass-through excepted)."""
    clip = lambda v: max(0.0, min(1.0, v))
    opex, tl = _share(row, "Operating Expense"), _share(row, "Total Liabilities")
    sector = row.get("Sector", "Other") if hasattr(row, "get") else "Other"
    out = {}

    def pick(name, observed_col=None, amount_col=None, denom=None, amount_label=""):
        v = _share(row, observed_col) if observed_col else None
        if v is not None:
            out[name] = (clip(v), f"Observed: {observed_col}")
            return
        a = _share(row, amount_col) if amount_col else None
        if a is not None and denom:
            out[name] = (clip(a / denom), f"Derived: {amount_label}")
            return
        if name == "fuel_cost_share":
            out[name] = (config.SECTOR_FUEL_COST_SHARE.get(sector, config.SECTOR_FUEL_COST_SHARE["Other"]), f"Sector default ({sector})")
            return
        out[name] = (config.DEFAULT_EXPOSURES[name], "Default (placeholder)")

    pick("fuel_cost_share", "Fuel Cost Share", "Fuel Cost", opex, "Fuel Cost / Operating Expense")
    pick("fx_cost_share", "FX Cost Share")
    pick("fx_revenue_share", "FX Revenue Share")
    pick("fx_debt_share", "FX Debt Share", "FX Debt", tl, "FX Debt / Total Liabilities")
    pick("floating_debt_share", "Floating Rate Debt Share")
    pick("near_term_maturity_share", None, "Short Term Debt", tl, "Short Term Debt / Total Liabilities")
    for name in ("tariff_passthrough", "revenue_elasticity", "fuel_subsidy_share"):
        out[name] = (config.DEFAULT_EXPOSURES[name], "Default (placeholder)" if name != "fuel_subsidy_share" else "User (off by default)")
    return out


def recovery_rate_scenarios(sector: str):
    """Four points on the sector's actual GEMs recovery-rate distribution
    (config.SECTOR_RECOVERY_DATA), relabeled as government backstop
    intensity: lender recovery rate (RR) = government LGD directly here
    (not 1 - RR) — the lender recovers a lot precisely because the
    government stepped in to make it whole, so a high RR means a high
    government LGD, i.e. high backstop intensity.
      Low Backstop Intensity     = 10th percentile RR (least the
                                    government has had to absorb)
      25th Percentile            = the reported 25th percentile RR
      Average Backstop Intensity = the reported average RR
      High Backstop Intensity    = 90th percentile RR (most the
                                    government has had to absorb)
    Real distribution points, not an interpolation. Returns a list of
    (label, LGD fraction) tuples, ascending."""
    d = config.SECTOR_RECOVERY_DATA.get(sector, config.SECTOR_RECOVERY_DATA["Other"])
    return [
        ("Low Backstop Intensity", round(d["p10"], 4)),
        ("25th Percentile", round(d["p25"], 4)),
        ("Average Backstop Intensity", round(d["average"], 4)),
        ("High Backstop Intensity", round(d["p90"], 4)),
    ]



def historical_revenue_volatility(df: pd.DataFrame, entity: str):
    """Standard deviation of year-over-year revenue growth for one SOE,
    computed from its own panel data. Returns NaN if the SOE has fewer
    than 3 years of Revenue observations — callers should fall back to
    config.SECTOR_REVENUE_VOLATILITY in that case."""
    d = df[df["Entity"] == entity].sort_values("Year")
    revenue = d["Revenues"].dropna()
    if len(revenue) < 3:
        return np.nan
    growth = revenue.pct_change().dropna()
    if len(growth) < 2:
        return np.nan
    return float(growth.std())


def rating_notch_change(df: pd.DataFrame, entity: str):
    """Change in an SOE's Z-EM-derived rating from its earliest to latest
    available year, in notches (negative = deterioration). Returns
    (first_rating, last_rating, notch_change) — notch_change is None if
    fewer than 2 years of data or a rating fell outside the recognized
    scale."""
    d = df[df["Entity"] == entity].sort_values("Year")
    d = d.dropna(subset=["Rating"])
    if len(d) < 2:
        return None, None, None
    first_rating = d["Rating"].iloc[0]
    last_rating = d["Rating"].iloc[-1]
    first_idx = config.rating_index(first_rating)
    last_idx = config.rating_index(last_rating)
    if first_idx is None or last_idx is None:
        return first_rating, last_rating, None
    return first_rating, last_rating, last_idx - first_idx
