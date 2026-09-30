"""
Standard data schema for the SOE Fiscal Risk Toolkit.

This is the contract between the internal PDF → Excel extraction pipeline and
the dashboard upload: one row per SOE per fiscal year, every variable with a
canonical snake_case key, the internal column name the calculation modules
use, the statement it comes from, and the label variants seen in real
financial statements (so "Operating Costs", "OPEX" or a typo such as
"Operating Expnese" all land in operating_expense).

    VARIABLES          the dictionary (one dict per variable)
    standardize_columns(df)  renames uploaded columns to the internal names
                             and reports how each one was matched
    template_frame()   empty frame with the canonical headers, for the Excel
                       template

Matching, in order: exact canonical key or internal name → listed synonym →
close spelling (difflib ratio ≥ FUZZY_CUTOFF). Exact and synonym matches are
HIGH / MEDIUM confidence; spelling matches are LOW and should be reviewed.
The same dictionary is embedded in the HTML version, which applies the same
rules in the browser.

Extending the schema: add a dict to VARIABLES. Columns the calculation
modules read are marked required=True; everything else is carried through
and used where a module can (exposure shares, guaranteed debt, provenance).
"""

from __future__ import annotations

import difflib
import re

import pandas as pd

FUZZY_CUTOFF = 0.88

# statement groups, in the order they appear in the template
STATEMENTS = ["Identifier", "Balance sheet", "Income statement", "Cash flow", "Government relationship", "Shock exposure", "Provenance"]


def _v(key, column, label, statement, kind="amount", required=False, used_by="", synonyms=()):
    return {"key": key, "column": column, "label": label, "statement": statement, "kind": kind,
            "required": required, "used_by": used_by, "synonyms": list(synonyms)}


VARIABLES = [
    # --- identifiers -------------------------------------------------------
    _v("country", "Country", "Country", "Identifier", "text", False, "Grouping, repository",
       ["country name", "economy", "country code", "iso3"]),
    _v("soe_name", "Entity", "SOE name", "Identifier", "text", True, "Every page",
       ["entity", "soe", "company", "enterprise", "name", "soe name", "entity name", "company name"]),
    _v("sector", "Sector", "Sector", "Identifier", "text", True, "Sector filters, fuel share / LGD / volatility defaults",
       ["industry", "gics sector", "sector name", "activity"]),
    _v("fiscal_year", "Year", "Fiscal year", "Identifier", "year", True, "Every page",
       ["year", "fy", "financial year", "reporting year", "period"]),
    _v("currency", "Currency", "Currency", "Identifier", "text", True, "Labels",
       ["ccy", "reporting currency", "currency code"]),
    _v("unit", "Units", "Unit", "Identifier", "text", True, "Labels, unit scaling",
       ["units", "scale", "unit of measure", "denomination"]),
    # --- balance sheet -----------------------------------------------------
    _v("total_assets", "Total Assets", "Total assets", "Balance sheet", required=True, used_by="Z-EM X1–X3, KPIs",
       synonyms=["assets", "total asset", "assets total", "sum of assets"]),
    _v("current_assets", "Current Assets", "Current assets", "Balance sheet", required=True, used_by="Z-EM X1, liquidity KPIs",
       synonyms=["total current assets", "current asset"]),
    _v("cash", "Cash and Equivalents", "Cash and equivalents", "Balance sheet", used_by="Carried (liquidity context)",
       synonyms=["cash", "cash and cash equivalents", "cash & cash equivalents", "cash and bank balances", "cash at bank"]),
    _v("receivables", "Receivables", "Receivables", "Balance sheet", used_by="Carried (arrears context)",
       synonyms=["trade receivables", "accounts receivable", "trade and other receivables", "debtors"]),
    _v("inventory", "Inventory", "Inventory", "Balance sheet", used_by="Carried",
       synonyms=["inventories", "stocks", "stock"]),
    _v("total_liabilities", "Total Liabilities", "Total liabilities", "Balance sheet", required=True, used_by="Z-EM X4, leverage KPIs, EAD",
       synonyms=["liabilities", "total liability", "liabilities total"]),
    _v("current_liabilities", "Current Liabilities", "Current liabilities", "Balance sheet", required=True, used_by="Z-EM X1, liquidity KPIs",
       synonyms=["total current liabilities", "current liability"]),
    _v("short_term_debt", "Short Term Debt", "Short-term debt", "Balance sheet", used_by="Near-term maturity share (refinancing shock)",
       synonyms=["short-term borrowings", "short term borrowings", "current borrowings", "short term loans", "current portion of borrowings"]),
    _v("long_term_debt", "Long Term Debt", "Long-term debt", "Balance sheet", used_by="Carried",
       synonyms=["long-term borrowings", "long term borrowings", "non-current borrowings", "long term loans"]),
    _v("fx_debt", "FX Debt", "Foreign-currency debt", "Balance sheet", used_by="FX debt share (FX revaluation shock)",
       synonyms=["foreign currency debt", "fx denominated debt", "foreign currency borrowings", "external debt"]),
    _v("government_guaranteed_debt", "Government Guaranteed Debt", "Government-guaranteed debt", "Balance sheet", used_by="EAD (observed basis)",
       synonyms=["guaranteed debt", "sovereign guaranteed debt", "government guaranteed borrowings", "state guaranteed debt"]),
    _v("total_equity", "Equity", "Total equity", "Balance sheet", required=True, used_by="Z-EM X4, ROE, leverage",
       synonyms=["equity", "total equity", "shareholders equity", "shareholders funds", "net worth", "book equity", "net assets"]),
    _v("retained_earnings", "Retained Earnings", "Retained earnings", "Balance sheet", required=True, used_by="Z-EM X2",
       synonyms=["retained profit", "accumulated profit", "accumulated losses", "accumulated deficit", "retained earnings deficit"]),
    # --- income statement ----------------------------------------------------
    _v("revenue", "Revenues", "Revenue", "Income statement", required=True, used_by="Margins, revenue shock",
       synonyms=["revenues", "total revenue", "turnover", "sales", "total income", "total revenues"]),
    _v("operating_revenue", "Operating Revenue", "Operating revenue", "Income statement", used_by="Carried",
       synonyms=["revenue from operations", "operating income revenue", "operating revenues"]),
    _v("operating_expense", "Operating Expense", "Operating expense", "Income statement", required=True, used_by="Fuel and FX shocks",
       synonyms=["operating expenses", "operating costs", "operating cost", "operating expenditure", "opex"]),
    _v("total_expense", "Total Expense", "Total expense", "Income statement", required=True, used_by="Grants / total expense",
       synonyms=["total expenses", "total expenditure", "total costs", "total cost"]),
    _v("fuel_cost", "Fuel Cost", "Fuel / energy cost", "Income statement", used_by="Fuel cost share (fuel shock)",
       synonyms=["fuel", "fuel costs", "fuel and energy cost", "energy cost", "fuel expense", "cost of fuel"]),
    _v("labor_cost", "Labor Cost", "Labour cost", "Income statement", used_by="Carried",
       synonyms=["labour cost", "staff costs", "personnel expenses", "wages and salaries", "employee costs", "employee benefits expense"]),
    _v("ebit", "Operating Profits (EBIT)", "EBIT (operating profit)", "Income statement", required=True, used_by="Z-EM X3, margins, coverage",
       synonyms=["ebit", "operating profit", "operating profits", "operating income", "profit from operations", "operating result"]),
    _v("ebitda", "EBITDA", "EBITDA", "Income statement", required=True, used_by="Debt / EBITDA, margins",
       synonyms=["ebitda"]),
    _v("depreciation", "Depreciation", "Depreciation and amortisation", "Income statement", required=True, used_by="Depreciation / EBITDA",
       synonyms=["depreciation and amortisation", "depreciation and amortization", "d&a", "depreciation amortisation"]),
    _v("interest_expense", "Interest Expense", "Interest expense", "Income statement", required=True, used_by="Coverage, rate and refinancing shocks",
       synonyms=["finance costs", "finance cost", "interest paid", "interest costs", "interest"]),
    _v("tax_expense", "Tax Expense", "Tax expense", "Income statement", required=True, used_by="Effective tax rate",
       synonyms=["income tax", "income tax expense", "tax", "taxation"]),
    _v("net_income", "Net Income", "Net income", "Income statement", required=True, used_by="ROA, ROE, shock law of motion",
       synonyms=["net profit", "profit for the year", "net profit after tax", "profit after tax", "net result", "profit loss for the year"]),
    # --- cash flow -------------------------------------------------------------
    _v("operating_cash_flow", "Operating Cash Flow", "Operating cash flow", "Cash flow", used_by="Carried",
       synonyms=["cash from operations", "net cash from operating activities", "cash generated from operations"]),
    _v("capex", "Capex", "Capital expenditure", "Cash flow", used_by="Carried",
       synonyms=["capital expenditure", "purchase of property plant and equipment", "investment in fixed assets"]),
    _v("debt_service", "Debt Service", "Debt service", "Cash flow", used_by="Carried",
       synonyms=["debt service payments", "principal and interest paid", "repayment of borrowings"]),
    # --- government relationship ---------------------------------------------
    _v("government_grants", "Government Grants", "Government grants", "Government relationship", required=True, used_by="Fiscal-dependency KPIs",
       synonyms=["grants", "government transfers", "transfers from government", "grants received", "government grant"]),
    _v("government_subsidies", "Government Subsidies", "Government subsidies", "Government relationship", used_by="Carried",
       synonyms=["subsidies", "operating subsidies", "subsidy income"]),
    _v("capital_injection", "Capital Injection", "Capital injection", "Government relationship", used_by="Carried",
       synonyms=["equity injection", "capital contribution", "recapitalisation"]),
    _v("on_lending", "On-lending", "Government on-lending", "Government relationship", used_by="Carried",
       synonyms=["on lending", "onlending", "government loans", "loans from government"]),
    _v("government_arrears_owed", "Government Arrears Owed", "Government arrears owed to the SOE", "Government relationship", used_by="Carried (arrears context)",
       synonyms=["government arrears", "arrears owed by government", "receivables from government"]),
    # --- shock exposure shares (0–1) -------------------------------------------
    _v("fuel_cost_share", "Fuel Cost Share", "Fuel cost share of operating expense", "Shock exposure", "share", used_by="Fuel shock (bottom-up)",
       synonyms=["fuel share", "fuel share of opex"]),
    _v("fx_cost_share", "FX Cost Share", "FX share of operating costs", "Shock exposure", "share", used_by="FX shock, operations (bottom-up)",
       synonyms=["fx share of costs", "foreign currency cost share"]),
    _v("fx_revenue_share", "FX Revenue Share", "FX share of revenue", "Shock exposure", "share", used_by="FX shock, operations (bottom-up)",
       synonyms=["fx share of revenue", "foreign currency revenue share"]),
    _v("fx_debt_share", "FX Debt Share", "FX share of liabilities", "Shock exposure", "share", used_by="FX shock, balance sheet (bottom-up)",
       synonyms=["fx share of debt", "foreign currency debt share"]),
    _v("floating_rate_debt_share", "Floating Rate Debt Share", "Floating-rate share of liabilities", "Shock exposure", "share", used_by="Interest-rate shock (bottom-up)",
       synonyms=["floating share", "variable rate debt share", "floating rate share"]),
    # --- provenance (audit trail from the extraction pipeline) ----------------
    _v("source_file", "Source File", "Source file", "Provenance", "text", used_by="Audit trail",
       synonyms=["file", "source", "pdf", "document"]),
    _v("source_page", "Source Page", "Source page(s)", "Provenance", "text", used_by="Audit trail",
       synonyms=["page", "pages", "page number"]),
    _v("audit_status", "Audit Status", "Audit status (audited / unaudited / draft)", "Provenance", "text", used_by="Audit trail",
       synonyms=["audited", "audit", "fs status"]),
    _v("extraction_method", "Extraction Method", "Extraction method (manual / machine / semantic)", "Provenance", "text", used_by="Audit trail",
       synonyms=["method", "extraction"]),
    _v("data_quality_flag", "Data Quality Flag", "Data quality (Observed / Proxy / User assumption)", "Provenance", "text", used_by="Data-quality panel",
       synonyms=["quality", "quality flag", "data quality", "dq flag", "confidence"]),
]

BY_COLUMN = {v["column"]: v for v in VARIABLES}
BY_KEY = {v["key"]: v for v in VARIABLES}
REQUIRED_COLUMNS = [v["column"] for v in VARIABLES if v["required"]]
NUMERIC_KINDS = {"amount", "share", "year"}
PROVENANCE_COLUMNS = [v["column"] for v in VARIABLES if v["statement"] == "Provenance"]


def normalize(label: str) -> str:
    """Lower-case, '&' → 'and', drop punctuation and brackets' contents kept as words."""
    s = str(label).strip().lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _lookup():
    table = {}
    for v in VARIABLES:
        for name, how in [(v["key"], "exact"), (v["column"], "exact")] + [(s, "synonym") for s in v["synonyms"]]:
            n = normalize(name)
            if n and n not in table:
                table[n] = (v["column"], how)
    return table


LOOKUP = _lookup()


def match_column(label: str):
    """Returns (internal_column, method, score) or (None, 'unmatched', 0)."""
    n = normalize(label)
    if n in LOOKUP:
        col, how = LOOKUP[n]
        return col, how, 1.0
    best = difflib.get_close_matches(n, list(LOOKUP), n=1, cutoff=FUZZY_CUTOFF)
    if best:
        return LOOKUP[best[0]][0], "spelling", round(difflib.SequenceMatcher(None, n, best[0]).ratio(), 3)
    return None, "unmatched", 0.0


CONFIDENCE = {"exact": "HIGH", "synonym": "MEDIUM", "spelling": "LOW", "unmatched": "—", "duplicate": "—"}


def standardize_columns(df: pd.DataFrame):
    """Rename uploaded columns to the internal names. Returns (frame, report)
    where report is a DataFrame: uploaded column, mapped to, schema key,
    method, confidence. Exact matches claim their target first, then
    synonyms, then spelling matches; a column whose target is already taken
    keeps its name and is reported as a duplicate."""
    matches = {col: match_column(col) for col in df.columns}
    priority = {"exact": 0, "synonym": 1, "spelling": 2, "unmatched": 3}
    taken, final = set(), {}
    for col in sorted(df.columns, key=lambda c: priority[matches[c][1]]):
        target, how, score = matches[col]
        if target is None:
            final[col] = (None, "unmatched", 0.0)
        elif target in taken:
            final[col] = (None, "duplicate", 0.0)
        else:
            taken.add(target)
            final[col] = (target, how, score)
    rename, rows = {}, []
    for col in df.columns:
        target, how, score = final[col]
        if target and target != col:
            rename[col] = target
        rows.append({
            "Uploaded column": col, "Mapped to": target or "", "Schema key": BY_COLUMN[target]["key"] if target else "",
            "Method": f"spelling ({score:.2f})" if how == "spelling" else how, "Confidence": CONFIDENCE[how],
        })
    return df.rename(columns=rename), pd.DataFrame(rows)


def template_frame() -> pd.DataFrame:
    """Empty frame with the canonical snake_case headers (the extraction
    pipeline's output format), in statement order."""
    order = sorted(VARIABLES, key=lambda v: STATEMENTS.index(v["statement"]))
    return pd.DataFrame(columns=[v["key"] for v in order])


def dictionary_frame() -> pd.DataFrame:
    """The variable dictionary as a table (for the template's second sheet)."""
    order = sorted(VARIABLES, key=lambda v: STATEMENTS.index(v["statement"]))
    return pd.DataFrame([{
        "key": v["key"], "label": v["label"], "statement": v["statement"], "kind": v["kind"],
        "required": "yes" if v["required"] else "", "used by": v["used_by"],
        "tool column": v["column"], "also recognised as": "; ".join(v["synonyms"]),
    } for v in order])


def payload() -> dict:
    """What the HTML version needs to apply the same matching in the browser."""
    return {"variables": VARIABLES, "fuzzy_cutoff": FUZZY_CUTOFF, "statements": STATEMENTS}
