# Market Analysis — Quantitative Derivatives Risk & Market Diagnostics Toolkit

Deterministic Python quantitative engines, NIFTY index options risk and execution workflow tools, and GitHub Copilot CLI extensions/skills for Indian (NSE/NIFTY) and US equity markets.

---

## 📂 Repository Structure

```text
market-analysis/
├── skills/
│   └── nifty-spread-pilot/
│       ├── SKILL.md                # NIFTY 50 Options Spread Pilot MCP workflow specification
│       ├── spread_engine.py        # Pure-Python Discounted Black-76 Greeks, Statutory Charges & Non-Linear F* OCO Engine
│       └── test_spread_engine.py   # Analytical & finite-difference verification test suite
└── market-quant-plugin/
    ├── .github/plugin/             # Copilot CLI Plugin Marketplace manifest
    ├── plugin/
    │   ├── plugin.json             # Plugin manifest (extension + skill)
    │   ├── com.github.copilot/     # Live ANSI Terminal HUD & Multi-Agent Telemetry Extension
    │   └── skills/market-quant/    # Cross-Sectional Market Diagnostics Engine & Skill
    ├── extension.test.mjs          # Node.js unit test suite for ANSI HUD & extension
    └── README.md                   # Plugin documentation
```

---

## ⚡ 1. NIFTY Spread Pilot (`skills/nifty-spread-pilot`)

Zero-dependency Python options risk engine (`spread_engine.py`) and Kite MCP workflow skill for evaluating, ranking, and managing vertical index option spreads (`BEAR_CALL`, `BULL_PUT`, `BULL_CALL`, `BEAR_PUT`) on NIFTY 50:

- **Discounted Black-76 & Put-Call Parity**:
  - Recovers implied forward $F = K + e^{rT}(C - P)$ from ATM Call/Put pairs and computes analytical 1st-order (`Delta`, `Gamma`, `Theta/day`, `Vega/1%`) and 2nd-order (`Vanna`, `Charm`, `Vomma`) Greeks using a safeguarded Newton-Raphson + bisection IV solver (`< 0.15 ms` per evaluation), verified against central finite differences.
- **Itemized Zerodha + NSE Statutory Charges**:
  - Deducts exact round-trip brokerage, STT on sell turnover, NSE exchange turnover charges, SEBI/IPFT fees, stamp duty on buy turnover, and 18% GST from every target, breakeven, and scenario payoff calculation.
- **Non-Linear $F^*$ Root-Finder & Margin-Aware Two-Leg OCO GTT Exit Sequencing**:
  - Because broker `two-leg` GTTs are independent single-instrument triggers rather than atomic exchange spread orders, the engine sequences triggers and limit buffers so the **short leg is bought back before the long hedge leg is sold**, preventing naked-short peak-margin penalties.
  - `NO_LOSS_PROFIT_LOCK_OCO`: Solves via bisection (with sticky-delta IV stress bumps) for the underlying forward level $F^*$ where the model-implied worst-case limit fill (`short_upper_limit - long_upper_limit`) preserves $\ge ₹0$ net profit after statutory charges under continuous-market fill assumptions (subject to overnight/intraday gap risk beyond the limit buffer).
  - `PROFIT_LOCK_INFEASIBLE`: Flags thin profit cushions that cannot absorb GTT limit-order slippage buffers without risking a net loss.
  - `LOSS_MINIMIZATION_OCO`: When a spread is underwater inside its risk cap, sets the Lower GTT trigger to cost-breakeven scratch ($E_{\text{zero}}$) and the Upper GTT trigger to cap loss ahead of the short-strike Gamma wall ($|\Delta_s| < 0.48$).
  - `CLOSE_ALL_IMMEDIATELY`: Priority exit gate on executable touch target hit, loss-cap breach, short-strike Gamma wall ($|\Delta_s| \ge 0.48$), structural spot invalidation, or $\ge 15:15\text{ IST}$ intraday cutoff.

### Run Unit Tests
```powershell
python skills\nifty-spread-pilot\test_spread_engine.py -v
```

---

## 📊 2. Market-Quant Plugin (`market-quant-plugin`)

Copilot CLI Extension and Skill combining a deterministic Python market diagnostics engine (`market_quant_engine.py`) with a live ANSI terminal HUD (`ansi-hud.mjs`) and SHA-256 data-grounding verification (`market_quant_verify_report`):

- **Cross-Sectional Price/Volume & Spot-vs-ETF Flow Diagnostics**: Computes `CMF(20)`, `RSI(14)`, 20-day Up/Down volume ratios, and cash-ETF (`BeES`/`SPDR`) vs. spot-index flow spreads, enforcing non-zero volume data-quality gates (`cmf_invalid_symbols`) so zero-volume indices (`IndiaVIX`, `USDINR`, `US10Y`, `DXY`) are excluded from volume-weighted metrics.
- **Intraday Hourly Return/Volatility Profile & Volume Profile**: Aggregates 60-day 1-hour session return/volatility distributions (opening vs. mid-session vs. closing execution windows) and 120-day range-distributed volume profiles (`POC`, `VAL`, `VAH`, low-volume nodes).
- **Statistically Gated Regime Estimators**: Computes Variogram and Rescaled-Range ($R/S$) Hurst exponents (gated by standard-error z-scores), 1-year Bollinger Bandwidth percentiles, and exploratory detrended spectral periodograms (explicitly suppressed via `fft_reliable = false` when harmonic variance share falls below threshold).
- **Deterministic Grounding Audit**: Injects SHA-256 dataset hashes and machine-readable ground truth (`quorum_grounding.json`, `data_quality.json`) into multi-agent research runs and deterministically audits generated Markdown reports against the underlying CSV/JSON matrices.

### Run Extension Tests
```powershell
node --test market-quant-plugin\extension.test.mjs
```
