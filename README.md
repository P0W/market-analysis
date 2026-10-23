# Market Analysis — Quantitative Microstructure & Options Spread Toolkit

A collection of deterministic quantitative engines, options derivatives risk tools, and GitHub Copilot CLI skills/plugins for Indian (NSE/NIFTY) and global equity markets.

---

## 📂 Repository Structure

```text
market-analysis/
├── skills/
│   └── nifty-spread-pilot/
│       ├── SKILL.md                # NIFTY 50 Options Spread Pilot skill definition
│       ├── spread_engine.py        # Pure-Python Discounted Black-76 Greeks, Dynamic Charges & Non-Linear F* OCO Engine
│       └── test_spread_engine.py   # Mathematical verification & regime unit test suite
└── market-quant-plugin/
    ├── .github/plugin/             # Copilot CLI Plugin Marketplace manifest
    ├── plugin/
    │   ├── plugin.json             # Plugin manifest (extension + skill)
    │   ├── com.github.copilot/     # Live ANSI Terminal HUD & Multi-Agent Fleet Extension
    │   └── skills/market-quant/    # Institutional Microstructure & Quantitative Engine Skill
    ├── extension.test.mjs          # Node.js unit test suite for ANSI HUD & extension
    └── README.md                   # Plugin documentation
```

---

## ⚡ 1. NIFTY Spread Pilot (`skills/nifty-spread-pilot`)

Zero-dependency Python options engine (`spread_engine.py`) and Copilot CLI skill for evaluating, ranking, and managing vertical options spreads (`BEAR_CALL`, `BULL_PUT`, `BULL_CALL`, `BEAR_PUT`) on NIFTY 50:

- **Discounted Black-76 & Put-Call Parity**:
  - Computes implied forward $F = K + e^{rT}(C - P)$ from ATM Call/Put pairs and exact 1st-order (`Delta`, `Gamma`, `Theta/day`, `Vega/1%`) & 2nd-order (`Vanna`, `Charm`, `Vomma`) Greeks with safeguarded Newton-Bisection IV solving (`< 0.15 ms` per evaluation).
- **Itemized Zerodha + NSE Statutory Charges**:
  - Deducts exact brokerage, STT on sell turnover, NSE exchange turnover charges, SEBI/IPFT fees, stamp duty, and 18% GST from every target and breakeven calculation.
- **Non-Linear $F^*$ Root-Finder & Three-Regime OCO State Machine**:
  - `NO_LOSS_PROFIT_LOCK_OCO`: Solves for the exact forward level $F^*$ where even the worst-case limit fill (`short_upper_limit - long_upper_limit`) preserves $\ge ₹0$ net profit after charges while targeting ~50% of Max Net Profit.
  - `PROFIT_LOCK_INFEASIBLE`: Detects thin profit cushions that cannot absorb GTT limit-order slippage buffers without going negative.
  - `LOSS_MINIMIZATION_OCO`: When a spread is underwater inside its risk cap, sets the Lower GTT trigger to Cost-Breakeven Scratch ($E_{\text{zero}}$, ₹0 net loss on a bounce) and the Upper GTT trigger to cap maximum loss before the short-strike Gamma wall.
  - `CLOSE_ALL_IMMEDIATELY`: Priority kill-switch on target hit, loss-cap breach, pre-strike Gamma wall ($|\Delta_s| \ge 0.48$), structural spot invalidation, or $\ge 15:15\text{ IST}$ intraday exit window.

### Run Unit Tests
```powershell
python skills\nifty-spread-pilot\test_spread_engine.py -v
```

---

## 📊 2. Market-Quant Plugin (`market-quant-plugin`)

Self-contained Copilot CLI Extension & Skill combining `market_quant_engine.py` (Chaikin Money Flow vs RSI divergences, Spot vs ETF order-flow spread, 60-day 1-hour Intraday Smart-Money Clock, Variogram/R-S Hurst exponent, Bollinger squeeze percentiles, gated FFT harmonic cycles, and 120-day Volume Profile POC/VAL/VAH) with a live ANSI terminal HUD (`ansi-hud.mjs`) and multi-desk research workflow.

### Run Extension Tests
```powershell
node --test market-quant-plugin\extension.test.mjs
```
