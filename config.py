"""
All tunable numbers for the SOE Fiscal Risk Tool live here — coefficients,
thresholds, theme, chart layout. Change values here; page code shouldn't
need touching for recalibration.
"""

# ---------------------------------------------------------------------------
# Altman Z''-EM (Emerging Market) coefficients
# Z_EM = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4 + 3.25
# ---------------------------------------------------------------------------
ZEM_COEFFICIENTS = {"X1": 6.56, "X2": 3.26, "X3": 6.72, "X4": 1.05}
# No constant: this tool uses the Z'' (Eidelman) convention — the rating
# table and 1.1/2.6 zone cutoffs below are calibrated to the constant-free
# score, not Altman's Z''-EM (+3.25) variant from the shock-framework PDF.
# Mixing the two systematically inflated every score by 3.25.
ZEM_CONSTANT = 0.0

ZEM_LABELS = {
    "X1": "Working Capital / Total Assets",
    "X2": "Retained Earnings / Total Assets",
    "X3": "EBIT / Total Assets",
    "X4": "Book Equity / Total Liabilities",
}

ZEM_DESCRIPTORS = {
    "X1": {
        "strong_positive": "strong working capital position",
        "weak_positive": "modest working capital buffer",
        "negative": "working capital strain (current liabilities exceed current assets)",
    },
    "X2": {
        "strong_positive": "a solid retained earnings base",
        "weak_positive": "a thin retained earnings base",
        "negative": "accumulated losses eroding retained earnings",
    },
    "X3": {
        "strong_positive": "strong operating profitability",
        "weak_positive": "thin operating margins",
        "negative": "operating losses",
    },
    "X4": {
        "strong_positive": "a well-capitalised equity position",
        "weak_positive": "a modest but positive equity buffer",
        "negative": "a negative net worth position (liabilities exceed equity)",
    },
}
ZEM_COMPONENT_STRONG_THRESHOLD = {"X1": 0.15, "X2": 0.05, "X3": 0.05, "X4": 0.20}
SINGLE_DRIVER_SHARE_THRESHOLD = 0.60

ZONES = [
    ("Distress", float("-inf"), 1.1),
    ("Grey", 1.1, 2.6),
    ("Safe", 2.6, float("inf")),
]
Z_DISTRESS_CUTOFF = 1.1
Z_SAFE_CUTOFF = 2.6

# Indicative credit-rating cohort mapping for the Z-EM score, for reference
# only (Z''-Score range -> rating -> 1-yr PD), per the uploaded rating table.
Z_RATING_TABLE = [
    (4.90, float("inf"), "AAA", 0.0002),
    (4.35, 4.90, "AA+", 0.0003),
    (4.05, 4.35, "AA", 0.0004),
    (3.75, 4.05, "AA-", 0.0005),
    (3.60, 3.75, "A+", 0.0007),
    (3.40, 3.60, "A", 0.0008),
    (3.15, 3.40, "A-", 0.0010),
    (3.00, 3.15, "BBB+", 0.0020),
    (2.60, 3.00, "BBB", 0.0025),
    (2.40, 2.60, "BBB-", 0.0032),
    (2.00, 2.40, "BB+", 0.0075),
    (1.70, 2.00, "BB", 0.0100),
    (1.50, 1.70, "BB-", 0.0127),
    (1.25, 1.50, "B+", 0.0147),
    (0.90, 1.25, "B", 0.0207),
    (0.50, 0.90, "B-", 0.0710),
    (-0.05, 0.50, "CCC+", 0.1627),
    (-0.75, -0.05, "CCC", 0.1627),
    (-1.50, -0.75, "CCC-", 0.2000),
    (float("-inf"), -1.50, "D", 0.4000),
]


def z_rating(z):
    """Indicative rating cohort for a Z-EM score, from Z_RATING_TABLE."""
    if z != z:  # NaN
        return "—"
    for lo, hi, rating, _pd in Z_RATING_TABLE:
        if lo < z <= hi or (lo == float("-inf") and z <= hi):
            return rating
    return "—"


# ---------------------------------------------------------------------------
# Probability of Distress
#
# PD_BY_ZONE (3-bucket, from SOE_shock_framework.pdf Section 10) is kept
# only as a coarse fallback for a missing/unrecognized rating. The primary
# calibration is PD_BY_RATING below — the 1-yr PD column from the Z-EM
# rating cohort table (20 rating bands, AAA...D), already embedded in
# Z_RATING_TABLE above but previously unused past the rating letter itself.
# This gives real differentiation within a zone: e.g. a Distress-zone SOE
# rated 'B' (PD 2.07%) is not the same risk as one rated 'D' (PD 40.00%) —
# the old flat 72% for every Distress-zone SOE collapsed that distinction.
# ---------------------------------------------------------------------------
PD_BY_ZONE = {"Distress": 0.72, "Grey": 0.35, "Safe": 0.05}  # coarse fallback only

PD_BY_RATING = {rating: pd for (_lo, _hi, rating, pd) in Z_RATING_TABLE}


def pd_by_rating(rating: str) -> float:
    """Per-rating 1-yr PD from the uploaded rating cohort table. Falls back
    to PD_BY_ZONE via classify_zone(rating's midpoint) only if the rating
    string isn't recognized."""
    if rating in PD_BY_RATING:
        return PD_BY_RATING[rating]
    return float("nan")


def worst_pd_in_zone(zone: str) -> float:
    """The highest 1-yr PD among all rating bands whose Z-score range
    overlaps the given zone (Safe/Grey/Distress) — used as a 'maximum PD'
    reference for the same zone the SOE currently sits in, pending a
    dedicated max-PD table. A rating band straddling a zone boundary (e.g.
    'B', which spans both Distress and Grey) counts toward both zones,
    which is the conservative choice."""
    zone_bounds = {name: (lo, hi) for name, lo, hi in ZONES}
    if zone not in zone_bounds:
        return float("nan")
    lower, upper = zone_bounds[zone]
    candidates = [pd for (r_lo, r_hi, _rating, pd) in Z_RATING_TABLE if r_hi > lower and r_lo < upper]
    return max(candidates) if candidates else float("nan")


LGD_SLIDER_MIN = 1
LGD_SLIDER_MAX = 100
LGD_SLIDER_DEFAULT = 70

# ---------------------------------------------------------------------------
# Government LGD, by sector — sourced from GEMs (Global Emerging Markets Risk
# Database) "Default and Recovery Statistics: Public Lending 1994-2024"
# (EIB/IFC consortium, Table 26, recovery rates by GICS sector).
#
# GEMs measures the LENDER's recovery rate (RR) on public-counterparty
# loans. GEMs states explicitly that these recovery rates are high "because
# of the implicit state guarantees that these borrowers often benefit
# from" — the lender recovers a lot precisely BECAUSE the government steps
# in as guarantor of last resort. That support is the same money on both
# sides of the transaction: what the lender recovers IS what the
# government paid out to make the lender whole. So lender RR = government
# LGD directly (NOT 1 - RR) — a high lender recovery rate means the
# government absorbed a lot, i.e. a high government LGD. Flagged as a
# working assumption (lender RR as a proxy for government LGD), not an
# established fact, pending a direct source.
#
# Sector mapping (GEMs' raw GICS sector -> this tool's sector categories):
#   Transport, Industry   -> GICS "Industrials" (airlines/rail/road sit here)
#   Power / Utilities     -> GICS "Utilities"
#   Telecoms              -> GICS "Communication services"
#   Other                 -> GICS "Others" (direct match)
#   Energy, Agriculture   -> GEMs' Energy and Consumer staples rows are
#                            undisclosed (below GEMs' own 10-contract
#                            minimum) -> fall back to the "Overall" row,
#                            per the fallback rule agreed for this build.
#
# Decision rule: a disclosed sector, however thin its sample (e.g.
# Communication services and Materials both have only 11 defaulted
# contracts), is kept as reported — no shrinkage. Only an undisclosed
# (blank) sector falls back to Overall.
# ---------------------------------------------------------------------------
SECTOR_RECOVERY_DATA = {
    "Transport": {"average": 0.933, "p10": 0.813, "p25": 0.960, "p90": 1.000, "n_defaults": 49, "gems_source": "Industrials"},
    "Energy": {"average": 0.858, "p10": 0.521, "p25": 0.853, "p90": 1.000, "n_defaults": 308, "gems_source": "Overall (Energy undisclosed by GEMs)"},
    "Power / Utilities": {"average": 0.878, "p10": 0.523, "p25": 0.912, "p90": 1.000, "n_defaults": 92, "gems_source": "Utilities"},
    "Agriculture": {"average": 0.858, "p10": 0.521, "p25": 0.853, "p90": 1.000, "n_defaults": 308, "gems_source": "Overall (Consumer staples undisclosed by GEMs)"},
    "Industry": {"average": 0.933, "p10": 0.813, "p25": 0.960, "p90": 1.000, "n_defaults": 49, "gems_source": "Industrials"},
    "Telecoms": {"average": 0.799, "p10": 0.374, "p25": 0.645, "p90": 1.000, "n_defaults": 11, "gems_source": "Communication services"},
    "Other": {"average": 0.824, "p10": 0.515, "p25": 0.742, "p90": 1.000, "n_defaults": 111, "gems_source": "Others"},
}

# Derived display range per sector: (low government LGD, high government
# LGD) = (p10 RR, p90 RR) directly — since RR = LGD here, not 1-RR. Single
# source of truth is SECTOR_RECOVERY_DATA above; this is computed from it,
# not maintained separately.
SECTOR_LGD_REFERENCE = {
    sector: (round(d["p10"], 4), round(d["p90"], 4))
    for sector, d in SECTOR_RECOVERY_DATA.items()
}
EAD_METHOD = "total_liabilities"

# ---------------------------------------------------------------------------
# KPI specs — formula inputs (`requires`, our raw column names), direction,
# red/amber/green cuts (illustrative IMF SOE Health Check Tool-style
# starting points, pending recalibration), and the description shown under
# each chart. `requires` names are checked against the ingested DataFrame's
# raw columns (before ratio computation) to decide if a KPI is available.
# ---------------------------------------------------------------------------
KPI_THRESHOLDS = {
    "operating_margin": {
        "label": "Operating margin", "unit": "%", "direction": "higher_is_better",
        "red_cut": 0.0, "green_cut": 0.10,
        "requires": ["Operating Profits (EBIT)", "Revenues"],
        "description": "EBIT as a share of revenue. Negative means operating losses before financing costs.",
    },
    "net_margin": {
        "label": "Net margin", "unit": "%", "direction": "higher_is_better",
        "red_cut": 0.0, "green_cut": 0.05,
        "requires": ["Net Income", "Revenues"],
        "description": "Bottom-line profit as a share of revenue, after interest and tax.",
    },
    "ebitda_margin": {
        "label": "EBITDA margin", "unit": "%", "direction": "higher_is_better",
        "red_cut": 0.0, "green_cut": 0.15,
        "requires": ["EBITDA", "Revenues"],
        "description": "Cash operating profitability before depreciation, interest, and tax.",
    },
    "roa": {
        "label": "Return on assets", "unit": "%", "direction": "higher_is_better",
        "red_cut": 0.0, "green_cut": 0.03,
        "requires": ["Net Income", "Total Assets"],
        "description": "Net income relative to the asset base — how efficiently assets generate profit.",
    },
    "roe": {
        "label": "Return on equity", "unit": "%", "direction": "higher_is_better",
        "red_cut": 0.0, "green_cut": 0.10,
        "requires": ["Net Income", "Equity"],
        "description": "Net income relative to equity. Suppressed when equity is negative — the ratio's sign flips and no longer means what it normally means.",
    },
    "current_ratio": {
        "label": "Current ratio", "unit": "x", "direction": "higher_is_better",
        "red_cut": 1.0, "green_cut": 1.5,
        "requires": ["Current Assets", "Current Liabilities"],
        "description": "Current assets divided by current liabilities. Below 1x signals a liquidity squeeze.",
    },
    "working_capital_ratio": {
        "label": "Working capital / assets", "unit": "%", "direction": "higher_is_better",
        "red_cut": -0.05, "green_cut": 0.05,
        "requires": ["Current Assets", "Current Liabilities", "Total Assets"],
        "description": "Net working capital as a share of total assets — this is Altman's X1 component.",
    },
    "debt_to_ebitda": {
        "label": "Debt / EBITDA", "unit": "x", "direction": "lower_is_better",
        "red_cut": 6.0, "green_cut": 4.0,
        "requires": ["Total Liabilities", "EBITDA"],
        "description": "Total liabilities relative to EBITDA — roughly, years of cash operating profit to repay debt. Suppressed when EBITDA is negative.",
    },
    "liabilities_to_assets": {
        "label": "Liabilities / assets", "unit": "%", "direction": "lower_is_better",
        "red_cut": 0.85, "green_cut": 0.65,
        "requires": ["Total Liabilities", "Total Assets"],
        "description": "Overall leverage — how much of the asset base is financed by liabilities rather than equity.",
    },
    "interest_coverage": {
        "label": "Interest coverage", "unit": "x", "direction": "higher_is_better",
        "red_cut": 1.0, "green_cut": 2.5,
        "requires": ["Operating Profits (EBIT)", "Interest Expense"],
        "description": "EBIT divided by interest expense. Below 1x means operating profit can't cover debt service.",
    },
    "debt_to_equity": {
        "label": "Debt / equity", "unit": "x", "direction": "lower_is_better",
        "red_cut": 3.0, "green_cut": 1.5,
        "requires": ["Total Liabilities", "Equity"],
        "description": "Total liabilities relative to equity. Suppressed when equity is negative.",
    },
    "asset_turnover": {
        "label": "Asset turnover", "unit": "x", "direction": "higher_is_better",
        "red_cut": 0.2, "green_cut": 0.6,
        "requires": ["Revenues", "Total Assets"],
        "description": "Revenue generated per unit of assets. Supplementary only — excluded from the Z-EM formula itself.",
    },
    "depreciation_to_ebitda": {
        "label": "Depreciation / EBITDA", "unit": "%", "direction": "lower_is_better",
        "red_cut": 0.60, "green_cut": 0.30,
        "requires": ["Depreciation", "EBITDA"],
        "description": "A proxy for capital intensity — how much of cash operating profit is absorbed by depreciation.",
    },
    "grants_to_revenue": {
        "label": "Grants / revenue", "unit": "%", "direction": "lower_is_better",
        "red_cut": 0.50, "green_cut": 0.25,
        "requires": ["Government Grants", "Revenues"],
        "description": "Government grants relative to revenue — a direct measure of fiscal dependency.",
    },
    "grants_to_expense": {
        "label": "Grants / total expense", "unit": "%", "direction": "lower_is_better",
        "red_cut": 0.40, "green_cut": 0.20,
        "requires": ["Government Grants", "Total Expense"],
        "description": "Government grants relative to total expense — how much of spending grants cover.",
    },
    "effective_tax_rate": {
        "label": "Effective tax rate", "unit": "%", "direction": "lower_is_better",
        "red_cut": 0.40, "green_cut": 0.25,
        "requires": ["Tax Expense", "Operating Profits (EBIT)"],
        "description": "Tax expense relative to EBIT. Only meaningful when EBIT is positive.",
    },
}

KPI_CATEGORIES = {
    "profitability": ["operating_margin", "net_margin", "ebitda_margin", "roa", "roe"],
    "liquidity": ["current_ratio", "working_capital_ratio"],
    "solvency": ["debt_to_ebitda", "liabilities_to_assets", "interest_coverage", "debt_to_equity", "asset_turnover", "depreciation_to_ebitda"],
    "fiscal_dependency": ["grants_to_revenue", "grants_to_expense", "effective_tax_rate"],
}
CATEGORY_LABELS = {
    "profitability": "Profitability",
    "liquidity": "Liquidity",
    "solvency": "Solvency",
    "fiscal_dependency": "Fiscal dependency",
}
CATEGORY_ORDER = ["profitability", "liquidity", "solvency", "fiscal_dependency"]

# ---------------------------------------------------------------------------
# Shock module defaults — sector fuel cost shares from SOE_shock_framework.pdf
# (Section 4); remaining defaults are starting points pending calibration.
#
# Shock magnitudes follow the standard DSA/DSF convention: FX depreciation
# 30%, interest-rate shock 200bps. Sliders on the Shock Scenarios page also
# now permit negative values (favorable shocks — cheaper fuel, currency
# appreciation, rate cuts, arrears clearing), not just adverse ones.
# ---------------------------------------------------------------------------
SECTOR_FUEL_COST_SHARE = {
    "Transport": 0.38, "Energy": 0.25, "Power / Utilities": 0.25,
    "Agriculture": 0.20, "Industry": 0.15, "Telecoms": 0.15, "Other": 0.20,
}

# Sector fallback for revenue-growth volatility, used when an SOE has fewer
# than 3 years of data to compute its own historical volatility. Illustrative
# starting points pending calibration against a larger panel.
SECTOR_REVENUE_VOLATILITY = {
    "Transport": 0.15, "Energy": 0.10, "Power / Utilities": 0.10,
    "Agriculture": 0.20, "Industry": 0.12, "Telecoms": 0.08, "Other": 0.15,
}

DEFAULT_SHOCK_PARAMS = {
    "fuel_shock_pct": 0.25, "tariff_passthrough": 0.50, "fx_shock_pct": 0.30,
    "fx_cost_share": 0.20, "fx_revenue_share": 0.10, "fx_debt_share": 0.30,
    "floating_debt_share": 0.40, "rate_shock_bps": 200,
    "revenue_shock_std_devs": -1.0, "revenue_elasticity": 1.00,
    "arrears_pct_of_revenue": 0.05, "shock_duration_years": 2,
    "near_term_maturity_share": 0.20, "refinancing_spread_bps": 150,
    # Case C of the fuel transmission: share of the fuel-cost increase the
    # government absorbs through a subsidy. It never reaches the SOE's EBIT
    # but is a direct budget outlay, reported next to EFC. 0 = off.
    "fuel_subsidy_share": 0.0,
}

# Exposure starting values when an SOE's data carry no exposure columns
# (placeholders — replace with SOE-specific values from notes to the accounts
# or an SOE questionnaire; see calculations.soe_exposures for the order in
# which observed / derived / default values are used).
DEFAULT_EXPOSURES = {
    "tariff_passthrough": 0.50, "fx_cost_share": 0.20, "fx_revenue_share": 0.10,
    "fx_debt_share": 0.30, "floating_debt_share": 0.40, "near_term_maturity_share": 0.20,
    "revenue_elasticity": 1.00, "fuel_subsidy_share": 0.0,
}

# Exposure at default: EAD = share × total liabilities (a proxy for the part
# of the balance sheet the government would stand behind), or observed
# government-guaranteed debt where the data carry it. 1.0 reproduces the
# original "EAD = total liabilities" assumption; 0.6 / 0.8 are the
# sensitivity cases discussed for SOEs without guarantee data.
EAD_SHARE_DEFAULT = 1.0
EAD_SHARE_PRESETS = [0.6, 0.8, 1.0]

# Monte Carlo: interest-rate and revenue shocks can be drawn too (standard
# deviations 0 = held at the slider value, as in the original tool). Pairwise
# correlations, keyed "a|b"; only fuel–FX is non-zero by default.
MC_DEFAULT_RATE_STD_BPS = 0.0
MC_DEFAULT_REVENUE_STD_SD = 0.0
MC_DEFAULT_CORRELATIONS = {
    "fuel|fx": 0.30, "fuel|rate": 0.0, "fuel|revenue": 0.0,
    "fx|rate": 0.0, "fx|revenue": 0.0, "rate|revenue": 0.0,
}
MC_DEFAULT_SIMULATIONS = 1000
MC_DEFAULT_FUEL_STD = 0.10
MC_DEFAULT_FX_STD = 0.08
MC_DEFAULT_CORRELATION = 0.30
MC_HORIZON_YEARS = 3
DEFAULT_GDP_GROWTH = 0.03

# ---------------------------------------------------------------------------
# Ingestion schema
# ---------------------------------------------------------------------------
REQUIRED_COLUMNS = [
    "Entity", "Year", "Sector", "Revenues", "Total Expense", "Operating Expense",
    "Operating Profits (EBIT)", "Net Income", "Current Assets", "Total Assets",
    "Current Liabilities", "Total Liabilities", "Equity", "Retained Earnings",
    "Interest Expense", "Tax Expense", "EBITDA", "Government Grants",
    "Depreciation", "Currency", "Units",
]
OPTIONAL_SHOCK_COLUMNS = [
    "Cash and Equivalents", "FX Revenue Share", "FX Cost Share", "FX Debt Share",
    "Floating Rate Debt Share", "Short Term Debt", "Government Arrears Owed",
    "Fuel Cost Share",
]

# ---------------------------------------------------------------------------
# Theme — World Bank navy title band / top nav, bright-blue accent, and
# good / watch / alert status colors. Matches the interactive HTML version
# (templates/app.css) so the Streamlit app and the HTML file read as one
# product. Keys are unchanged from the earlier palette, so page code that
# refers to e.g. THEME["chart_navy"] or THEME["gold"] keeps working.
# ---------------------------------------------------------------------------
FONT_SCALE = 1.2
BASE_ROOT_PX = 16


def fs(px):
    return f"{round(px * FONT_SCALE, 1)}px"


THEME = {
    # top nav / title band
    "sidebar_bg": "#002244", "sidebar_bg_active": "#0B3A66",
    "sidebar_text": "#C6D0DB", "sidebar_text_active": "#FFFFFF",
    # surfaces and text
    "bg": "#F3F5F8", "card": "#FFFFFF", "border": "#E1E6EC", "line": "#E1E6EC",
    "text": "#1C2530", "ink2": "#4C5A68", "muted": "#76828F", "heading": "#002244",
    # accent (World Bank bright blue) and its stronger text shade
    "blue": "#0071BC", "blue_bg": "#E5F5FB", "accent": "#009FDA",
    # "gold" is the highlight color in charts (latest-year bar, markers)
    "gold": "#009FDA", "gold_bg": "#E5F5FB",
    # status: good / watch / alert — *_ink is the readable text shade
    "green": "#00A996", "green_bg": "#E5F6F4", "green_ink": "#00796B",
    "amber": "#F7B841", "amber_bg": "#FEF1D9", "amber_ink": "#8A5D00",
    "red": "#D03B3B", "red_bg": "#FAEBEB", "red_ink": "#B12F2F",
    "purple": "#002244", "purple_bg": "#E6EAF0",
    "chart_navy": "#002244", "chart_navy_bg": "#E6EAF0",
    "chart_cyan": "#009FDA", "chart_cyan_bg": "#E5F5FB",
}

ZONE_COLORS = {"Safe": THEME["green"], "Grey": THEME["amber"], "Distress": THEME["red"]}
ZONE_STYLE = {
    "Distress": {"color": THEME["red"], "bg": THEME["red_bg"]},
    "Grey": {"color": THEME["amber"], "bg": THEME["amber_bg"]},
    "Safe": {"color": THEME["green"], "bg": THEME["green_bg"]},
}

CHART_HEIGHT = 230
CHART_LAYOUT = dict(
    height=CHART_HEIGHT,
    margin=dict(l=6, r=6, t=6, b=6),
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Open Sans, Segoe UI, sans-serif", size=round(11 * FONT_SCALE, 1), color=THEME["text"]),
    bargap=0.45,
    bargroupgap=0.15,
    showlegend=False,
)
BAR_CORNER_RADIUS = 3
LINE_SHAPE = "linear"
LINE_SMOOTHING = 0.0
# Every line chart is drawn as a smooth curve through the data points: a cardinal
# spline (tension × the Catmull-Rom tangent, natural ends). 1.0 = Catmull-Rom,
# lower = tighter curve with less overshoot between points. Used by
# utils/charts.smooth_xy (Plotly pages) and templates/app.js (HTML version).
LINE_SMOOTH_TENSION = 0.75

# ---------------------------------------------------------------------------
# Plain-language definitions — used for hover tooltips (ⓘ icons) and the
# Home page glossary. Written for a reader with no finance background.
# ---------------------------------------------------------------------------
GLOSSARY = {
    "Z-EM score": "A single number summarizing an SOE's financial health from its balance sheet — the higher, the healthier. Built from four ratios (X1–X4) below.",
    "X1": "Working capital ÷ total assets. Measures short-term liquidity — can the SOE cover bills due soon with cash and near-cash assets?",
    "X2": "Retained earnings ÷ total assets. A running total of profit (or loss) kept in the business over its life — negative means accumulated losses.",
    "X3": "EBIT ÷ total assets. How much operating profit the SOE generates from what it owns, before interest and tax.",
    "X4": "Equity ÷ total liabilities. How much of the SOE is financed by its own capital versus borrowed money — negative equity means liabilities exceed what the SOE owns.",
    "Zone": "Safe, Grey, or Distress — a plain-language read of the Z-EM score. Safe > 2.6, Grey 1.1–2.6, Distress ≤ 1.1.",
    "Rating": "An indicative credit-rating letter grade (AAA…D) mapped from the Z-EM score, for reference only — not an actual credit rating from a rating agency.",
    "PD": "Probability of Distress — the estimated chance the SOE ends up in financial distress within a year, taken from the one-year PD of its Z-EM rating band (AAA…D).",
    "EAD": "Exposure at Default — how much money the government could be on the hook for if the SOE defaults. Currently approximated by Total Liabilities.",
    "LGD": "Loss Given Default — of the exposure (EAD), what share the government would actually lose, after any recovery (asset sales, restructuring). You set this — 100% means nothing is recovered.",
    "EFC": "Expected Fiscal Cost = PD × EAD × LGD. The average fiscal cost to government you'd expect if this scenario played out many times.",
    "Fuel shock": "How much more expensive fuel becomes, as a percentage. 25% means fuel prices rise by a quarter.",
    "Tariff pass-through": "How much of a fuel-price rise the SOE is allowed to charge back to customers. 0% means the SOE absorbs the whole shock itself; 100% means customers pay all of it and the SOE's costs are unaffected.",
    "FX shock": "How much the local currency weakens against a hard currency like the US dollar. 15% means it now takes 15% more local currency to buy the same US$1.",
    "Interest rate shock": "How much borrowing costs rise, in basis points (100 bps = 1 percentage point). Only affects the share of debt at a floating (adjustable) interest rate.",
    "GDP/demand shock": "How much the wider economy contracts or grows, which affects how much customers buy from the SOE.",
    "Revenue shock": "A shock to the SOE's revenue, sized in standard deviations of its own historical revenue volatility (or a sector default) rather than a flat percentage — the standard debt-sustainability-analysis convention.",
    "Refinancing shock": "The extra interest cost of rolling over debt that's coming due soon, at a stressed spread — distinct from a floating-rate shock, which reprices debt already on a variable rate.",
    "Government arrears": "Money the government owes the SOE (e.g. for services already delivered) but hasn't yet paid — this can squeeze the SOE's cash even if its accounting profit looks fine.",
    "Monte Carlo simulation": "Instead of one shock scenario, the tool runs thousands of random shock combinations to show a range of possible outcomes, not just one guess.",
    "Fiscal-at-risk": "The 95th-percentile Expected Fiscal Cost across all simulations — a 'bad but plausible' scenario, not the worst case and not the average.",
}

# ---------------------------------------------------------------------------
# Government support / strategic-SOE notch adjustment — a SIMPLIFIED, openly
# labeled proxy for S&P Global Ratings' "Rating Government-Related Entities:
# Methodology And Assumptions" (25-Mar-2015). This is NOT a replica of S&P's
# actual Role-Link matrix or notching tables (their real cell values weren't
# available to transcribe) — it is a transparent, editable stand-in built to
# the same two-dimensional logic: Role x Link -> a likelihood-of-support
# tier -> a bounded notch uplift, capped by the sovereign's own rating.
#
# Same rating alphabet as Z_RATING_TABLE above, so an SOE's Z-EM-derived
# rating and a sovereign's credit rating sit on one shared scale with no
# translation needed.
# ---------------------------------------------------------------------------

# Ascending order: index 0 = worst (D), index 19 = best (AAA). Matches the
# rating letters produced by z_rating() above.
RATING_SCALE_ASC = [
    "D", "CCC-", "CCC", "CCC+", "B-", "B", "B+", "BB-", "BB", "BB+",
    "BBB-", "BBB", "BBB+", "A-", "A", "A+", "AA-", "AA", "AA+", "AAA",
]
SOVEREIGN_RATING_OPTIONS = list(reversed(RATING_SCALE_ASC))  # best-first, for a dropdown
SOVEREIGN_OUTLOOK_OPTIONS = ["Stable", "Positive", "Negative"]


def rating_notch_shift(rating: str, notches: int) -> str:
    """Shift a rating letter up (positive) or down (negative) by `notches`,
    clipped to the scale's ends. Returns the input unchanged if it isn't a
    recognized rating (e.g. '—')."""
    if rating not in RATING_SCALE_ASC:
        return rating
    idx = RATING_SCALE_ASC.index(rating)
    idx = max(0, min(len(RATING_SCALE_ASC) - 1, idx + notches))
    return RATING_SCALE_ASC[idx]


def rating_index(rating: str):
    return RATING_SCALE_ASC.index(rating) if rating in RATING_SCALE_ASC else None


# --- Role: how important is a default of this SOE to the government? ---
# Paraphrased from S&P's Table 2 ("Assessing The Importance Of A GRE's Role
# To The Government").
ROLE_LEVELS = ["Critical", "Very Important", "Important", "Limited Importance"]
ROLE_SCORE = {"Critical": 4, "Very Important": 3, "Important": 2, "Limited Importance": 1}
ROLE_CRITERIA = {
    "Critical": "The SOE operates essentially on behalf of the government — providing a key public service the government would have to provide itself if the SOE didn't exist — or is among the most important SOEs in the country/sector.",
    "Very Important": "Default would have a major impact: either a not-for-profit entity central to a key policy objective, or a profit-seeking SOE whose distress would significantly disrupt the local economy.",
    "Important": "Default would have an important but manageable impact — the SOE provides essential infrastructure or services, or its distress would meaningfully affect one sector of the economy.",
    "Limited Importance": "Default would have a limited impact — one of many similar SOEs, easily substituted, or the government cares more about jobs/operations than its credit standing.",
}

# --- Link: how tightly bound is the government to this SOE? ---
# Paraphrased from S&P's Table 3 ("Assessing The Strength And Durability Of
# The Link Between The Government And A GRE").
LINK_LEVELS = ["Integral", "Very Strong", "Strong", "Limited"]
LINK_SCORE = {"Integral": 4, "Very Strong": 3, "Strong": 2, "Limited": 1}
LINK_CRITERIA = {
    "Integral": "Essentially an arm of, or very tightly controlled by, the government — a legal framework provides for explicit support, and there's a track record of considerable, timely credit support in all circumstances.",
    "Very Strong": "A very strong, durable link — the government is a strong stable shareholder driving strategy, and has a track record of very strong, timely credit support in most circumstances.",
    "Strong": "The government is an important (often controlling) shareholder with a policy or track record of support in certain circumstances, but governance is more independent, privatization may be contemplated, or a legal framework partly constrains intervention.",
    "Limited": "The government is a minority or non-shareholder with little interference, has very limited capacity or willingness to support on a timely basis, or a track record of adverse intervention.",
}

# --- Role x Link -> likelihood-of-support tier ---
# Simplified: sum the two ordinal scores (range 2-8) and map onto S&P's
# named tiers. This is a stand-in for S&P's actual Role-Link matrix (Table
# 1), not a reproduction of it.
LIKELIHOOD_TIERS_ASC = ["Low", "Moderate", "Moderately High", "High", "Very High", "Extremely High", "Almost Certain"]
_ROLE_LINK_SCORE_TO_TIER = {2: "Low", 3: "Moderate", 4: "Moderately High", 5: "High", 6: "Very High", 7: "Extremely High", 8: "Almost Certain"}


def role_link_to_likelihood(role: str, link: str) -> str:
    combined = ROLE_SCORE.get(role, 1) + LINK_SCORE.get(link, 1)
    return _ROLE_LINK_SCORE_TO_TIER.get(combined, "Low")


# Max notch uplift allowed for each likelihood tier, and the minimum gap
# that must remain below the sovereign's own rating (0 = may equalize with
# the sovereign; None on max_notches = uplift only bounded by the gap).
LIKELIHOOD_UPLIFT = {
    "Almost Certain": {"max_notches": None, "min_gap_to_sovereign": 0},
    "Extremely High": {"max_notches": 6, "min_gap_to_sovereign": 1},
    "Very High": {"max_notches": 5, "min_gap_to_sovereign": 2},
    "High": {"max_notches": 4, "min_gap_to_sovereign": 3},
    "Moderately High": {"max_notches": 3, "min_gap_to_sovereign": 4},
    "Moderate": {"max_notches": 2, "min_gap_to_sovereign": 5},
    "Low": {"max_notches": 0, "min_gap_to_sovereign": None},
}

# Dynamic cap (S&P criteria, paragraph 47): if the SOE's own rating has
# fallen sharply and the sovereign outlook is Negative, the support
# assumption itself is capped, regardless of the Role/Link inputs — this
# is what stops the notch uplift from freezing at an optimistic setting
# while the underlying SOE deteriorates.
DYNAMIC_CAP_TRIGGER_NOTCHES = 3  # rating fall (in notches) across available years that triggers the cap
DYNAMIC_CAP_TIER = "Moderate"  # likelihood tier ceiling once triggered


# ---------------------------------------------------------------------------
# Interactive HTML version (report.py, "Report" page)
#
# The HTML page runs the same calculations in the browser (templates/engine.js)
# with every number from this file; the settings here only decide what it shows. Trigger rules and the EFC/GDP status bands are
# illustrative, like the KPI cutoffs — recalibrate before official use.
# ---------------------------------------------------------------------------
REPORT_TITLE = "SOE Fiscal Risk Dashboard"

# KPIs shown in the scorecard's default "Headline" view (one or two per category).
REPORT_HEADLINE_KPIS = [
    "operating_margin", "roa", "current_ratio", "liabilities_to_assets",
    "debt_to_ebitda", "interest_coverage", "grants_to_revenue",
]

# Standard stress: shock magnitudes and exposures come from DEFAULT_SHOCK_PARAMS
# (DSA/DSF convention). Each channel below is also run on its own so the report
# can show which shock does the damage. Keys are DEFAULT_SHOCK_PARAMS magnitude keys.
REPORT_STRESS_CHANNELS = {
    "fuel": ("Fuel", "fuel_shock_pct"),
    "fx": ("FX", "fx_shock_pct"),
    "rate": ("Interest rate", "rate_shock_bps"),
    "revenue": ("Revenue", "revenue_shock_std_devs"),
    "refi": ("Refinancing", "refinancing_spread_bps"),
    "arrears": ("Arrears", "arrears_pct_of_revenue"),
}

# EFC as a share of GDP — status bands for the overview tile (illustrative).
REPORT_EFC_GDP_WATCH = 0.005
REPORT_EFC_GDP_ALERT = 0.010

# Trigger rules evaluated per SOE in report.py (evaluation logic keyed by id).
# level: "alert" | "watch" | "ok". Actions are examples of pre-agreed responses.
TRIGGER_RULES = [
    {"id": "distress", "level": "alert", "short": "Distress zone",
     "condition": f"Z″ ≤ {Z_DISTRESS_CUTOFF} (distress zone)",
     "action": "Activate the intervention protocol · require a restructuring plan · budget the expected fiscal cost explicitly for next year"},
    {"id": "neg_equity", "level": "alert", "short": "Negative equity",
     "condition": "Book equity ≤ 0 (liabilities exceed assets)",
     "action": "Treat liabilities as a likely call on the budget · assess recapitalisation against restructuring"},
    {"id": "debt_ebitda", "level": "alert", "short": "Debt/EBITDA",
     "condition": f"Debt/EBITDA > {KPI_THRESHOLDS['debt_to_ebitda']['red_cut']:.0f}× or EBITDA ≤ 0",
     "action": "Prior approval for new borrowing and guarantees · review tariffs and public-service compensation"},
    {"id": "stress_drop", "level": "alert", "short": "Fails stress test",
     "condition": "Standard stress drops the SOE one zone or more below its no-shock path",
     "action": "Record the contingent liability in the fiscal risk statement · consider risk financing for the exposure"},
    {"id": "grey", "level": "watch", "short": "Grey zone",
     "condition": f"{Z_DISTRESS_CUTOFF} < Z″ ≤ {Z_SAFE_CUTOFF} (grey zone)",
     "action": "Quarterly financial monitoring · require a performance improvement plan"},
    {"id": "rating_fall", "level": "watch", "short": "Rating falling",
     "condition": f"Indicative rating down {DYNAMIC_CAP_TRIGGER_NOTCHES}+ notches from the first to the latest year",
     "action": f"Cap assumed government support at {DYNAMIC_CAP_TIER} (GRE dynamic cap) · commission a deep-dive review"},
    {"id": "grant_dependency", "level": "watch", "short": "Grant-dependent",
     "condition": f"Grants / revenue > {KPI_THRESHOLDS['grants_to_revenue']['red_cut']:.0%} — Z″ likely overstates health",
     "action": "Read Z″ together with fiscal-dependency KPIs · review the transfer framework"},
    {"id": "routine", "level": "ok", "short": "Routine",
     "condition": f"Z″ > {Z_SAFE_CUTOFF} and no other rule fires",
     "action": "Routine annual monitoring"},
]


# ---------------------------------------------------------------------------
# Parameter register — every number the tool uses, where it comes from, and
# whether it is backed by literature / data, set by the user, a working proxy,
# or a placeholder that still needs a source. Shown on the "Assumptions &
# sources" page and in the HTML version, so no number in the dashboard is a
# magic number. Keep it in step when you change a value above.
#   status: "literature" | "user" | "proxy" | "placeholder" | "design"
# ---------------------------------------------------------------------------
PARAMETER_STATUS_LABELS = {
    "literature": "Literature / data",
    "user": "User-set in the tool",
    "proxy": "Proxy — working assumption",
    "placeholder": "Placeholder — needs a source",
    "design": "Model design choice — needs justification",
}


def _p(group, parameter, value, status, source, used_in):
    return {"group": group, "parameter": parameter, "value": value, "status": status, "source": source, "used_in": used_in}


_S = DEFAULT_SHOCK_PARAMS
PARAMETER_REGISTER = [
    _p("Distress score", "Z″ coefficients (X1–X4)", ", ".join(f"{k} {v}" for k, v in ZEM_COEFFICIENTS.items()), "literature",
       "Altman, Hartzell & Peck (1995); Altman (2005), Emerging Markets Review 6(4) — four-ratio Z″ for non-manufacturers", "Altman Z-EM, every downstream page"),
    _p("Distress score", "Constant", f"{ZEM_CONSTANT}", "literature",
       "Z″ (Eidelman) convention without the +3.25 EM constant — citation to verify", "Altman Z-EM"),
    _p("Distress score", "Zone cutoffs", f"distress ≤ {Z_DISTRESS_CUTOFF}, safe > {Z_SAFE_CUTOFF}", "literature",
       "Altman Z″ zones (1.1 / 2.6) for the constant-free score", "Altman Z-EM, EFC, triggers"),
    _p("Distress score", "Rating bands (20, AAA…D)", "Z_RATING_TABLE", "literature",
       "Rating cohort table supplied to the project (Altman 2005 mapping) — original source to cite", "Ratings, PD"),
    _p("Probability of distress", "One-year PD by rating", "0.02% (AAA) … 40% (D)", "literature",
       "PD column of the rating cohort table — S&P annual default study, year to confirm", "EFC, shocks, Monte Carlo"),
    _p("Probability of distress", "Zone-maximum PD", "max PD among bands overlapping the zone", "placeholder",
       "Interim reference pending a dedicated maximum-PD table", "EFC backstop chart"),
    _p("Probability of distress", "Legacy PD by zone", ", ".join(f"{k} {v:.0%}" for k, v in PD_BY_ZONE.items()), "placeholder",
       "SOE shock framework note (s.10); kept only as a documented legacy value, not used", "—"),
    _p("Exposure at default", "EAD basis", f"share × total liabilities (default {EAD_SHARE_DEFAULT:.0%}); guaranteed debt if observed", "proxy",
       "Implicit-guarantee assumption; 60% / 80% sensitivity cases from the team discussion", "EFC, shocks"),
    _p("Loss given default", "LGD", f"{LGD_SLIDER_DEFAULT}% default, {LGD_SLIDER_MIN}–{LGD_SLIDER_MAX}%", "user",
       "Set by the user; GEMs sector values shown as reference", "EFC, shocks"),
    _p("Loss given default", "Sector LGD reference (GEMs)", "Avg / P10 / P25 / P90 by sector", "literature",
       "GEMs Consortium (2025), Default and Recovery Statistics: Public Lending 1994–2024, Table 26 — lender recovery rate taken as government LGD (working assumption)", "EFC backstop chart"),
    _p("KPIs", "Red / amber / green cutoffs (16 ratios)", "see KPI_THRESHOLDS", "placeholder",
       "IMF SOE Health Check Tool-style starting points; not calibrated to a country or sector sample", "KPI Dashboard, triggers"),
    _p("KPIs", "Suppression rule", "ROE, D/E, D/EBITDA, Dep/EBITDA, ETR → n/a when the denominator ≤ 0", "design",
       "Avoids reading a sign-flipped ratio as good; shown as a flag", "KPI Dashboard"),
    _p("Shock magnitudes", "FX depreciation (standard stress)", f"{_S['fx_shock_pct']:.0%}", "literature",
       "IMF–World Bank LIC DSF Guidance Note (2018) standard exchange-rate shock — paragraph to cite", "Standard stress, Early Warning"),
    _p("Shock magnitudes", "Interest-rate shock (standard stress)", f"+{_S['rate_shock_bps']:.0f} bps", "literature",
       "DSF / MAC SRDSF standard interest-rate shock — paragraph to cite", "Standard stress"),
    _p("Shock magnitudes", "Revenue shock (standard stress)", f"{_S['revenue_shock_std_devs']:+.0f} s.d. of own revenue growth", "literature",
       "DSF convention of shocks sized in historical standard deviations", "Standard stress"),
    _p("Shock magnitudes", "Fuel price shock (standard stress)", f"+{_S['fuel_shock_pct']:.0%}", "placeholder",
       "Illustrative; calibrate from oil-price history (e.g. a one-s.d. annual move)", "Standard stress"),
    _p("Shock magnitudes", "Refinancing spread (standard stress)", f"+{_S['refinancing_spread_bps']:.0f} bps", "placeholder",
       "Illustrative; calibrate from sovereign/SOE spread episodes", "Standard stress"),
    _p("Shock magnitudes", "Government arrears (standard stress)", f"{_S['arrears_pct_of_revenue']:.0%} of revenue a year", "placeholder",
       "Illustrative; calibrate from arrears data where available", "Standard stress"),
    _p("Shock dynamics", "Shock profile", f"full magnitude for {_S['shock_duration_years']} years, then off (no AR(1))", "design",
       "Step profile chosen for transparency; persistence (years) to be justified from data — the tool does not use an AR(1) process", "Shock Scenarios, Monte Carlo"),
    _p("Shock dynamics", "Projection horizon", f"{MC_HORIZON_YEARS} years (1–7)", "user", "Set by the user", "Shock Scenarios"),
    _p("Exposures", "Sector fuel cost share of opex", ", ".join(f"{k} {v:.0%}" for k, v in SECTOR_FUEL_COST_SHARE.items()), "literature",
       "SOE fuel-shock framework note (April 2026, internal) — source table to cite; used only when the SOE's own fuel data are missing", "Fuel shock"),
    _p("Exposures", "Default exposure shares", ", ".join(f"{k} {v:g}" for k, v in DEFAULT_EXPOSURES.items() if k not in ("revenue_elasticity", "fuel_subsidy_share")), "placeholder",
       "Generic starting values; replaced per SOE when the data carry FX / floating / short-term debt / fuel columns (bottom-up)", "Shock Scenarios"),
    _p("Exposures", "EBIT elasticity to revenue", f"{DEFAULT_EXPOSURES['revenue_elasticity']}", "placeholder",
       "1.0 = costs fixed in the short run; estimate from the SOE's cost structure", "Revenue shock"),
    _p("Exposures", "Tariff pass-through of fuel costs", f"{DEFAULT_EXPOSURES['tariff_passthrough']:.0%}", "placeholder",
       "Depends on the regulatory regime; set per SOE / sector", "Fuel shock"),
    _p("Exposures", "Government subsidy share of fuel costs (Case C)", f"{DEFAULT_EXPOSURES['fuel_subsidy_share']:.0%} (off)", "user",
       "Set by the user; the absorbed amount is reported as a direct fiscal cost", "Fuel shock"),
    _p("Exposures", "Revenue volatility fallback", ", ".join(f"{k} {v:.0%}" for k, v in SECTOR_REVENUE_VOLATILITY.items()), "placeholder",
       "Used only when an SOE has fewer than three years of revenue", "Revenue shock"),
    _p("Monte Carlo", "Fuel / FX standard deviations", f"{MC_DEFAULT_FUEL_STD:.0%} / {MC_DEFAULT_FX_STD:.0%}", "placeholder",
       "Calibrate from historical annual changes for the country", "Monte Carlo"),
    _p("Monte Carlo", "Interest-rate / revenue standard deviations", f"{MC_DEFAULT_RATE_STD_BPS:.0f} bps / {MC_DEFAULT_REVENUE_STD_SD:g} s.d. (off)", "user",
       "Off by default; set to draw these shocks too", "Monte Carlo"),
    _p("Monte Carlo", "Shock correlations", ", ".join(f"{k.replace('|', '–')} {v:g}" for k, v in MC_DEFAULT_CORRELATIONS.items() if v), "placeholder",
       "Fuel–FX 0.30 reflects co-movement for fuel importers; estimate the matrix from country data", "Monte Carlo"),
    _p("Fiscal context", "Nominal GDP growth", f"{DEFAULT_GDP_GROWTH:.0%}", "user", "Set by the user", "EFC / GDP paths"),
    _p("Government support", "Role and Link scores, tier mapping, uplift table", "4 + 4 levels → 7 tiers", "proxy",
       "Simplified stand-in for S&P Global Ratings, Rating GREs: Methodology and Assumptions (25 March 2015); S&P matrix not transcribed", "Government Support"),
    _p("Government support", "Dynamic cap trigger", f"rating down {DYNAMIC_CAP_TRIGGER_NOTCHES}+ notches or Negative outlook → {DYNAMIC_CAP_TIER}", "proxy",
       "After S&P GRE criteria (para. 47) — paragraph to verify", "Government Support"),
    _p("Early warning", "Trigger rules and actions", f"{len(TRIGGER_RULES)} rules", "placeholder",
       "Illustrative rules and pre-agreed actions for discussion with the Ministry of Finance", "Early Warning, Report"),
    _p("Early warning", "EFC / GDP bands", f"watch {REPORT_EFC_GDP_WATCH:.1%}, alert {REPORT_EFC_GDP_ALERT:.1%}", "placeholder",
       "Illustrative; relate to the fiscal risk statement's materiality threshold", "Home, Report"),
    _p("Narrative", "Single-driver share / strong-component thresholds", f"{SINGLE_DRIVER_SHARE_THRESHOLD:.0%} / X1 {ZEM_COMPONENT_STRONG_THRESHOLD['X1']}, X2 {ZEM_COMPONENT_STRONG_THRESHOLD['X2']}, X3 {ZEM_COMPONENT_STRONG_THRESHOLD['X3']}, X4 {ZEM_COMPONENT_STRONG_THRESHOLD['X4']}", "placeholder",
       "Wording thresholds for the automated summaries only", "Altman Z-EM text"),
]
