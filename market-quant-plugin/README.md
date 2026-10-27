# Market-Quant — GitHub Copilot CLI Extension & Quantitative Diagnostics Skill

**Market-Quant** is a self-contained **GitHub Copilot CLI Plugin (Extension + Skill)** that pairs a deterministic Python market diagnostics engine (`market_quant_engine.py`) with **ANSI-colored terminal scorecards, multi-agent progress telemetry, SHA-256 data-grounding contracts, and automated report verification**.

---

## ✨ Key Capabilities (Extension + Skill Hybrid)

1. **Live ANSI Terminal Scorecard (`market_quant_hud` & `market_quant_scan`)**:
   - Streams a color-coded terminal HUD directly into the Copilot CLI timeline via `session.log()`:
     - **Primary Index Regime Diagnostics**: Variogram Hurst Exponent ($H \pm SE$) + Classical Rescaled-Range ($R/S$), 1Y Bollinger Bandwidth percentile, variance-gated spectral periodogram status, and 120-day 70% Volume Profile (`VAL ◄── POC ──► VAH` + `LVN` low-volume nodes).
     - **Spot Index vs. Cash-ETF Flow Spreads**: Compares `Nifty50 vs NiftyBees`, `BankNifty vs BankBees`, `NiftyIT vs ITBees`, `NiftyPharma vs PharmaBees` (or US `SP500 vs SPY`, `Nasdaq100 vs QQQ`) using `█/▓` volume-flow bars and regime badges.
     - **60-Day 1-Hour Intraday Return & Volatility Profile**: Contrasts opening-hour return/win-rate distributions against closing-window VWAP activity and afternoon implied-volatility changes.
     - **Cross-Sectional Constituent Screening**: Lists price-momentum vs. volume-flow divergences (`RSI >= 55, CMF <= -0.05`), positive volume-flow accumulations (`RSI < 55, CMF >= +0.10, Up/Down Vol >= 1.25x`), and confirmed volume breakouts.
2. **Real-Time Multi-Agent Fleet Progress Bar (`onSubagentStart` / `onSubagentStop`)**:
   - Intercepts specialist sub-agent launches, injects the deterministic `quorum_grounding.json` SHA-256 contract (`SIGNAL_SPEC` + `cmf_invalid_symbols`) so sub-agents remain grounded in computed tables, and renders a live progress bar in the CLI timeline:
     `FLEET ██████░░░░ 3/5 │ ✔ D1:Micro  ✔ D2:Vol/FFT  ✔ D3:Macro  ⟳ D4:RedTeam  ○ D5:PM`
3. **Live Quorum Blackboard Telemetry**:
   - Listens to `quorum-debate_start`, `quorum-board_post`, and `quorum-tally_consensus` tool events and displays colored round/stance/vote updates in the terminal timeline.
4. **Deterministic Report Auditor (`market_quant_verify_report`)**:
   - Audits generated Markdown reports against `anomaly_summary.json` and `data_quality.json` to ensure zero-volume symbols (`IndiaVIX`, `USDINR`, `US10Y`, `DXY`) are never cited with volume-weighted `CMF` values and all cited metrics match computed outputs.
5. **Registered Dynamic Workflow (`market-quant-fleet`)**:
   - Orchestrates the 4-phase, 5-desk multi-agent research pipeline via `run_dynamic_workflow`.

---

## 📦 Package Layout

```text
market-quant-plugin/
├── .github/
│   └── plugin/
│       └── marketplace.json                        # Copilot CLI Plugin Marketplace manifest
├── plugin/
│   ├── plugin.json                                 # Plugin manifest (wires both extension + skill)
│   ├── com.github.copilot/
│   │   └── extensions/
│   │       └── market-quant/
│   │           ├── extension.mjs                   # Copilot SDK Extension (tools, hooks, workflow)
│   │           └── ansi-hud.mjs                    # ANSI terminal scorecard & progress bar renderer
│   └── skills/
│       └── market-quant/
│           ├── SKILL.md                            # Multi-model orchestration skill instructions
│           └── market_quant_engine.py              # Canonical Python quantitative diagnostics engine
├── extension.test.mjs                              # Node.js unit test suite
└── README.md
```

---

## 🚀 Installation (Native Copilot CLI Plugin Marketplace)

Install directly using the Copilot CLI plugin marketplace commands (from a local folder or Git repository):

```powershell
copilot plugin marketplace add ./market-quant-plugin
copilot plugin install market-quant@market-quant-marketplace
```

Then run `/restart` (or start a new Copilot CLI session) to activate the plugin's extension and skill.

---

## 🛠️ Registered Extension Tools

| Tool Name | Description |
|---|---|
| `market_quant_scan` | Runs `market_quant_engine.py` (`india`, `us`, `crypto`, `global`), streams live progress, renders the ANSI terminal HUD, and outputs 300-DPI PNGs + interactive HTML + JSON/CSV matrices. |
| `market_quant_hud` | Renders the colorful ANSI Institutional Quant Terminal Scorecard & Fleet Progress Bar for any existing workspace (`open_dashboard: true` opens the HTML studio). |
| `market_quant_verify_report` | Deterministically audits Markdown reports in `reports/` and `agents/results/` against `anomaly_summary.json` and `data_quality.json`. |
