# SOE Fiscal Risk Tool

Multi-page Python/Streamlit tool for state-owned enterprises: Altman
Z''-EM distress scoring, an expanded KPI diagnostic set, Expected Fiscal
Cost (PD × EAD × LGD), and dynamic shock simulation through each SOE's own
exposures, with a correlated Monte Carlo option. A standard data schema
(variable dictionary, synonym and spelling matching, provenance columns)
sits under the upload, and every parameter is listed with its source and
status. Visual system and page patterns matched to the companion Pacific SOE
fiscal-injection tool.

The tool is the **Country Analysis** module of the SOE fiscal-risk toolkit.
Global Monitoring (cross-country benchmarking), Hidden Subsidies and PSO
Analysis are planned modules; energy-sector tariff and subsidy modelling is
a separate model.

## Structure

```
soe_tool/
├── Home.py                 Main entry point — shows the interactive tool
│                            full-window (same screens as the HTML version)
├── classic.py               Python-rendered multipage version (Plotly pages
│                            below, Excel template, HTML export page)
├── config.py                ALL tunable numbers live here, plus the
│                              parameter register (source + status of each)
├── schema.py                 Standard data schema: 49 variables, synonyms,
│                              column matching, template and dictionary
├── calculations.py          Z-EM, KPI ratios, red/amber/green classify, EFC
│                              (EAD options), bottom-up shock exposures
├── shocks.py                 Shock transmission engine + Monte Carlo
├── narrative.py              Rule-based component-attribution summaries
├── data_loader.py            Upload handling (column matching, "Data" sheet),
│                              schema validation, data-quality summary, Excel
│                              template, sample data, 8-SOE demo portfolio
├── report.py                 Builds the interactive HTML version (one file);
│                              also a command-line tool
├── templates/
│   ├── app.html               HTML skeleton: tabs and placeholders
│   ├── app.css                Styles (same palette as the Streamlit theme)
│   ├── app.js                 Tabs, controls and SVG charts
│   └── engine.js              JavaScript port of the calculation modules
├── tests/
│   ├── check_engine_parity.py JS engine vs Python modules (needs Node.js)
│   └── check_cash_channel.py  Oil-shock cash channel: legacy reproduction,
│                                balance-sheet identity, cash arithmetic
├── .streamlit/config.toml     Widget colors matching the palette
├── assets/
│   └── logo.png              top-nav wordmark (used via st.logo)
├── utils/
│   ├── theme.py               shared CSS, palette, stat cards, header
│   ├── charts.py               chart label wrapping, CSV+PNG download row
│   ├── filters.py               shared Sector filter bar
│   ├── summary.py                rules-based plain-language summaries
│   └── portfolio.py               latest_per_entity helper
├── app_pages/
│   ├── home.py                Toolkit modules, upload with column-mapping
│   │                            report, template, data quality
│   ├── kpi_dashboard.py        Profitability/Liquidity/Solvency/Fiscal —
│   │                            4-column layout, dropdown per column
│   ├── altman_z.py              Component matrix (X1–X4 + Z-EM), scorecard
│   │                             with rating, benchmark, donut
│   ├── efc.py                    Expected Fiscal Cost, PD×EAD×LGD; EAD as a
│   │                               share of liabilities or guaranteed debt
│   ├── shock_scenarios.py         Bottom-up exposures, fuel Cases A/B/C,
│   │                               tariff policy and cash channel (delayed
│   │                               State compensation, short-term funding),
│   │                               single scenario / correlated Monte Carlo,
│   │                               EFC-as-%-of-GDP path
│   ├── strategic_soe.py           Government support (GRE) uplift
│   ├── assumptions.py             Parameter register (source, status)
│   └── report.py                  HTML version page: preview, download
└── requirements.txt
```

## Run it locally

```bash
pip install -r requirements.txt
streamlit run Home.py       # the tool, exactly as the HTML version looks
streamlit run classic.py    # the Python-rendered multipage version
```

`Home.py` builds the interactive page with `report.py` (demo portfolio
loaded) and fills the browser window with it; the calculations run in the
viewer's browser, and files uploaded there are read in the browser, not sent
to the server. On Streamlit Community Cloud, point the app at `Home.py`.

## Interactive HTML version

The **HTML version** page (next to Home in the top nav) exports the whole
tool as one self-contained `.html` file. Every Streamlit page becomes a tab:
Home (overview, toolkit modules, upload with column mapping, data quality),
**Report** (five sections — executive summary, financial performance,
distress and fiscal risk, stress tests by channel, policy implications — with
a print / save-as-PDF button when the file is opened on its own), KPI
Dashboard, Altman Z-EM, Expected Fiscal Cost, Shock Scenarios (sliders,
single scenario, Monte Carlo, all SOEs), Government Support, Early Warning
(trigger rules) and Assumptions & sources (parameter register, data
dictionary). It opens in any browser with no Python or server, works
offline, follows the viewer's light/dark setting, and people can load their
own CSV/Excel file into it (headers are matched to the schema the same way
as in Python).

Long panels: Home has a "Try a long panel" button (30 invented SOEs,
2005–2024, `data_loader.long_panel_demo()`) to see how they are drawn. Year
chips are replaced by from–to year selects; a KPI trend
with 11 or more years is drawn as a line (latest point marked, labels
thinned) instead of bars; bar lists with more than 12 SOEs show the 12
weakest (or largest EFC) first with a "Show all" button.

The calculations run in the browser (`templates/engine.js`, a JavaScript
port of `calculations.py`, `shocks.py`, `narrative.py`, `utils/summary.py`,
the GRE uplift and `schema.py`'s column matching). Every number they use — coefficients, cutoffs, the
rating/PD table, sector tables, shock defaults, trigger rules — is embedded
from `config.py` when the file is built, so recalibrating `config.py` needs
no JavaScript change. **If you change a formula** in the Python modules,
make the same change in `templates/engine.js` and run

```bash
python tests/check_engine_parity.py     # needs Node.js; compares JS vs Python
python tests/check_cash_channel.py      # oil-shock cash channel checks
```

From a shell:

```bash
python report.py --demo --out soe_tool.html                 # 8-SOE demo portfolio
python report.py --sample --out soe_tool.html               # built-in 2-SOE sample
python report.py --input my_soes.xlsx --lgd 70 --gdp 9.5e12 --out soe_tool.html
```

Files: `templates/app.html` (skeleton), `templates/app.css` (styles, same
palette as the Streamlit theme), `templates/app.js` (tabs, controls, SVG
charts), `templates/engine.js` (calculations). The Monte Carlo in the HTML
file uses its own seeded random generator, so individual draws differ from
numpy's, but percentiles agree within sampling error (checked by the parity
script).

## Page layout

Every page opens with a row of key figures (counts, medians, totals) in
boxes with a light wash of their status colour — red alert, amber watch,
green good, blue for plain totals — and the detail underneath. On Home the
data loader takes the left half and the portfolio overview the right half.
The HTML version builds the row in `templates/app.js`; the classic Python
pages use `utils/theme.stat_strip` with the numbers from `utils/overview.py`
(the standard stress test, KPI status with suppressed ratios as alerts, the
portfolio overview), so both show the same figures.

## Charts

Every line chart — in the HTML version and on the Python pages — is a smooth
curve through the data points (a cardinal spline, `config.LINE_SMOOTH_TENSION`
= 0.75; `templates/app.js` smoothPath and `utils/charts.smooth_xy` draw the
same curve). The curve passes through every point; between two years it is for
reading the trend only, and the values are the ones at the points (hover).
Missing years break the line instead of bridging it.

## Uploading data

CSV or Excel (.xlsx/.xls), one row per SOE-year. The same reading rules run
in the browser (`templates/engine.js`) and in Python (`data_loader.py`),
checked against each other by the parity script:

- Column names are matched to the standard schema: exact name, known
  synonym, or close spelling; the mapping is shown for review.
- Excel: the sheet named "Data" (the template's) or else the first sheet.
  Title or note rows above the table are skipped — the header is the row
  among the first 15 that matches the most schema columns.
- CSV: comma, semicolon, tab or pipe separators are detected; UTF-8 or
  Windows (cp1252) text.
- Numbers as spreadsheets display them are read: `1,234,567`, `(1,234)` for
  negatives, `35%`, `1234,5` (decimal comma), `1 234`; `-`, `n/a` and blanks
  are missing. `1,234` is read as one thousand two hundred thirty-four.
- Years such as `FY2023` or `2023/24` are read as 2023.
- Uploaded files are read in the viewer's browser and are not stored: reload
  the page and it starts again from the demo data.

PDF statements are not read here; they go through the extraction step into
the standard Excel template first.

## Where to make changes later

Almost everything tunable lives in **`config.py`**:

- `ZEM_COEFFICIENTS` / `ZEM_CONSTANT` — the Altman Z''-EM formula itself
- `Z_DISTRESS_CUTOFF` / `Z_SAFE_CUTOFF` — zone boundaries
- `Z_RATING_TABLE` / `z_rating()` — indicative credit-rating cohort mapping
- `PD_BY_ZONE` — PD mapped from Z-EM zone, a placeholder pending
  probit-estimated probabilities
- `KPI_THRESHOLDS` — red/amber/green cutoffs, formulas' required raw
  columns, and the description shown under each chart
- `KPI_CATEGORIES` / `CATEGORY_LABELS` — which ratios show up under
  Profitability / Liquidity / Solvency / Fiscal dependency
- `SECTOR_FUEL_COST_SHARE`, `DEFAULT_SHOCK_PARAMS`, `DEFAULT_EXPOSURES`,
  `MC_DEFAULT_*` (incl. `MC_DEFAULT_CORRELATIONS`) — shock, exposure and
  Monte Carlo defaults
- `DEFAULT_CASH_SETTINGS` — cash channel of the shock engine (State
  compensation paid in-year, collection of unpaid compensation, write-off,
  short-term / supplier-arrears funding of the cash gap, interest on new
  debt, VAT). The defaults reproduce the original model
- `OIL_SHOCK_PRESET` — the "Oil +60% with delayed State payment" preset
  (SENELEC review assumptions; the 8% interest rate is a placeholder)
- `EAD_SHARE_DEFAULT` / `EAD_SHARE_PRESETS` — EAD proxy (share of total
  liabilities; 60% / 80% sensitivity cases)
- `PARAMETER_REGISTER` — one row per coefficient/threshold/default with its
  value, source and status (literature/data, user-set, proxy, placeholder,
  design choice). Update a row when a placeholder gets a source; the
  Assumptions pages read it
- `schema.py` `VARIABLES` — the standard data schema: add a synonym there
  when an extraction produces a new header spelling
- `THEME` / `ZONE_COLORS` — the color palette (World Bank navy #002244,
  bright blue #009FDA, good / watch / alert). The HTML version carries the
  same values as CSS tokens at the top of `templates/app.css`
- `TRIGGER_RULES`, `REPORT_HEADLINE_KPIS`, `REPORT_EFC_GDP_WATCH/ALERT` —
  Early Warning rules and HTML-version display settings
- `CHART_LAYOUT` / `FONT_SCALE` — shared chart sizing and app-wide font scale

## Known simplifications, flagged in-app

- PD comes from each SOE's rating band in the 20-band cohort table — not yet
  probit-estimated from panel data.
- EAD is a share of Total Liabilities (100% default, 60% / 80% sensitivity
  cases) unless the data report Government Guaranteed Debt and that basis
  is selected.
- Shock exposures are bottom-up where the data carry them (fuel cost, FX
  debt, short-term debt, exposure shares); otherwise sector or generic
  placeholder defaults, labelled as such under each slider.
- Shocks follow a step profile (full size for the active years, then off);
  there is no AR(1) persistence. The Monte Carlo draws are independent
  across simulations, correlated across channels.
- LGD is user-set (1–100%); sector reference ranges are shown but not
  auto-applied.
- The shock engine holds Tax Expense flat across the horizon and carries
  the reported Net Income plus the shock's effect on EBIT and interest.
  Every cash shortfall is borrowed (no opening cash buffer is drawn down):
  long-term by default, or in current liabilities for the short-term share
  set on the Cash & financing tab. A borrowed loss leaves total assets
  unchanged (TA = TL + Equity); `legacy_loss_assets = True` restores the
  original rule. The model is annual. See `shocks.py` for full documentation.
- Fuel: an end-user tariff increase (policy Option B) is applied first; the
  rest of the fuel-cost change is split between customers (tariff
  pass-through, Case B), the government (State compensation, Case C —
  recognised in full, paid in cash only at the in-year paid share) and the
  SOE (the rest, Case A).
- The PDF-to-Excel extraction step is not part of this tool; the upload
  expects the standard schema (or recognisable synonyms) and records
  provenance columns when the file carries them.
- Chart PNG downloads need the pinned `kaleido==0.2.1` + `plotly==5.24.1`
  combination in `requirements.txt` — if it can't render an image, the
  "🖼 Chart" button simply doesn't appear; "⬇ Data" always still works.
- Portfolio averages are simple means across SOEs — not asset-weighted.
- A full guidance note (methodology, assumptions, calibration) is planned
  once the framework stabilizes — not yet built.

## October 2026 — optional government-support workbook panels

**No Senegal/Senelec financial statements are bundled or preloaded.** `Home.py`
continues to start with the same built-in illustrative 8-SOE demo portfolio. A
new workbook is only used after the viewer clicks **Upload data** and selects a
local CSV/Excel file. Switching to any built-in dataset (or reloading) clears
the uploaded dataset and its supplementary disclosures.

Uploads are handled in the browser. The workbook's main `Data` tab is used if
present, otherwise the first sheet. An extended workbook may also contain
`Grants_detail`, `Source_lines`, `Validation`, `Checks`, and `Definitions`:

- Main-sheet columns such as `tariff_pso_compensation`, `operating_subsidy`,
  `investment_grant`, and `equity_injection` map to optional numeric schema
  fields (the data dictionary shows the standardized labels).
- Records in `Grants_detail` marked **Flow** can fill missing annual-support
  cells on the main sheet for the matching SOE and year. If the grant sheet
  supplies FCFA (ones), values are converted to the row's stated `Units`;
  dissimilar currencies are rejected. Primary-sheet values win if sources
  disagree, with reconciliation differences listed under **Assumptions**.
- If a workbook has multiple SOEs, `Grants_detail` needs an `Entity` or `SOE`
  column for an unambiguous join. Stocks, guarantees, and tax relief are not
  summed with annual cash flows. Missing values are not silently set to 0.
- **KPI Dashboard** adds a *reported vs mechanical ex-tariff-compensation
  EBIT-margin* chart for uploaded records with a reported tariff-compensation
  amount. The adjusted series is a sensitivity, not audited accounting.
- **Government Support** adds a category-by-year annual-flow chart and table
  but does not alter the existing GRE Role × Link rating-uplift methodology.
- **Assumptions** lists supplementary workbook validation results, source
  lines, grant details, and reconciliation issues. **Shock Scenarios** flags
  missing actual exposure shares; its scenario equations are unchanged.
- The four existing KPI charts, all nine page tabs and built-in datasets remain
  unchanged. The Profitability dropdown continues to exclude EBITDA margin.
- All line charts (historical, scenario, percentile fans, and the optional EBIT
  comparison) use the same smooth spline from `config.LINE_SMOOTH_TENSION`.

The Excel upload widget in the interactive HTML uses SheetJS (xlsx 0.18.5) via
`cdnjs.cloudflare.com` on the first Excel upload and requires web access to
that library. CSV uploads work without loading SheetJS. Streamlit must be
served via `Home.py`, which already embeds the HTML UI with uploads enabled.


## Profitability KPI: Cost recovery

The **Cost recovery (x)** selection is **always displayed** inside the existing **KPI Dashboard → Profitability → Ratio** control, regardless of whether data for the metric exist. It is available in trend, comparison, and scorecard views, with the existing chart styles and illustrative thresholds.

`Cost recovery = (Revenues - Government Grants) / (Cost of Goods Sold + Other Operating Expenses)`

Excel/CSV uploads may use these column labels or schema keys `cost_of_goods_sold` / `other_operating_expenses`. There is no `Operating Expense` fallback: it is not necessarily equal to the named sum. Invalid/non-positive cost totals and missing components produce `n/a`; the KPI remains selectable but displays "Data unavailable" when no row contains the necessary inputs. **This computation assumes Government Grants were included in the supplied Revenues**, so verify statement classification to prevent double subtraction. Tariff/PSO already represented by Government Grants is not deducted separately, and investment grants/equity support must not be combined with the income-statement grants value. Illustrative traffic-light cutoffs: alert <1.00x, good >=1.10x.

The built-in demo has no separate COGS and Other Operating Expenses components and is intentionally unchanged: its profitability dropdown nevertheless offers Cost recovery and shows "Data unavailable" until suitable data are uploaded. An uploaded Senelec workbook with all required fields automatically plots its actual values.

## Persistent navigation and KPI catalog

All nine top-level tabs, all configured KPI ratio choices (excluding intentionally removed EBITDA margin), and the new support/evidence panels remain visible with the built-in demo. Missing values display a `Data unavailable` message and, where appropriate, identify absent source fields. Uploading a compatible workbook populates existing controls; it does not reveal new navigation items. Missing observations are not silently treated as zero or counted as risk alerts.


### Download any chart as PNG

Move the pointer over any chart in the interactive `Home.py` dashboard, then click the small download icon in its upper-right corner. This saves **only that chart** as a high-resolution PNG (up to 3× the SVG resolution), rather than taking a screenshot of the entire page. The export works for all rendered SVG charts including KPI trends and comparisons, Altman Z-EM, Expected Fiscal Cost, Shock Scenarios and uploaded-workbook government-support charts. It uses no external image-export service. When a chart has no data, there is no image to download; its placeholder remains visible. Keyboard users can Tab to the icon. All page menus and KPI choices remain available without an upload.

The optional `classic.py` multipage Streamlit interface uses Plotly's image-download icon on chart hover as well.

## Oil shock: cash, State compensation and tariff policy

Follows the review note on SENELEC: an oil shock is not only a cost shock, it
opens a gap between fuel bills paid now and State compensation paid later,
which the utility borrows to cover.

- **Fuel tab** — *End-user tariff increase* (Option A = 0% freeze, Option B =
  +10–15%) and *State compensation share (Case C)*: the share of the
  remaining fuel-cost change the State compensates (for SENELEC, the gap
  between the regulator's allowed revenue, RMA, and tariff revenue).
- **Cash & financing tab** — share of the compensation paid in the same year
  (a ~300-day lag is about 18%; the review uses 30%), share of unpaid
  compensation collected the next year, share written off as a loss (100% =
  the "treat unpaid compensation as a loss" proxy), share of the cash gap
  funded short-term and via unpaid supplier bills, interest rate on new
  borrowing, unrecovered input VAT on the extra fuel bill.
- **Presets** — "Oil +60% with delayed State payment" (`OIL_SHOCK_PRESET`),
  "Option A: tariff freeze", "Option B: +10%" and "+15%". In the Python
  version the oil preset is a switch above the tabs.
- **Liquidity & State compensation card** — State compensation recognised,
  paid in cash and still unpaid; cash funding gap, new short-term debt,
  supplier arrears and interest; current ratio, adjusted current ratio
  (without State receivables and trapped VAT) and debt to assets; who pays
  the fuel-cost change; and a year-by-year table. The scenario CSV carries
  the same columns.
- Optional data columns: `Government Arrears Owed` is read as the opening
  State receivable and `VAT Credits` as the opening trapped VAT; both are
  left out of the adjusted current ratio.

Reading the results: when a receivable is funded with short-term debt, equal
amounts are added to current assets and current liabilities, so a current
ratio below 1 can rise. Net income and Z-EM barely move while compensation
is booked as revenue; the stress shows in cash, short-term debt, the
adjusted current ratio and the State's unpaid bill. Writing unpaid
compensation off as a loss moves Z-EM.

With every new setting at its default the engine gives the original
results, except that a borrowed loss no longer reduces total assets. In the
demo portfolio's standard stress, zones, ratings, EFC and the early-warning
flags stay the same; only the Z-EM values of the loss-making SOEs become
less negative (SOE A −16.5 → −9.3 in the final year). Longer horizons or
other scenarios can move a rating band.
`DEFAULT_SHOCK_PARAMS["legacy_loss_assets"] = True` brings the old numbers
back exactly.

