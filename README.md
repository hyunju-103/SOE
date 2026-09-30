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
│   └── check_engine_parity.py JS engine vs Python modules (needs Node.js)
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
- The shock engine holds Tax Expense and Current Liabilities flat across
  the horizon, carries the reported Net Income plus the shock's effect on
  EBIT and interest, and assumes losses are debt-financed. See `shocks.py`
  for full documentation.
- Fuel: the fuel-cost change is split between customers (tariff
  pass-through, Case B), the government (subsidy share, Case C — reported
  as a direct fuel subsidy, a budget outlay on top of EFC) and the SOE (the
  rest, Case A).
- The PDF-to-Excel extraction step is not part of this tool; the upload
  expects the standard schema (or recognisable synonyms) and records
  provenance columns when the file carries them.
- Chart PNG downloads need the pinned `kaleido==0.2.1` + `plotly==5.24.1`
  combination in `requirements.txt` — if it can't render an image, the
  "🖼 Chart" button simply doesn't appear; "⬇ Data" always still works.
- Portfolio averages are simple means across SOEs — not asset-weighted.
- A full guidance note (methodology, assumptions, calibration) is planned
  once the framework stabilizes — not yet built.
