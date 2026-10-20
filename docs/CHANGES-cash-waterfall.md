# Cash waterfall, emergency government support and RMA coverage

This builds on `fuel-path-cash-first` (the version in `SOE-main_1.zip`, 20 Oct 2026). It adds the three items from the SENELEC oil-shock note that the tool did not yet cover:

- the cash waterfall reform;
- the "need for emergency government support" at the end of the financing order;
- Option A's "customer collections cover only 65–68% of the shocked RMA".

The framework is unchanged: Z″ → rating → PD → EFC = PD × EAD × LGD. The Python engine (`shocks.py`) and the JavaScript engine (`templates/engine.js`) stay in parity.

**Default behaviour.** Everything new is off by default (`waterfall_on = 0`, `borrowing_cap_debt_to_assets = 0`). With the shipped settings, the engine gives the previous numbers bit for bit on every existing output column. This was checked against the previous `shocks.py` on 187,824 values: the demo portfolio with and without a cash column, the defaults, the oil preset, legacy mode and 40 random cash settings. The new columns are additions only.

## Changes

### A. Cash waterfall reform (`waterfall_on`, `waterfall_refinance_share`, `short_term_debt_rate`, `waterfall_long_term_rate`)

- **What it represents.** Revenues are paid into a protected account (SENELEC: the FSE) and paid out in a fixed order, with IPPs first. Suppliers are no longer paid late. Because the cash flow is predictable, overdrafts can be refinanced into structured long-term loans.
- **What the engine does when it is on:**
  1. **Refinancing, at the start of projection year 1.** The amount refinanced is R = `waterfall_refinance_share` × short-term bank debt, capped at current liabilities.
     - Short-term bank debt is the optional `Short Term Debt` column. Without that column, the proxy is `near_term_maturity_share` × total liabilities.
     - Current liabilities fall by R. Total liabilities do not change, because the debt moves to non-current. Working capital and X1 rise.
  2. **Interest saving, every year.** The saving is R × (`short_term_debt_rate` − `waterfall_long_term_rate`). It raises net income and lowers interest expense. The refinanced debt also leaves the base of the refinancing-spread shock: the near-term maturity share falls by R / total liabilities.
  3. **IPPs paid first.** No supplier arrears build up: `cash_gap_payables_share` is set to 0, so the short-term part of a cash gap is interest-bearing bank debt. A cash gap during the shock keeps the short-/long-term split and the rate set for it on the Cash & financing tab.
- **Why the borrowing terms in point 3 stay as set.** The note says the waterfall lets SENELEC refinance its existing overdrafts. It does not say that borrowing during the shock becomes long-term. A first version made that borrowing long-term too, and it produced a misleading result: the less the State paid, the better the Z-score looked. Unpaid compensation sits in current assets, so funding it long-term inflates working capital. With 0% of compensation paid, Z-EM rose to 1.57 by 2029.
- **Defaults.** `short_term_debt_rate` is 8.0%, the mid-point of the note's 7.5–8.5% for overdrafts. `waterfall_long_term_rate` is 5.0%, a placeholder to be set from the refinancing terms (DFI or concessional terms are lower). `waterfall_refinance_share` is 100%.
- **Front end.** The Cash & financing tab has an Off/On switch, the refinanced share (with the debt base it uses) and the two rates. A "+ Cash waterfall (reform)" button sits in the oil preset row; it toggles the reform on top of any scenario (`config.WATERFALL_PRESET`). The no-shock path uses the same policy, so "vs no shock" still isolates the shock. The Liquidity card adds two tiles and a year-by-year table that compare the same scenario with and without the reform (Z-EM, rating, current liabilities, current ratio, EFC or EFC/GDP). The chart caption ends with "· cash waterfall".
- **Legacy mode.** `legacy_loss_assets = True` ignores the waterfall.

### B. Emergency government support (`borrowing_cap_debt_to_assets`)

- **What it does.** New borrowing stops where total liabilities / total assets at year end would pass the cap. The rest of the cash gap is a government capital injection, which goes into equity and not into retained earnings. Interest is paid only on what is borrowed, and TA = TL + Equity still holds. This is the last step of the IMF SOE Stress Test Tool's financing order (User Guide 2023, Section VIII): cash, then borrowing, then injection.
- **Outputs.** `Emergency Support` (the year's injection) and `Cumulative Emergency Support`. The Liquidity card shows a tile, with the amount as a share of year-1 GDP when GDP is entered. A warning box under the key figures says the injection is a budget outlay on top of EFC.
- **Default.** 0 = no cap; the SOE can always borrow.

### C. RMA coverage (`Tariff Share of RMA`)

- **Formula.** (Revenue − Government Grants + tariff increase + tariff pass-through) / (Revenue + fuel-cost change). This is what customers pay as a share of the regulator's allowed revenue after the shock; the State covers the rest.
- **When it is NaN.** When the data have no `Government Grants`.
- **Display.** The Liquidity card shows the lowest shock-year value against the base year, and the year-by-year table has a column for it.

### D. Other

- **Scenario CSV.** It gains `Refinanced Debt`, `Interest Saved`, `Emergency Support`, `Cumulative Emergency Support` and `Tariff Share of RMA`.
- **Assumptions page.** `PARAMETER_REGISTER` has four new rows with sources.
- **Glossary.** `GLOSSARY` has three new terms: Cash waterfall, Emergency support and RMA coverage.
- **Classic version.** The classic Streamlit page (`app_pages/shock_scenarios.py`) has the same controls and outputs.

## SENELEC, 2024 base

The settings are the oil preset (+60% in 2026, +30% in 2027; 60% of compensation paid in-year), with cash 56.3 bn (Trésorerie-actif) and short-term bank debt 134.5 bn (Trésorerie-passif, `Short Term Debt`). LGD and EAD are 100%, and GDP is 19,618 bn growing 2.5% a year.

| 2026 | Without waterfall | With waterfall |
|---|---|---|
| Z-EM (rating) | 0.15 (CCC+) | 0.57 (B−) |
| Current liabilities | 1,126.6 bn | 988.0 bn |
| Current ratio | 0.81 | 0.93 |
| Interest saved | — | 4.0 bn a year (134.5 × 3%) |
| EFC (% of GDP) | 254.6 bn (1.24%) | 110.8 bn (0.54%) |

- **Why EFC halves.** Z crosses 0.5, the CCC+/B− boundary, and the PD falls from 16.27% to 7.1%. Z = 0.57 sits just above that boundary, so the size of the gain depends on a single rating step.
- **Distress zone.** Z stays below 1.1, so SENELEC remains in the distress zone.
- **No shock, waterfall on.** The rating moves only from 2027 (0.55, B−).
- **Customers' share of the RMA in 2026.** 60.8% under Option A and 69.9% under Option B +15%, against 78.8% in 2024. The note says 65–68% for Option A; the base of that figure should be confirmed.
- **Emergency support.** With nothing paid by the State and a cap at the 2024 level (0.70), the injection is 16.5 bn in 2026 and 18.8 bn in 2027.

## Tests

- `tests/check_cash_waterfall.py` (new, 13,088 checks):
  - off by default, bit-exact;
  - refinancing arithmetic, the cap at current liabilities and the proxy;
  - no supplier arrears under the reform, and the smaller refinancing-shock base;
  - the cap, injection and balance-sheet identity, and that a cap that does not bind changes nothing;
  - RMA coverage, including missing grants;
  - legacy mode and the caption;
  - a higher Z-EM with the reform.
- `tests/check_engine_parity.py`:
  - six new scenarios: `waterfall`, `waterfall_half`, `waterfall_custom`, `cap`, `cap_waterfall`, `waterfall_legacy`;
  - a partial `Short Term Debt` column;
  - eight more compared columns.
- The existing checks pass unchanged: `check_cash_channel.py`, `check_fuel_path_cash.py` and `check_cost_recovery.py`.
