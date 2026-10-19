# Fuel price path, oil linkage, tariff base and cash-first financing

Branch `fuel-path-cash-first`, from `064ac24` (main, 19 Oct 2026). Not pushed.

This extends the oil-shock cash channel already in the tool. It adds only what the SENELEC scenario (+60% oil in 2026) and the IMF SOE Stress Test Tool approach need. The framework is unchanged: Z″ → rating → PD → EFC = PD × EAD × LGD, with EAD = share × total liabilities. SENELEC enters only through parameters (`config.OIL_SHOCK_PRESET`). The Python engine (`shocks.py`) and the JavaScript engine (`templates/engine.js`) stay in parity.

**Default behaviour.** With the shipped defaults the engine gives the `064ac24` numbers bit for bit, with one exception (item D). An SOE whose data report `Cash and Equivalents` and that has a cash shortfall now pays that shortfall from its cash before it borrows. The demo portfolio has no cash column, so the demo, Home, Report and Early Warning numbers do not change. `cash_buffer_share = 0` restores the old borrow-everything rule exactly.

## Changes

### A. Fuel price path (`fuel_shock_path`)

- **What changed.** A new magnitude in `DEFAULT_SHOCK_PARAMS`: a per-year list of fuel price changes. Index 0 is projection year 1, and the path is zero beyond its end. When it is set, it replaces the step shock (`fuel_shock_pct` for `shock_duration_years`) for the fuel channel only. The other shocks keep the step. The tariff increase applies in the years where the path is non-zero. Monte Carlo centres the fuel draws on the path's peak (the first largest absolute value) and rescales the whole path for each draw, so its shape is kept. The chart caption reads `Fuel path +0/+60/+30/+0/+0%`. The duration suffix appears only when a step shock is also on.
- **Why.** Stefano's scenario is "+60% in 2026". The step shock always starts in projection year 1 (2025 from a 2024 base). The IMF tool also enters oil as an explicit annual price path.
- **Default.** `[]`, which means the step profile, as before. An empty list, `None` or a scalar (the zero-magnitude dicts put `0.0` in) all mean the step.
- **How to turn it off.** Leave the path empty (blank field in either front end).
- **Tests.** `check_fuel_path_cash.py` §3 shows that `[p]*D + [0]*(H−D)` equals the step of magnitude `p` for `D` years bit for bit, including the tariff, on 8 SOEs × 6 scenarios × 2 magnitudes × 2 tariffs. It also checks zero years, years beyond the path, Monte Carlo centring and shape (§7), and the caption (§8). §2a shows that an empty, `0.0` or `None` path equals `064ac24`. Parity scenarios `path_step` and `path_neg` cover the JS engine, as does the JS Monte Carlo path check.

### B. Oil linkage of the fuel bill (`fuel_oil_linkage`, ε)

- **What changed.** `fuel_cost_increase = fuel_cost_share × OpEx × ε × p_t`, evaluated left to right, so ε = 1 is bit-exact.
- **Why.** HFO and diesel follow oil; coal does not. In 2022, coal was 35.7 bn of SENELEC's 494.9 bn of fuel purchases (annual report 2022), so ε ≈ 0.9. φ × ε is the IMF tool's "share of oil in purchased inputs".
- **Default.** 1.0 (inert).
- **How to turn it off.** Set it to 1.
- **Tests.** §4 checks that ε 0.5 halves the fuel-cost change and equals half the shock. §2a checks that ε = 1 matches `064ac24`. Parity scenario `linkage`.

### C. Tariff increase base (`tariff_revenue_base`)

- **What changed.** `"revenue"` (as before) or `"revenue_ex_grants"`, which computes the tariff revenue as `tariff_increase_pct × max(0, Revenue − Government Grants)`. Missing or NaN grants count as 0. The floor at 0 handles grants above revenue.
- **Why.** In 2024, 214.7 bn of RMA compensation sits inside SENELEC's 1,015.2 bn of revenue. A +15% tariff applies to customer sales (800.5 bn), not to the compensation.
- **Default.** `"revenue"` (inert).
- **How to turn it off.** Choose "All revenue".
- **Tests.** §5 covers revenue, ex-grants, grants missing, grants NaN, and grants above revenue. Parity scenario `tariff_exg`; the oil preset scenarios use ex-grants.

### D. Cash-first financing (`cash_buffer_share`, `cash_floor_opex_share`)

- **What changed.** The engine carries a `Cash` state, the opening `Cash and Equivalents` (0 when not reported). When a year has a cash need, it first draws `min(need, max(0, Cash − floor × OpEx)) × share` from cash. Only the rest is borrowed, grossed up for half a year of interest as before. The draw lowers Cash, current assets and total assets. In a surplus year, after short-term debt is repaid, the leftover rebuilds Cash and current assets only up to the cumulative drawdown of earlier years. Any remainder goes to total assets only, as before. New output columns: `Cash` (stock) and `Cash Drawdown` (flow). `Cash Funding Gap` is now the amount borrowed after cash. The rule is off when the data report no cash, when the share is 0, or when `legacy_loss_assets=True`.
- **Why.** Many SOEs in developing countries cannot borrow quickly (team decision, 19 Oct 2026). The IMF SOE Stress Test Tool User Guide (2023, Section VIII) meets liquidity gaps from cash first, then borrowing, then injections.
- **Balance sheet.** With draw d: ΔTA = Δreceivable + VAT − d, ΔTL = funding − repaid, ΔE = NI. Because funding − interest_new = need − d, ΔTA = ΔTL + ΔE holds (tested to 1e-6).
- **Default.** Share 1.0 and floor 0.0. This is the one default that changes outputs, for SOEs that report cash and run a shortfall. Rebuilding is capped at the drawdown so that the no-shock path of a profitable SOE stays bit-exact.
- **How to turn it off.** `cash_buffer_share = 0` (the "Cash drawn before borrowing" slider at 0%).
- **Reading it.** Paying from cash lowers X1 by 6.56 × draw / TA, whereas long-term borrowing leaves working capital unchanged. Less is borrowed, though, so liabilities, EAD and the X4 denominator are lower, and the net effect on Z-EM can go either way. See the numbers below.
- **Tests.** §6 uses round numbers: cash 150, loss 100, floor 10% of OpEx 900 → draw 60, borrow 40 / (1 − 0.04). Year 2 draws nothing at the floor. Share 0.5 → draw 30. No floor → draw 100, then 50. The rebuild is capped (cash 90 → 110 → 130 → 150 → 150). Cash is 0 without a cash figure and flat when the buffer is off, and the identity holds. §1 checks that legacy mode never draws. §2b–c check `064ac24` equivalence. Parity scenarios `cash_floor`, `cash_half` and `cash_off` run on a partial cash column (SOE A, C, D, G, H); CASH_KEYS adds `Cash` and `Cash Drawdown`.

### E. Oil preset re-sourced (`OIL_SHOCK_PRESET`)

| Setting | Before (placeholder/proxy) | Now | Source (status "Literature / data" in the register unless noted) |
|---|---|---|---|
| Fuel price path | step +60%, years 1–2 | `[0, .60, .30, 0, 0]` | Task team scenario, email of 16 Oct 2026 (+60% in 2026); 2027 +30% is a half-reversion assumption |
| φ fuel share of OpEx | 0.70 (incl. IPP) | 0.55 | Annual report 2022: fuel purchases 494.9 / OpEx 888.5 bn = 0.557, rounded down; IPP excluded (0.70 = sensitivity) |
| ε oil linkage | — | 0.9 | HFO 361.9 and coal 35.7 within 494.9 bn (AR 2022) |
| θ pass-through / σ State share | 0 / 1 | 0 / 1 | Tariff frozen; the State compensates the RMA gap |
| ρ paid in-year | 0.30 | 0.60 | 2022: 333.2 bn recognised, 135.8 bn still receivable at year-end |
| Backlog collected / provision | 1.0 / 0 | 1.0 / 0 | Receivable paid with a lag (team decision, 19 Oct 2026: SENELEC's 2022 pattern); write-off = sensitivity |
| Short-term share / payables | 1.0 / 0 | 1.0 / 0 | Overdrafts and short-term loans |
| Interest on new debt | 8% (placeholder) | 3.3% | Interest 14.6 bn / borrowings 430.8 bn (2024) = 3.4%, rounded |
| Trapped VAT | default 0 | 0 | 2024 VAT credit not in the workbook |
| Tariff base | revenue | revenue less grants | 214.7 bn RMA compensation inside revenue |
| Cash-first share / floor | — | defaults 1.0 / 0 | Status "Model design choice": IMF User Guide 2023, Section VIII |

`fuel_shock_pct` stays at 0.60: it labels the button and centres Monte Carlo, and the engine ignores it while a path is set. Both front ends set the horizon to at least 5 years with the preset. The parameter register (`config.PARAMETER_REGISTER`, Assumptions page) has new rows for the path, φ, ε, the tariff base, the cash-first share and the cash floor. The paid-share and interest rows are re-sourced (interest now shown as `0.0% (oil preset 3.3%)`), and the old "30% used as a proxy" text is gone.

### F. User interface

- **HTML app (`templates/app.js`).** The Fuel tab gets a path text field (whole percents only, blank means the step, invalid input shows a hint and is not applied, with a note when the path is longer than the horizon), an ε slider and an "All revenue / Revenue less grants" toggle. The Cash & financing tab gets "Cash drawn before borrowing" and "Cash floor kept" sliders. The oil preset assigns a copy of the path and sets `H = min(7, max(H, 5, path length))`. The Liquidity card gets a "Cash drawn down" tile (opening → closing cash, floor) and a "Borrowed after cash" tile when cash-first is live, plus Cash drawn / Cash columns in its table. The scenario CSV adds `Cash Drawdown` after `Cash Funding Gap` and `Cash` after `New Long-term Debt`. The Monte Carlo note, the footer and the State-compensation alert (number of path years) are updated. `fuel_shock_path` joins `MAGS`; its zero is a frozen `[]` and the code always assigns new arrays.
- **Streamlit page (`app_pages/shock_scenarios.py`).** Adds the path text input, the ε slider, a tariff-base radio (never routed through `_start`, which casts to float), the cash sliders (with an "inert" caption when the SOE reports no cash), horizon default 5 with the oil preset, the five new parameters, the cash tile and table columns, and the Monte Carlo captions. `utils/overview.py`: `fuel_shock_path` is in `MAGNITUDES` (zero = `[]`). `schema.py`: `Cash and Equivalents` is "used by cash-first financing".
- **Label.** The exposure source label for policy settings is now "Policy setting (default: original model, cash drawn first)", byte-identical in `calculations.py` and `engine.js`.
- **Cache.** `Home.py` caches the embedded HTML with `@st.cache_data`. After pulling this branch, restart Streamlit (or clear its cache) to load the new `app.js` and `engine.js`.

### G. Tests

| Script | Result on this branch | On `064ac24` |
|---|---|---|
| `tests/check_cash_channel.py` | OK, 3,536 checks | 3,536 |
| `tests/check_fuel_path_cash.py` (new) | OK, 73,303 checks; 24 SOE × scenario cases draw cash | — |
| `tests/check_engine_parity.py` (Node 22) | OK, JS matches Python on 12,253 checks | 7,362 |
| `tests/check_cost_recovery.py` | PASS | PASS |

`check_cash_channel.py` tests 4–5 used the old preset's round numbers. They now use a local `LEGACY_OIL` dict, which holds the preset as it stood, so the arithmetic checks are independent of recalibration. `node --check` passes on `app.js` and `engine.js`. A headless-browser smoke run of the HTML app (oil preset, path edits, invalid path, Cash tab, Monte Carlo and All-SOEs views, other pages) showed no page errors. A stubbed-Streamlit run of the classic page (preset on/off, single and Monte Carlo views, invalid path) ran end to end.

## IMF approach: where each element lands

| IMF STT element | Where it lands in the engine |
|---|---|
| Oil enters cost of sales as purchases × share of oil in inputs × Δoil (annual price path, p. 19, 47; HTN p. 9 "share of oil in purchased inputs") | `fuel_cost_increase = φ · ε · OpEx · p_t` with `fuel_shock_path` (new) and `fuel_oil_linkage` ε (new); φ·ε is the IMF structural parameter |
| Regulated prices move only via indexation; "tariff indexation shock" = government severs the link (p. 32) | `tariff_increase_pct` (existing), tariff freeze = Option A; base ex-grants (new switch) so the compensation already inside Revenue is not re-indexed |
| Subsidies are exogenous lump sums (p. 47); HTN Table 1 fiscal link = "subsidies triggered by indexation schemes" | `fuel_subsidy_share` σ makes the subsidy endogenous = the HTN fiscal link; this is our extension, stated as such |
| Financing hierarchy: cash first, then borrowing up to a leverage cap, injection as last resort (pp. 60–62) | **new** cash-first step (`cash_buffer_share`, `cash_floor_opex_share`), then Hyunju's borrowing split; the government "injection" in our framework is the compensation actually paid (ρ) and, contingently, EFC |
| No-injection counterfactual: whole gap borrowed, interest on new debt at the effective rate, one-year grace (pp. 64–65) | Hyunju's borrow-the-gap rule with `new_debt_interest_rate` and half-year interest on the draw = the counterfactual; kept |
| Arrears and overdrafts excluded as gap fillers (Note 43) | We allow supplier arrears and short-term bank debt (SENELEC reality); stated as a departure |
| Not in the IMF tool: State compensation receivables, pass-through parameter, fuel share of opex, +60 % convention | Our layer (σ, ρ, backlog, provision) stays; +60 % is Stefano's scenario, not a convention |

## Not changed, and why

- **Provision placement stays below EBIT** (Hyunju's rule). SYSCOHADA would present a doubtful-receivable provision above the operating result. This is an open convention, and it does not matter under the headline treatment for SENELEC (receivable paid with a lag, provision 0).
- **`legacy_loss_assets=False` is kept** (TA = TL + E, patch P1). Legacy mode also switches cash-first off, so `legacy_loss_assets=True` still reproduces the original formula exactly.
- **The arrears channel is unchanged.** It has no offsetting entry by design, and the identity tests net it out.
- **No tariff persistence.** Option B applies in shock years only (team decision, 19 Oct 2026). In practice past increases were not reversed (Senegal 2023), so B is a lower bound on the tariff relief.
- **IPP purchases stay outside φ** in the base case (SENELEC parameter table); φ 0.70 is the sensitivity that includes them.
- **No demand response.** Revenue and OpEx are held at base-year values, as in the rest of the engine.
- **Borrowing split, interest gross-up and repayment order are unchanged.** Cash-first only reduces what goes into them.
- **`report.py` export is unchanged.** The four new settings live in `DEFAULT_CASH_SETTINGS` and flow through `soe_exposures`, `POLICY_KEYS`, the report payload and the parity exposure check without new names.

## Numerical equivalence

- **Shipped defaults vs `064ac24`, no cash column.** All 8 demo SOEs (A–H), latest year, H = 5, 6 scenarios: zero, standard stress, custom (negative fuel, FX, rate cut, refinancing, arrears clearing), subsidy, deep, and the old oil preset with policy settings (tariff 10%, provision 30%, payables 40%, trapped VAT 60%, 8%). Every output column of the old engine is identical (`==`, NaN = NaN). The same holds with `fuel_shock_path` set to `[]`, `0.0` and `None`.
- **`cash_buffer_share = 0` vs `064ac24`, with cash.** A demo copy with cash = 25% of current assets for SOE A, C, D, G and H (none for B, E, F). The same 8 SOEs × 6 scenarios are bit-exact.
- **Shipped defaults on the cash copy.** Bit-exact for the 18 cases without cash and for the 6 cash cases that never borrow. The other 24 cases draw cash; for them the test asserts that a draw happens and that TA = TL + E.
- **Monte Carlo without a path.** 200 draws on SOE F give identical draws, Z-EM and EFC to `064ac24`.
- **Legacy.** `legacy_loss_assets=True`, with the buffer at 0 or 1 and with or without cash, equals the original pre-cash-channel formula (1e-9) on 8 SOEs × 5 scenarios.
- **Size of the cash-first effect (demo cash copy, H = 5, final year, cash off → cash first).**

| Scenario | SOE | Cash drawn | Z-EM | Rating | Total liabilities |
|---|---|---|---|---|---|
| No shock | A | 11.84 of 11.84 bn | −8.58 → −10.83 | D → D | 169.4 → 157.6 bn |
| No shock | C | 11.37 of 11.37 bn | −0.52 → −0.85 | CCC → CCC− | 237.4 → 226.0 bn |
| No shock | G | 2.95 of 2.95 bn | −3.90 → −4.34 | D → D | 105.9 → 103.0 bn |
| Standard stress | A | 11.84 of 11.84 bn | −10.00 → −12.56 | D → D | 212.5 → 199.5 bn |
| Standard stress | C | 11.37 of 11.37 bn | −1.38 → −1.75 | CCC− → D | 307.5 → 295.0 bn |
| Standard stress | D | 2.49 of 9.45 bn | 4.81 → 4.97 | AA+ → AAA | 53.4 → 50.8 bn |
| Standard stress | G | 2.95 of 2.95 bn | −5.32 → −5.83 | D → D | 136.5 → 133.3 bn |

In SOE C, X1 dominates and the rating falls. In SOE D, a partial draw lowers liabilities enough for X4 to dominate, and the rating rises. EFC also falls with the lower liabilities (EAD). These cases are the reason for the reading note in the README.

## Files

`shocks.py`, `config.py`, `calculations.py` (label), `schema.py` (used-by text), `templates/engine.js`, `templates/app.js`, `app_pages/shock_scenarios.py`, `utils/overview.py`, `tests/check_fuel_path_cash.py` (new), `tests/check_cash_channel.py`, `tests/check_engine_parity.py`, `README.md`, and this note.
