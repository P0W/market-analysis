# Market-Quant — Shareable GitHub Copilot CLI Extension & Skill

**Market-Quant** is a self-contained **GitHub Copilot CLI Plugin (Extension + Skill)** that combines a deterministic Python quantitative & microstructure engine (`market_quant_engine.py`) with **live ANSI-colored terminal scorecards, multi-agent progress bars, Quorum blackboard telemetry, and a 5-desk multi-model research workflow**.

---

## ✨ What You Get (Extension + Skill Hybrid)

1. **Live ANSI Terminal Scorecard (`market_quant_hud` & `market_quant_scan`)**:
   - Streams a color-coded institutional HUD directly into your Copilot CLI timeline via `session.log()`:
     - **Primary Index Regime**: Variogram Hurst Exponent ($H \pm SE$) + Classical Rescaled-Range ($R/S$), 1Y Bollinger Bandwidth squeeze percentile, Gated FFT Harmonic Cycle status, and 120-day contiguous 70% Volume Profile (`VAL ◄── POC ──► VAH` + `LVN` air pockets).
     - **Spot Index vs Cash-Verified ETF Flow Bars**: Visualizes `Nifty50 vs NiftyBees`, `BankNifty vs BankBees`, `NiftyIT vs ITBees`, `NiftyPharma vs PharmaBees` (or US `SP500 vs SPY`, `Nasdaq100 vs QQQ`) with `█/▓` order-flow bars and spread regime badges.
     - **60-Day 1-Hour Intraday Smart-Money Clock**: Contrasts Opening-Hour retail traps vs Closing-Window institutional VWAP accumulation and the Afternoon VIX Crush.
     - **Constituent Divergences**: Lists top Bull-Trap Distributions (`RSI >= 55, CMF <= -0.05`), Stealth Accumulations (`RSI < 55, CMF >= +0.10, Up/Down Vol >= 1.25x`), and True Institutional Breakouts.
2. **Real-Time Multi-Agent Fleet Progress Bar (`onSubagentStart` / `onSubagentStop`)**:
   - Automatically intercepts specialist sub-agent launches, injects the deterministic `quorum_grounding.json` SHA-256 contract (`SIGNAL_SPEC` + `cmf_invalid_symbols`) so agents never hallucinate numbers, and renders a live progress bar in the CLI timeline:
     `FLEET ██████░░░░ 3/5 │ ✔ D1:Micro  ✔ D2:Vol/FFT  ✔ D3:Macro  ⟳ D4:RedTeam  ○ D5:PM`
3. **Live Quorum Blackboard Telemetry**:
   - Listens to `quorum-debate_start`, `quorum-board_post`, and `quorum-tally_consensus` tool events and displays colored round/stance/vote updates in the terminal timeline.
4. **Deterministic Report Auditor (`market_quant_verify_report`)**:
   - Audits generated Markdown reports against `anomaly_summary.json` and `data_quality.json` to ensure zero-volume symbols (`IndiaVIX`, `USDINR`, `US10Y`, `DXY`) are never cited with valid CMF values and all ground-truth metrics match.
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
│   │           ├── ansi-hud.mjs                    # ANSI terminal scorecard & progress bar renderer
│   │           └── market_quant_engine.py          # Bundled self-contained Python quant engine
│   └── skills/
│       └── market-quant/
│           ├── SKILL.md                            # Multi-model orchestration skill instructions
│           └── market_quant_engine.py              # Python quant engine
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
