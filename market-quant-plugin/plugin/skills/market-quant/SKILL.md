---
name: market-quant
description: Institutional quantitative, microstructure, and multi-agent fleet research workflow for equity markets (Indian NSE/Nifty/BankNifty/BeES, US S&P500/Nasdaq/SPDR, or custom tickers). Combines a deterministic Python quant engine (CMF vs RSI divergences, Spot vs ETF real-money flow, 60-day intraday smart-money clock, Hurst exponent, Bollinger squeeze coils, FFT harmonic cycles, 120-day Volume Profile POC/VAL/VAH) with a 5-agent specialist fleet, Quorum blackboard debate, 300-DPI charts, and Clawpilot HTML studio. Triggers — "market quant", "indian market quant", "nifty microstructure", "smart money clock", "hidden market pattern", "quant deep dive", "social media quant chart".
---

# Market-Quant — Institutional Microstructure & Multi-Model Research Fleet

`market-quant` pairs a deterministic Python quantitative engine (`market_quant_engine.py`) with a **multi-model parallel fleet of 5 specialist research agents** that analyze institutional order flow, intraday execution clocks, fractal/harmonic regimes, and macro catalysts across diverse model families, followed by an adversarial **Skeptical Quant Risk Officer** audit.

## Bundled Engine, Companion CLI Extension & Workspace Layout

- **Engine script**: `$HOME/.copilot/skills/market-quant/market_quant_engine.py`
- **Companion Copilot CLI Extension** (`~/.copilot/extensions/market-quant/extension.mjs`):
  - **`market_quant_scan`** tool: Runs `market_quant_engine.py`, streams live progress, and renders an ANSI-colored institutional terminal scorecard (`formatQuantHud`) directly into the CLI timeline. Prefer calling `market_quant_scan` over raw `powershell` whenever the extension is loaded.
  - **`market_quant_hud`** tool: Renders the ANSI-colored terminal scorecard, Spot-vs-ETF order-flow bars, 60-day Intraday Smart-Money Clock, and Multi-Agent Fleet / Quorum Blackboard progress bar for an existing workspace (and optionally opens the HTML dashboard in the browser).
  - **`market_quant_verify_report`** tool: Deterministically audits all `.md` reports in `reports\` and `agents\results\` against `anomaly_summary.json` and `data_quality.json` (enforcing zero-volume CMF exclusions, SHA-256 grounding, and `SIGNAL_SPEC` compliance).
  - **Lifecycle Hooks (`onSubagentStart` / `onSubagentStop`) & Event Listeners**: Automatically injects `quorum_grounding.json` into specialist sub-agents and prints live ANSI progress bars (`[███░░] 3/5 Desks`) and Quorum debate badges in the CLI timeline.
  - **`market-quant-fleet` Dynamic Workflow**: Registered workflow for `run_dynamic_workflow` when the user explicitly requests a full automated workflow run.
- **Default workspace**: `C:\temp\market-analysis\<dd-mm-yy>\`
  - `data\` — cached OHLCV JSONs, `indices_and_etfs_metrics.csv`, `constituents_quant_matrix.csv`, `anomaly_summary.json`, `data_quality.json` (SHA-256 dataset hash, `asof_filter`, `cmf_invalid_symbols`, `fft_reliable`)
  - `agents\briefs\` — auto-generated role briefs for all 5 specialist desks (with embedded pre-sliced JSON payloads)
  - `agents\results\` — per-agent research outputs (`<role>.result.md`)
  - `agents\blackboard\` — `events.jsonl` shared findings log (seeded automatically by the engine)
  - `agents\fleet_dispatch.json` — machine-readable Wave 1 and Wave 2 agent dispatch plan
  - `agents\quorum_grounding.json` — verified ground-truth facts for optional Quorum MCP debates
  - `scripts\` — custom chart/refinement scripts for the session
  - `reports\` — final Markdown deep dive, 300-DPI PNG charts, Clawpilot HTML studio, and social media copy

---

## Runtime Model Selection & Multi-Model Diversity Rules

Before dispatching agents, inspect the host `task` tool schema for currently exposed models. Never hardcode a stale model ID that is absent from the runtime schema.

1. **Assign distinct model families across parallel desks**:
   - Deliberately diversify the 4 Wave 1 research desks across different model providers/families available in the runtime `task` tool enum.
   - If a requested model returns an authorization/availability error (e.g. `401 Unauthorized`), fall back to another verified model within the same or complementary family and log the fallback in the Multi-Model Fleet Audit Table.
   - Assign the Wave 2 **`skeptical_risk_officer`** to a strong/synthesis model from a family different from the primary Wave 1 narrative lead whenever multiple families are available.
2. **Corroboration principle**:
   - Independent agreement across different model families on the same anomaly increases thesis conviction.
   - Disagreement between desks triggers verification against `data\indices_and_etfs_metrics.csv`, `data\constituents_quant_matrix.csv`, and `data\data_quality.json` rather than majority voting.
3. **Optional Quorum MCP integration**:
   - When `quorum-debate_start`, `quorum-board_post`, and `quorum-tally_consensus` are exposed and the user requests a deep/contested bull-vs-bear regime debate, initialize a Quorum debate board with `grounding` set to `agents\quorum_grounding.json`.

---

## Workflow Steps & Completion Criteria

### Step 1 — Wave 0: Run the Deterministic Quant & Microstructure Engine

Run `market_quant_engine.py` via `powershell` to fetch/cache multi-timeframe OHLCV data (2Y daily, 5Y weekly, 60D 1-hour with IANA `ZoneInfo` timezone normalization), compute all quantitative lenses, render baseline charts, and scaffold the 5 specialist briefs plus `fleet_dispatch.json` and `data_quality.json`:

```powershell
python "$HOME/.copilot/skills/market-quant/market_quant_engine.py" --market india --workspace "C:\temp\market-analysis\<dd-mm-yy>"
```

- Supported flags:
  - `--market india` (default: Nifty 50, Bank Nifty, Sector Indices, India VIX, Nifty/Bank/IT/Pharma/Auto/PSU/Gold BeES ETFs, macro proxies, and 30 heavyweight NSE stocks)
  - `--market us` (S&P 500, Nasdaq 100, Russell 2000, VIX, Sector SPDR ETFs, macro proxies, and top US leaders)
  - `--tickers "TICKER1,TICKER2"` to append custom Yahoo Finance tickers
  - `--asof YYYY-MM-DD` to slice all daily, weekly, and hourly series at a historical date for reproducible backtesting
  - `--reuse-data` to reuse cached OHLCV JSON files in `<workspace>\data\` (verified against `primary_index`)
  - `--skip-charts` or `--emit-fleet-plan-only` to refresh CSVs, `anomaly_summary.json`, `data_quality.json`, and agent briefs without rendering charts

**Step 1 is complete when**:
- `<workspace>\data\anomaly_summary.json`, `data_quality.json`, `indices_and_etfs_metrics.csv`, and `constituents_quant_matrix.csv` exist.
- `<workspace>\agents\briefs\` contains the 5 generated specialist briefs and `<workspace>\agents\fleet_dispatch.json` exists.

---

### Step 2 — Wave 1: Dispatch the 4 Specialist Research Desks in Parallel

Read `<workspace>\data\anomaly_summary.json` and `<workspace>\data\data_quality.json` first. Then launch all **4 Wave 1 specialist agents in a single response** using parallel `task` tool calls (`mode="background"`, `agent_type="general-purpose"` or `"research"`), assigning each desk to a **different model family** from the runtime `task` enum:

| Desk Name (`name`) | Capability Band | Preferred Model Family Diversity | Core Responsibility & Output File |
|---|---|---|---|
| `microstructure_orderflow_desk` | `strong` / `workhorse` | Family A | Analyzes the **RSI(14) vs Chaikin Money Flow CMF(20)** quadrant using `SIGNAL_SPEC` (`bull_traps_high_rsi_neg_cmf`, `stealth_accumulation_gems`, `true_institutional_breakouts`, `heavy_institutional_liquidation`), `20D Up/Down Volume Ratio`, and **Spot Index vs Cash-Verified BeES/SPDR ETF CMF divergences**. Writes `<workspace>\agents\results\microstructure_orderflow_desk.result.md`. |
| `intraday_volatility_clock_desk` | `workhorse` | Family B | Analyzes the **60-Day 1-Hour Intraday Smart-Money Clock** (Overnight Gap vs Opening Hour retail trap vs Mid-Session drift vs Final-Hour institutional VWAP execution window, both additive and compounded), **Afternoon VIX Crush**, and **120-Day Range-Distributed Volume Profile (`POC`, `VAL`, `VAH`, `LVN` air pockets)**. Writes `<workspace>\agents\results\intraday_volatility_clock_desk.result.md`. |
| `cycles_fractal_regime_desk` | `strong` / `workhorse` | Family C | Analyzes the **60D/120D Fractal Hurst Exponent ($H$, Standard Error $SE$, and classical Rescaled-Range $R/S$)** vs **1-Year Bollinger Bandwidth Percentile (`BBW %ile`)** volatility squeeze coils and the **Fast Fourier Transform (`FFT`) 25-Day Forward Harmonic Projection** (gated by `fft_reliable` and `harmonic_variance_share_pct`). Writes `<workspace>\agents\results\cycles_fractal_regime_desk.result.md`. |
| `macro_catalyst_correlator_desk` | `workhorse` | Family D | Analyzes the **60-Day Date-Normalized Cross-Asset Macro Correlation Matrix** (`same_day_corr` and `macro_lag1_corr` across Crude, USD/INR, DXY, US 10Y, Gold, VIX) and uses `web_search` to corroborate statistical anomalies with live macro, earnings, and institutional FII/DII flow catalysts. Writes `<workspace>\agents\results\macro_catalyst_correlator_desk.result.md`. |

**Each Wave 1 agent prompt MUST include**:
1. The contents or path of its generated brief in `<workspace>\agents\briefs\<desk>.md` (which already embeds its pre-sliced JSON payload).
2. Direct paths to `<workspace>\data\anomaly_summary.json`, `<workspace>\data\data_quality.json`, `<workspace>\data\indices_and_etfs_metrics.csv`, and `<workspace>\data\constituents_quant_matrix.csv`.
3. Instruction to run independently (do NOT read or wait for peer results in `agents\results\`) and write structured findings to `<workspace>\agents\results\<desk>.result.md`.

Wait for Wave 1 completion notifications and collect results via `read_agent` (`wait: true`). Append a summary line per agent to `<workspace>\agents\blackboard\events.jsonl`.

**Step 2 is complete when**: all 4 Wave 1 result files exist in `<workspace>\agents\results\`.

---

### Step 3 — Wave 2: Dispatch the Adversarial Skeptical Quant Risk Officer

Once Wave 1 completes, launch **`skeptical_risk_officer`** via `task` using a `strong` / `synthesis` model from a model family distinct from the primary Wave 1 author:

- **Input**: `<workspace>\agents\briefs\skeptical_risk_officer.md`, all 4 `<workspace>\agents\results\*.result.md` files, and the raw ground-truth tables (`indices_and_etfs_metrics.csv`, `constituents_quant_matrix.csv`, `anomaly_summary.json`, `data_quality.json`).
- **Mandate**:
  1. Verify every cited ticker number (`RSI-14`, `CMF-20`, `Up/Down Vol Ratio`, `Hurst-60D`, `Hurst SE`, `1Y BBW %ile`, `POC/VAL/VAH`, `FFT cycle days`) against the raw CSVs. Flag and fix any mismatch.
  2. Stress-test bull and bear hypotheses: enforce `cmf_invalid_symbols` volume-quality gates, check `hurst_usable` standard-error bounds, check `fft_reliable` variance-share gates, and define concrete price/indicator invalidation levels.
  3. Rank the top 5 institutional insights with calibrated conviction scores (`[0.00–1.00]`).
- **Output**: `<workspace>\agents\results\skeptical_risk_officer.result.md`.

**Step 3 is complete when**: `skeptical_risk_officer.result.md` is written and all numerical discrepancies (if any) are resolved.

---

### Step 4 — Wave 3: Visual Quality Gate, Synthesis Report & Social Media Pack

Use the unified `SIGNAL_SPEC` interpretation rules below to synthesize the audited multi-desk findings into final deliverables inside `<workspace>\reports\`:

| Quantitative Lens | Bullish / Institutional Accumulation Signal | Bearish / Distribution / Trap Signal |
|---|---|---|
| **1. RSI(14) vs CMF(20) ("The RSI Lie")** | **Stealth Accumulation**: `RSI < 55` with `CMF(20) >= +0.10` and `Up/Down Vol >= 1.25x` (institutions absorbing supply quietly). **True Breakout**: `RSI >= 55` AND `CMF(20) >= +0.10`. | **Bull Trap / Upper-Wick Dump**: `RSI >= 55` (looks strong on a standard chart) but `CMF(20) <= -0.05` (institutions selling into retail gap-ups, closing bars near session lows). |
| **2. Spot Index vs Cash ETF CMF (`BeES`/`SPDR`)** | **Real-Money Sponsorship**: Cash-verified ETF `CMF(20) >= +0.10` exceeding Constituent Equal-Weight `CMF(20)` and Spot `CMF(20)`. | **The ETF Mirage**: Spot Index rallies (`1M Ret >= +2%`) via futures/index management while real-money Cash ETF (`BeES`/`SPDR`) shows negative `CMF(20) <= -0.10`. |
| **3. 60D Intraday Smart-Money Clock (1H)** | **Closing VWAP Accumulation**: Final active window (`>= 14:15 IST` or `>= 15:00 ET`, excluding flat zero-volume terminal quote markers) exhibits positive cumulative & compounded return, `>55%` win rate, and Afternoon VIX Crush (`<0%` hourly VIX change). | **Opening Hour Retail Trap**: First hour (`09:15 IST` or `09:30 ET`) shows negative cumulative return and `<48%` win rate as overnight gaps (`overnight_gap`) are sold into. |
| **4. Hurst Exponent ($H_{60}$, $SE$, $R/S$) vs 1Y BBW %ile** | **Coiled Trend Breakout**: `H >= 0.55` (persistent memory, confirmed by `hurst_usable` and `hurst_rs_60d`) OR `1Y BBW %ile <= 20%` paired with positive `CMF(20)`. | **Mean-Reverting Chop Trap**: `H <= 0.45` (anti-persistent whipsaw regime where breakout buyers get faded; `0.45 < H < 0.55` is random-walk noise). |
| **5. FFT Spectral Harmonic Wave (`[25D–75D]`)** | **Harmonic Trough Inflection**: Composite detrended wave at cyclical trough with upward 25-day slope (reliable when `fft_reliable = true`, i.e., `harmonic_variance_share_pct >= 15%` and `vol_regime_ratio_20v60 <= 1.35`). | **Harmonic Crest Exhaustion**: Composite detrended wave at cyclical crest (`+0 to +5 trading days` to peak) while price tests upper Volume Profile resistance. |
| **6. 120D Range-Distributed Volume Profile (`POC`, `VAL`, `VAH`, `LVN`)** | **Value Area Breakout / POC Reclaim**: Price holding above `POC` and `VAH` (contiguous 70% volume zone around `POC`) with expanding `CMF(20)`. | **Low-Volume Air Pocket (`LVN`)**: Price rallies into a Low-Volume Node (`lvn_air_pockets`) or below `POC` on negative `CMF(20)` — high rejection risk back toward `VAL`. |

#### Required Deliverables in `<workspace>\reports\`:
1. **Visual Verification Gate (Mandatory)**:
   - Call `view` on `<workspace>\reports\intraday_smart_money_clock_<dd-mm-yy>.png` and `<workspace>\reports\social_media_quant_infographic_<dd-mm-yy>.png`.
   - Confirm zero overlapping callout labels, clean axis margins, and legible annotations. If any scatter labels collide, adjust label offsets and re-render before finishing.
2. **Institutional Multi-Desk Research Report (`<workspace>\reports\Market_Quant_Deep_Dive_<dd-mm-yy>.md`)**:
   - Executive Summary & Ranked High-Conviction Anomalies (with `[0.00–1.00]` conviction scores)
   - Desk 1: Order Flow, RSI vs CMF Quadrant & Spot vs ETF Divergence
   - Desk 2: 60-Day Intraday Smart-Money Clock, Afternoon VIX Crush & 120D Volume Profile Geometry
   - Desk 3: Fractal Hurst Regimes, Bollinger Bandwidth Squeeze Coils & FFT Harmonic Cycle Projection
   - Desk 4: Cross-Asset Macro Correlations & Live Catalyst Corroboration
   - Desk 5: Skeptical Risk Officer Audit, Caveats & Exact Invalidation Levels
   - Multi-Model Fleet Audit Table (Desk, Agent Name, Model ID, Model Family, Key Finding)
3. **Interactive Clawpilot Dashboard (`<workspace>\reports\market_quant_dashboard_<dd-mm-yy>.html`)**:
   - Must include the mandatory Clawpilot theme detection `<script>` and `--cp-*` CSS variables (light & dark mode).
4. **Social Media Quant Pack (`<workspace>\reports\Social_Media_Quant_Posts_<dd-mm-yy>.md`)**:
   - Ready-to-post X/Twitter 5-tweet thread and LinkedIn post highlighting the 4 non-standard quant signals with exact audited numbers.

**Step 4 is complete when**: all deliverables exist in `<workspace>\reports\`, all PNG charts have been visually verified via `view`, and `<workspace>\README.md` indexes the workspace artifacts.
