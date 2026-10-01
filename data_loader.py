"""
Data ingestion layer. Accepts an uploaded Excel/CSV file in the long-format
schema (one row per SOE per year), validates required columns, and coerces
numeric fields. Missing optional (shock-module) columns are reported but do
not block ingestion.
"""

import csv
import io
import re

import numpy as np
import pandas as pd

import config
import schema

NUMERIC_COLUMNS = [
    "Year", "Revenues", "Total Expense", "Operating Expense",
    "Operating Profits (EBIT)", "Net Income", "Current Assets", "Total Assets",
    "Current Liabilities", "Total Liabilities", "Equity", "Retained Earnings",
    "Interest Expense", "Tax Expense", "EBITDA", "Government Grants",
    "Depreciation",
]
# Optional numeric columns from the standard schema (exposure shares, debt
# split, cash flow, government relationship) — coerced the same way.
OPTIONAL_NUMERIC_COLUMNS = [v["column"] for v in schema.VARIABLES
                            if v["kind"] in schema.NUMERIC_KINDS and v["column"] not in NUMERIC_COLUMNS]


_NA_TOKENS = {"", "-", "--", "\u2014", "\u2013", "n/a", "na", "nan", "none", "null", "...", "\u2026"}
_PLAIN_NUMBER = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
_THOUSANDS = re.compile(r"^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$")
_DECIMAL_COMMA = re.compile(r"^[+-]?\d+,\d+$")
_YEAR = re.compile(r"(19|20)\d{2}")


def parse_number(v) -> float:
    """One cell to a float, reading numbers the way spreadsheets display
    them: 1,234,567 (thousands commas), (1,234) (negative), 35% (0.35),
    1234,5 (decimal comma), 1 234 or 1'234 (spaced thousands), the Unicode
    minus sign. Blanks and markers such as -, n/a or ... become NaN, as does
    anything else that is not a number. templates/engine.js parseNumber is
    the same rule (checked by tests/check_engine_parity.py)."""
    if v is None or isinstance(v, bool):
        return float("nan")
    if isinstance(v, (int, float, np.integer, np.floating)):
        return float(v)
    t = str(v).strip().replace("\u2212", "-")
    for ch in ("\u00a0", "\u202f", " ", "'"):
        t = t.replace(ch, "")
    if t.lower() in _NA_TOKENS:
        return float("nan")
    neg = t.startswith("(") and t.endswith(")")
    if neg:
        t = t[1:-1]
    pct = t.endswith("%")
    if pct:
        t = t[:-1]
    if _THOUSANDS.match(t):
        t = t.replace(",", "")
    elif _DECIMAL_COMMA.match(t):
        t = t.replace(",", ".")
    if not _PLAIN_NUMBER.match(t):
        return float("nan")
    x = float(t)
    if pct:
        x /= 100
    return -x if neg else x


def parse_year(v) -> float:
    """A year cell to a number: 2023, 2023.0, "2023", "FY2023" and
    "2023/24" all give 2023 (the first four-digit year in the text)."""
    x = parse_number(v)
    if x == x and abs(x) != float("inf"):
        return float(int(x))
    m = _YEAR.search(str(v)) if v is not None else None
    return float(m.group(0)) if m else float("nan")


def _count_outside_quotes(line: str, d: str) -> int:
    n, q = 0, False
    for ch in line:
        if ch == '"':
            q = not q
        elif ch == d and not q:
            n += 1
    return n


def detect_delimiter(text: str) -> str:
    """Comma, semicolon, tab or pipe: the one with the highest median count
    per line over the first 20 non-empty lines (ties go to the comma)."""
    lines = [ln for ln in text.splitlines() if ln.strip()][:20]
    best, best_score = ",", 0.0
    for d in [",", ";", "\t", "|"]:
        if not lines:
            break
        counts = sorted(_count_outside_quotes(ln, d) for ln in lines)
        score = counts[len(counts) // 2]
        if score > best_score:
            best, best_score = d, score
    return best


def frame_from_rows(rows) -> pd.DataFrame:
    """Rows read without headers (lists of cells) to a DataFrame, taking the
    header from the row schema.find_header_row picks; empty rows dropped."""
    rows = [list(r) for r in rows]
    if not rows:
        return pd.DataFrame()
    h = schema.find_header_row(rows)
    width = max(len(r) for r in rows)
    head = []
    for i in range(width):
        c = rows[h][i] if i < len(rows[h]) else None
        c = "" if c is None or (isinstance(c, float) and c != c) else str(c).strip()
        head.append(c or f"Unnamed: {i}")
    body = [r + [None] * (width - len(r)) for r in rows[h + 1:]]
    body = [r for r in body if any(not (c is None or (isinstance(c, float) and c != c) or (isinstance(c, str) and not c.strip())) for c in r)]
    return pd.DataFrame(body, columns=head)


def load_uploaded_file(uploaded_file) -> pd.DataFrame:
    """Read an uploaded file object (xlsx or csv), or a path, into a DataFrame. CSV: the
    delimiter is detected (comma, semicolon, tab, pipe) and UTF-8 or Windows
    encodings are accepted. Excel: the "Data" sheet of the standard template
    if present, else the first sheet. Title or note rows above the header are
    skipped (schema.find_header_row)."""
    if isinstance(uploaded_file, (str, bytes)) or hasattr(uploaded_file, "__fspath__"):  # a path on disk
        with open(uploaded_file, "rb") as fh:
            data = io.BytesIO(fh.read())
        data.name = str(uploaded_file)
        uploaded_file = data
    name = uploaded_file.name.lower()
    if name.endswith(".csv") or name.endswith(".txt"):
        raw = uploaded_file.read()
        if isinstance(raw, str):
            text = raw
        else:
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw.decode("cp1252", errors="replace")
        rows = list(csv.reader(io.StringIO(text), delimiter=detect_delimiter(text)))
    else:
        xls = pd.ExcelFile(uploaded_file)
        sheet = "Data" if "Data" in xls.sheet_names else xls.sheet_names[0]
        rows = pd.read_excel(xls, sheet_name=sheet, header=None).values.tolist()
    return frame_from_rows(rows)


def load_and_standardize(uploaded_file):
    """Read an upload and map its column names onto the standard schema
    (schema.standardize_columns). Returns (df, mapping_report)."""
    return schema.standardize_columns(load_uploaded_file(uploaded_file))


def data_quality_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Rows per value of the Data Quality Flag / Audit Status / Extraction
    Method columns, when the upload carries them (audit trail from the
    extraction pipeline). Empty frame if none are present."""
    out = []
    for col in ["Data Quality Flag", "Audit Status", "Extraction Method"]:
        if col in df.columns:
            counts = df[col].fillna("(blank)").astype(str).value_counts()
            out += [{"Field": col, "Value": k, "Rows": int(v)} for k, v in counts.items()]
    return pd.DataFrame(out)


def validate_schema(df: pd.DataFrame) -> dict:
    """Check df against config.REQUIRED_COLUMNS and OPTIONAL_SHOCK_COLUMNS.
    Returns a dict: {'missing_required': [...], 'missing_optional': [...],
    'ok': bool}."""
    present = set(df.columns)

    # 'Sector' is required for cross-SOE sector comparisons but may be
    # absent in an initial upload — treat it as required-but-fixable.
    missing_required = [c for c in config.REQUIRED_COLUMNS if c not in present]
    missing_optional = [c for c in config.OPTIONAL_SHOCK_COLUMNS if c not in present]

    return {
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "ok": len(missing_required) == 0,
    }


def coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Force numeric columns to numeric dtype, coercing errors to NaN so a
    single bad cell doesn't break the whole pipeline. Reports offending
    rows separately via `numeric_issues`."""
    out = df.copy()
    for col in NUMERIC_COLUMNS + OPTIONAL_NUMERIC_COLUMNS:
        if col in out.columns:
            if col == "Year":
                out[col] = out[col].map(parse_year).astype(float)
            elif pd.api.types.is_numeric_dtype(out[col]):
                out[col] = pd.to_numeric(out[col], errors="coerce")
            else:  # text cells: read spreadsheet-formatted numbers (parse_number)
                out[col] = out[col].map(parse_number).astype(float)
    return out


def numeric_issues(df: pd.DataFrame) -> pd.DataFrame:
    """Return rows where a required numeric column failed to coerce
    (i.e. is NaN in the coerced frame but was not NaN/blank originally
    would require the pre-coercion frame; here we just flag any NaN in
    a required numeric column post-coercion for the user to review)."""
    required_numeric = [c for c in NUMERIC_COLUMNS if c in config.REQUIRED_COLUMNS]
    mask = df[required_numeric].isna().any(axis=1)
    return df.loc[mask, ["Entity", "Year"] + required_numeric] if "Entity" in df.columns else df.loc[mask]


# ---------------------------------------------------------------------------
# Sample dataset (SOE A - Energy, SOE B - Transport) for demo/testing
# ---------------------------------------------------------------------------
def sample_dataset() -> pd.DataFrame:
    csv_text = """Entity,Year,Sector,Revenues,Total Expense,Operating Expense,Operating Profits (EBIT),Net Income,Current Assets,Total Assets,Current Liabilities,Total Liabilities,Equity,Retained Earnings,Interest Expense,Tax Expense,EBITDA,Net Profit After Tax,Government Grants,Depreciation,Currency,Units
SOE A,2020,Energy,30271510431,53261812296,51429979206,-21364584285,-22990301865,31648484897,50564692838,50455671036,64327611746,-13762918908,-8469714137,610868478,302715104,-17842468772,-22990301865,15517321949,6173944775,FCFA,Absolute
SOE A,2021,Energy,34557778288,35886836510,35383283013,-825504725,-1329058222,40810007803,62442063419,63145445773,74822227996,-12380164577,-31460016002,290098143,305653942,2182341518,-1329058222,18229134502,3007846243,FCFA,Absolute
SOE A,2022,Energy,34693268082,39854246066,39142772316,-4449504234,-5160977984,40967799947,70293954181,72470060858,88609037352,-18315083171,-32789074224,123264449,346932680,242479036,-5160977984,1505559000,4691984270,FCFA,Absolute
SOE A,2023,Energy,38235261289,31844487779,32418714872,6399879771,6813438922,45129531424,83684082230,92937887980,111759665933,-28075583703,-37953021814,479444638,382665412,11102470602,6813438922,14511101888,4702590831,FCFA,Absolute
SOE A,2024,Energy,38423772477,46534568933,48269970712,-7092104070,-8057641089,47374294289,90303140285,109262403808,129137545242,-38834404957,-44766460736,587161828,384237725,-2496980951,-8057641089,11809921723,4595123119,FCFA,Absolute
SOE B,2020,Transport,4107284286,6795173873,6053698168,-3054238134,-1678623608,34299848286,165798922850,5025485902,144569370510,21229542844,-2509855635,741475705,41072843,396194336,-1678623608,16958124859,3450432470,FCFA,Absolute
SOE B,2021,Transport,5304148268,11111429504,8231264230,-2927115962,-1765501072,38696504564,175363451931,5791781654,158003236483,17360215448,-4188479243,827315468,53041483,3189216918,-1765501072,14854298535,6116332880,FCFA,Absolute
SOE B,2022,Transport,5674095665,8320013000,7254070000,-1579974257,-1533261234,43874758647,178578576195,6394854275,163178640327,15399935868,-5953980315,1009193455,56740957,3678092806,-1533261234,14427280189,5258067063,FCFA,Absolute
SOE B,2023,Transport,6134488908,8169292820,7732659414,-1598170506,-2034803912,48170728769,190991805260,7576528787,167373741454,23618063806,-7487241549,1567059813,61344889,3884462312,-2034803912,24680212039,6677479120,FCFA,Absolute
SOE B,2024,Transport,6279189030,10131040111,6703248655,-394835232,-1781721271,53533758953,191813708958,9116087247,170731784701,21081924257,-9522045461,2124729222,62791890,4325681000,-1781721271,23925793761,4720516232,FCFA,Absolute
"""
    return pd.read_csv(io.StringIO(csv_text))


# ---------------------------------------------------------------------------
# Illustrative demo portfolio (8 SOEs, 7 sectors) — SOE A and SOE B from the
# sample above plus six synthetic SOEs (C–H) built to span all three Z-EM
# zones. Invented figures for demonstrating the report, not real entities.
# ---------------------------------------------------------------------------
_DEMO_EXTRA_ROWS = """SOE C,2020,Power / Utilities,62000000000,60451250000,53320000000,8680000000,1548750000,46200000000,210000000000,26460000000,147000000000,63000000000,12600000000,6615000000,516250000,16030000000,1548750000,11160000000,7350000000,FCFA,Absolute
SOE C,2021,Power / Utilities,63860000000,63552800000,56835400000,7024600000,307200000,45708012000,217657200000,30870000000,154350000000,63307200000,12907200000,6615000000,102400000,14642602000,307200000,14049200000,7618002000,FCFA,Absolute
SOE C,2022,Power / Utilities,66414400000,68711142000,61101248000,5313152000,-2296742000,45508600640,227543003200,36637159944,166532545200,61010458000,10610458000,6945750000,664144000,13277157112,-2296742000,17931888000,7964005112,FCFA,Absolute
SOE C,2023,Power / Utilities,67742688000,72526945014,64355553600,3387134400,-4784257014,45400861762,238951904010,43854168726,182725703024,56226200986,5826200986,7493964534,677426880,11750451040,-4784257014,21000233280,8363316640,FCFA,Absolute
SOE C,2024,Power / Utilities,69774968640,76602125903,67681719581,2093249059,-6827157263,45479943788,252666354377,52849500770,203267310655,49399043723,-1000956277,8222656636,697749686,10936571462,-6827157263,23723489338,8843322403,FCFA,Absolute
SOE D,2020,Telecoms,48000000000,41997000000,38400000000,9600000000,6003000000,28500000000,95000000000,11970000000,39900000000,55100000000,23750000000,1596000000,2001000000,15300000000,6003000000,0,5700000000,FCFA,Absolute
SOE D,2021,Telecoms,50880000000,44063400000,40195200000,10684800000,6816600000,31810526000,102614600000,12209400000,40698000000,61916600000,30566600000,1596000000,2272200000,16841676000,6816600000,0,6156876000,FCFA,Absolute
SOE D,2022,Telecoms,53424000000,46230660000,42204960000,11219040000,7193340000,34166625200,110214920000,12742543800,41104980000,69109940000,37759940000,1627920000,2397780000,17831935200,7193340000,0,6612895200,FCFA,Absolute
SOE D,2023,Telecoms,55560960000,48459965400,44448768000,11112192000,7100994600,35441404260,118138014200,13416665472,41927079600,76210934600,44860934600,1644199200,2366998200,18200472852,7100994600,0,7088280852,FCFA,Absolute
SOE D,2024,Telecoms,57783398400,50807076516,46804552704,10978845696,6976321884,37785863303,125952877676,14112654993,42765621192,83187256484,51837256484,1677083184,2325440628,18536018357,6976321884,0,7557172661,FCFA,Absolute
SOE E,2020,Agriculture,21000000000,20681250000,19530000000,1470000000,318750000,12920000000,38000000000,9405000000,20900000000,17100000000,1520000000,1045000000,106250000,2990000000,318750000,1680000000,1520000000,FCFA,Absolute
SOE E,2021,Agriculture,23940000000,22748700000,21306600000,2633400000,1191300000,14334588000,39818300000,9471880000,21527000000,18291300000,2711300000,1045000000,397100000,4226132000,1191300000,1675800000,1592732000,FCFA,Absolute
SOE E,2022,Agriculture,21067200000,21511534000,20224512000,842688000,-444334000,13223465112,40071106400,10445345988,22224140400,17846966000,2266966000,1076350000,210672000,2445532256,-444334000,2528064000,1602844256,FCFA,Absolute
SOE E,2023,Agriculture,24859296000,24014698785,22621959360,2237336640,844597215,14631634231,41804669231,10632028767,23113106016,18691563215,3111563215,1111207020,281532405,3909523409,844597215,2237336640,1672186769,FCFA,Absolute
SOE E,2024,Agriculture,22870552320,22708118941,21498319181,1372233139,162433379,14504568569,42660495790,11189054622,23806499196,18853996594,3273996594,1155655301,54144460,3078652971,162433379,2515760755,1706419832,FCFA,Absolute
SOE F,2020,Industry,33000000000,30232500000,28050000000,4950000000,2767500000,18480000000,56000000000,9576000000,25200000000,30800000000,10080000000,1260000000,922500000,7750000000,2767500000,660000000,2800000000,FCFA,Absolute
SOE F,2021,Industry,33660000000,31323150000,29284200000,4375800000,2336850000,18909712000,59092850000,10382400000,25956000000,33136850000,12416850000,1260000000,778950000,7330442500,2336850000,673200000,2954642500,FCFA,Absolute
SOE F,2022,Industry,33323400000,31547569500,29657826000,3665574000,1775830500,19191145355,61906920500,11337580800,26994240000,34912680500,14192680500,1297800000,591943500,6760920025,1775830500,999702000,3095346025,FCFA,Absolute
SOE F,2023,Industry,32323698000,31154132385,29414565180,2909132820,1169565615,19327859434,64426198115,12471338880,28343952000,36082246115,15362246115,1349712000,389855205,6130442726,1169565615,1292947920,3221309906,FCFA,Absolute
SOE F,2024,Industry,31677224040,31077067978,29459818357,2217405683,600156062,19268630015,66443551777,13690128816,29761149600,36682402177,15962402177,1417197600,200052021,5539583272,600156062,1583861202,3322177589,FCFA,Absolute
SOE G,2020,Transport,27000000000,31770000000,28620000000,-1620000000,-4770000000,12000000000,60000000000,12000000000,48000000000,12000000000,-1200000000,2880000000,270000000,1380000000,-4770000000,8100000000,3000000000,FCFA,Absolute
SOE G,2021,Transport,33750000000,37642500000,34425000000,-675000000,-3892500000,11651370000,61323000000,14368185000,53215500000,8107500000,-5092500000,2880000000,337500000,2391150000,-3892500000,8775000000,3066150000,FCFA,Absolute
SOE G,2022,Transport,37800000000,41748930000,38178000000,-378000000,-3948930000,12408544440,68936358000,17045558520,58777788000,10158570000,-9041430000,3192930000,378000000,3068817900,-3948930000,10584000000,3446817900,FCFA,Absolute
SOE G,2023,Transport,38934000000,44018027280,40102020000,-1168020000,-5084027280,12072922682,71017192248,20442221354,65942649528,5074542720,-14125457280,3526667280,389340000,2382839612,-5084027280,12848220000,3550859612,FCFA,Absolute
SOE G,2024,Transport,37376640000,43575797372,39245472000,-1868832000,-6199157372,11810070602,73812941262,24729393451,74937555913,-1124614652,-20324614652,3956558972,373766400,1821815063,-6199157372,13455590400,3690647063,FCFA,Absolute
SOE H,2020,Other,9000000000,7132500000,6300000000,2700000000,1867500000,10080000000,24000000000,3300000000,6000000000,18000000000,9600000000,210000000,622500000,3420000000,1867500000,0,720000000,FCFA,Absolute
SOE H,2021,Other,9360000000,7481700000,6645600000,2714400000,1878300000,11153469000,25938300000,3333000000,6060000000,19878300000,11478300000,210000000,626100000,3492549000,1878300000,0,778149000,FCFA,Absolute
SOE H,2022,Other,9734400000,7703235000,6814080000,2920320000,2031165000,12333228600,28030065000,3427536000,6120600000,21909465000,13509465000,212100000,677055000,3761221950,2031165000,0,840901950,FCFA,Absolute
SOE H,2023,Other,10026432000,8081547030,7219031040,2807400960,1944884970,13242839267,30097361970,3496086720,6243012000,23854349970,15454349970,214221000,648294990,3710321819,1944884970,0,902920859,FCFA,Absolute
SOE H,2024,Other,10327224960,8322386783,7435601971,2891622989,2004838177,14502177174,32227060387,3629687177,6367872240,25859188147,17459188147,218505420,668279392,3858434800,2004838177,0,966811812,FCFA,Absolute
"""


# Illustrative exposure data for the demo SOEs (bottom-up shocks): shares as
# reported, or amounts from which the tool derives a share. SOE A, B and H
# carry none, so the tool falls back to sector / generic defaults for them.
_DEMO_EXPOSURES = {
    "SOE C": {"FX Debt Share": 0.70, "Floating Rate Debt Share": 0.50, "fuel_of_opex": 0.42, "st_debt_of_tl": 0.25, "guaranteed_of_tl": 0.60},
    "SOE D": {"FX Debt Share": 0.10, "Floating Rate Debt Share": 0.20, "FX Cost Share": 0.35, "FX Revenue Share": 0.05, "st_debt_of_tl": 0.15},
    "SOE E": {"FX Debt Share": 0.20, "FX Cost Share": 0.15, "FX Revenue Share": 0.40, "Fuel Cost Share": 0.18},
    "SOE F": {"FX Debt Share": 0.45, "Floating Rate Debt Share": 0.60, "FX Cost Share": 0.30, "FX Revenue Share": 0.25, "st_debt_of_tl": 0.35},
    "SOE G": {"FX Debt Share": 0.80, "Floating Rate Debt Share": 0.50, "FX Cost Share": 0.45, "FX Revenue Share": 0.30, "Fuel Cost Share": 0.35, "guaranteed_of_tl": 0.90},
}


def demo_portfolio() -> pd.DataFrame:
    """Sample dataset (SOE A, SOE B) plus six illustrative SOEs (C–H) with
    consistent, invented financial statements, illustrative exposure data
    for the bottom-up shocks, and provenance columns as the extraction
    pipeline would fill them. Used by the Home page's 'demo portfolio'
    button and by `python report.py --demo`."""
    extra = pd.read_csv(io.StringIO(_DEMO_EXTRA_ROWS), header=None, names=list(sample_dataset().columns))
    df = pd.concat([sample_dataset(), extra], ignore_index=True)
    for col in ["FX Debt Share", "Floating Rate Debt Share", "FX Cost Share", "FX Revenue Share", "Fuel Cost Share",
                "Fuel Cost", "Short Term Debt", "Government Guaranteed Debt"]:
        df[col] = float("nan")
    for ent, e in _DEMO_EXPOSURES.items():
        m = df["Entity"] == ent
        for col in ["FX Debt Share", "Floating Rate Debt Share", "FX Cost Share", "FX Revenue Share", "Fuel Cost Share"]:
            if col in e:
                df.loc[m, col] = e[col]
        if "fuel_of_opex" in e:
            df.loc[m, "Fuel Cost"] = (df.loc[m, "Operating Expense"] * e["fuel_of_opex"]).round()
        if "st_debt_of_tl" in e:
            df.loc[m, "Short Term Debt"] = (df.loc[m, "Total Liabilities"] * e["st_debt_of_tl"]).round()
        if "guaranteed_of_tl" in e:
            df.loc[m, "Government Guaranteed Debt"] = (df.loc[m, "Total Liabilities"] * e["guaranteed_of_tl"]).round()
    df["Source File"] = df["Entity"].str.replace(" ", "_") + "_FS_" + df["Year"].astype(str) + ".pdf"
    df["Audit Status"] = ["Unaudited" if (y == 2024 and e in ("SOE A", "SOE G")) else "Audited" for e, y in zip(df["Entity"], df["Year"])]
    df["Extraction Method"] = ["Manual" if e in ("SOE A", "SOE B") else "Machine" for e in df["Entity"]]
    df["Data Quality Flag"] = ["Proxy" if (e == "SOE E" and y >= 2023) else "Observed" for e, y in zip(df["Entity"], df["Year"])]
    return df


LONG_PANEL_LABEL = "Long-panel test data: 30 invented SOEs, 2005–2024"


def long_panel_demo(n_soes: int = 30, first_year: int = 2005, last_year: int = 2024, seed: int = 7) -> pd.DataFrame:
    """Invented 30-SOE x 20-year panel for checking how the tool reads long
    histories and large portfolios (KPI trends as lines, year ranges, the
    "12 weakest first" lists). Deterministic (fixed seed). Not real data.

    Each SOE follows a simple path: revenue grows with noise; the EBIT margin,
    leverage and current ratio drift (improving, stable or deteriorating);
    retained earnings accumulate net income. About half the SOEs also report
    FX debt, short-term debt and government-guaranteed debt, so the
    bottom-up exposures and the observed-EAD option have something to use."""
    rng = np.random.default_rng(seed)
    sectors = ["Power / Utilities", "Transport", "Energy", "Agriculture", "Telecoms", "Industry", "Other"]
    years = list(range(first_year, last_year + 1))
    n_y = len(years)
    rows = []
    for i in range(n_soes):
        sector = sectors[i % len(sectors)]
        trend = rng.choice([-1, 0, 1], p=[0.35, 0.3, 0.35])          # deteriorating / stable / improving
        rev = float(rng.lognormal(np.log(4e8), 0.8))
        g_mu, g_sd = rng.uniform(0.0, 0.07), rng.uniform(0.03, 0.12)
        m0 = rng.uniform(-0.02, 0.16) + (0.04 if trend > 0 else 0)
        m_drift = trend * rng.uniform(0.002, 0.009)
        turnover = rng.uniform(0.25, 0.8)
        lev0 = rng.uniform(0.35, 0.8)
        lev_drift = -trend * rng.uniform(0.003, 0.015)
        ca_share = rng.uniform(0.12, 0.3)
        cr0, cr_drift = rng.uniform(0.8, 2.2), trend * rng.uniform(0.0, 0.04)
        dep_share, rate = rng.uniform(0.05, 0.12), rng.uniform(0.03, 0.07)
        grant_share = rng.choice([0.0, rng.uniform(0.02, 0.15), rng.uniform(0.2, 0.6)], p=[0.45, 0.4, 0.15])
        reports_debt = rng.random() < 0.5
        fx_share, st_share, gd_share = rng.uniform(0.05, 0.8), rng.uniform(0.05, 0.4), rng.uniform(0.1, 0.7)
        fuel_share = config.SECTOR_FUEL_COST_SHARE.get(sector, 0.15) * rng.uniform(0.6, 1.4)
        re = None
        for t, y in enumerate(years):
            if t:
                rev *= 1 + g_mu + g_sd * rng.standard_normal()
            margin = float(np.clip(m0 + m_drift * t + 0.03 * rng.standard_normal(), -0.45, 0.4))
            ta = rev / turnover * (1 + 0.02 * rng.standard_normal())
            lev = float(np.clip(lev0 + lev_drift * t + 0.03 * rng.standard_normal(), 0.15, 1.35))
            tl = lev * ta
            ebit = margin * rev
            dep = dep_share * rev
            interest = rate * tl
            tax = max(0.0, 0.25 * (ebit - interest))
            ni = ebit - interest - tax
            re = (rng.uniform(-0.05, 0.25) * ta) if re is None else re + ni
            ca = ca_share * ta
            cr = float(np.clip(cr0 + cr_drift * t + 0.1 * rng.standard_normal(), 0.25, 4.0))
            opex = rev - ebit - dep
            row = {
                "Entity": f"SOE {i + 1:02d}", "Year": y, "Sector": sector,
                "Revenues": round(rev), "Total Expense": round(opex + dep + interest), "Operating Expense": round(opex),
                "Operating Profits (EBIT)": round(ebit), "Net Income": round(ni), "Current Assets": round(ca),
                "Total Assets": round(ta), "Current Liabilities": round(ca / cr), "Total Liabilities": round(tl),
                "Equity": round(ta - tl), "Retained Earnings": round(re), "Interest Expense": round(interest),
                "Tax Expense": round(tax), "EBITDA": round(ebit + dep), "Government Grants": round(max(0.0, grant_share * (1 + 0.2 * rng.standard_normal())) * rev),
                "Depreciation": round(dep), "Currency": "LCU", "Units": "Absolute",
            }
            if reports_debt:
                row.update({"FX Debt": round(fx_share * tl), "Short Term Debt": round(st_share * tl),
                            "Government Guaranteed Debt": round(gd_share * tl)})
            if sector in ("Energy", "Power / Utilities", "Transport"):
                row["Fuel Cost"] = round(fuel_share * opex)
            rows.append(row)
    return pd.DataFrame(rows)


def template_excel_bytes() -> bytes:
    """The standard upload template: a "Data" sheet with the canonical
    snake_case headers (what the PDF-extraction pipeline should output), a
    "Dictionary" sheet (labels, statements, synonyms the upload recognises),
    and a short "Readme"."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        schema.template_frame().to_excel(xw, sheet_name="Data", index=False)
        schema.dictionary_frame().to_excel(xw, sheet_name="Dictionary", index=False)
        pd.DataFrame({"Readme": [
            "One row per SOE per fiscal year. Required columns are marked 'yes' on the Dictionary sheet.",
            "Amounts in the reporting currency and the unit given in the 'unit' column (e.g. Absolute, Millions).",
            "Exposure shares (fuel_cost_share, fx_debt_share, ...) are decimals: 0.30 means 30%. Leave blank if unknown — the tool then uses sector or generic defaults and says so.",
            "Provenance columns (source_file ... data_quality_flag) keep the audit trail: data_quality_flag = Observed, Proxy or User assumption.",
            "Column names in other wording are recognised too (see 'also recognised as'); unrecognised columns are carried but not used.",
        ]}).to_excel(xw, sheet_name="Readme", index=False)
        for ws in xw.book.worksheets:
            for cell in ws[1]:
                cell.font = cell.font.copy(bold=True)
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(60, max(12, max(len(str(c.value or "")) for c in col) + 2))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Blank template — headers only, for the Home page download button
# ---------------------------------------------------------------------------
TEMPLATE_CSV = ",".join(config.REQUIRED_COLUMNS) + "\n"
