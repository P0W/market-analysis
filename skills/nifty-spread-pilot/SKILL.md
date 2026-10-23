---
name: nifty-spread-pilot
description: 'Automated NIFTY 50 Options Spread Pilot (Bear Call, Bull Put, Bull Call, Bear Put) via Kite MCP + Discounted Black-76 Greeks. Enforces Zerodha token pre-flight login checks, finds the highest-edge spread with an immediate NO POSITION gate, evaluates live spreads with exact itemized Zerodha+NSE statutory charges, solves non-linearly for F* OCO triggers across No-Loss Profit-Lock and Loss-Minimization regimes, designs peak-margin-safe sequenced Two-Leg OCO GTT orders, and flags immediate CLOSE ALL triggers. Triggers -- "spread pilot", "bear call spread", "bull put spread", "nifty option position", "analyze greeks", "what spread to take", "trail my option", "close spread", "option spread".'
---

# NIFTY Spread Pilot Skill (`nifty-spread-pilot`)

End-to-end tactical options spread analyzer and position guardian for NIFTY 50 on Zerodha Kite MCP, backed by the zero-dependency Discounted Black-76 Greeks, Dynamic Charges & Non-Linear OCO Root-Finder in `spread_engine.py`.

---

## Core Operating Rules (Non-Negotiable)

1. **Step 0 — Zerodha Authentication Pre-Flight Gate (`AUTH_REQUIRED`)**:
   - Before running any position audit, quote fetch, or GTT action, probe live Kite connectivity (`kite-get_margins` or `kite-get_positions`).
   - If any Kite MCP call returns a session/token error (`TokenException`, `Invalid api_key or access_token`, `403`, or logged-out state):
     1. Immediately call **`kite-login`**.
     2. Present the returned authorization URL as a clickable Markdown link (`[Authorize Zerodha Kite Session](...)`) and state **`🔐 AUTH_REQUIRED — Zerodha token expired. Please click the link to log in, then say "done" to resume.`**
     3. **Halt** all calculations and order/GTT proposals until login is confirmed and fresh quotes/positions are fetched. Never use stale or cached prices.

2. **Zero Assumed Numbers & Discounted Put-Call Parity**:
   - Always pull live positions (`kite-get_positions`), active orders/GTTs (`kite-get_orders`, `kite-get_gtts`), free margin (`kite-get_margins`), and live option quotes (`kite-get_quotes`, including best bid/ask depth when available) from Kite MCP first.
   - Compute the true implied futures price $F$ from the nearest ATM Call/Put pair via discounted put-call parity:
     $$F = K + e^{rT}(C - P)$$
     using `mode="parity"` in `spread_engine.py`.

3. **Exact Itemized Zerodha + NSE Statutory Charges**:
   - Every target, breakeven, and P&L scenario **must** deduct round-trip Zerodha + NSE statutory charges computed by `compute_zerodha_nse_charges`:
     - Brokerage (`₹20 × executed orders`), STT (`0.10%` on sell premium), NSE Exchange Turnover (`0.03503%`), SEBI/IPFT (`0.0006%`), Stamp Duty (`0.003%` on buy premium), and `18%` GST on `(Brokerage + Exchange Txn + SEBI/IPFT)`.
   - Never quote gross profit alone when the user asks for a rupee target or a no-loss floor.

4. **Immediate `NO POSITION` / `🚨 CLOSE ALL` Priority Gate**:
   - **Pre-Trade (`NO_POSITION_RECOMMENDED`)**: If no candidate spread satisfies all edge gates (`credit_to_width_pct >= 18%`, `net_theta_pts_day >= +1.5`, `otm_cushion_pts >= 40`, and `0.16 <= |short_delta| <= 0.42`), immediately declare **`🚫 DO NOT ENTER A SPREAD NOW`** and explain why.
   - **In-Trade (`🚨 CLOSE_ALL_IMMEDIATELY`)**: Immediately recommend closing both legs (`BUY Short Leg FIRST` → `SELL Long Leg SECOND`) if any Priority-1 kill-switch fires:
     - Executable Net P&L (at bid/ask touch) already meets or exceeds the user's Net-After-Charges profit target,
     - Executable Net Loss breaches the maximum loss cap (`max_loss_net_rupees`),
     - Implied Forward breaches the short strike, Short $|\Delta| \ge 0.48$, or cushion drops inside the pre-strike Gamma danger zone while underwater,
     - Spot/Implied Forward breaches the structural invalidation level (e.g., 200-WMA / breakdown candle high), or
     - Current time is $\ge 15:15\text{ IST}$ on a same-day exit mandate.

5. **Three-Regime Non-Linear OCO GTT Framework (`NO_LOSS` vs `LOSS_MINIMIZATION`)**:
   - Option legs do **not** move linearly near the short strike. Always use `spread_engine.py` (`solve_forward_for_spread_value`) to solve non-linearly for the exact underlying forward levels $F^*_{\text{lower}}$ and $F^*_{\text{upper}}$ with Sticky-Delta IV stress bumps.
   - **Regime A1 — `NO_LOSS_PROFIT_LOCK_OCO` (Spread in Net Profit with Sufficient Cushion)**:
     - **Lower GTT Trigger (`Profit Target`)**: Solves for $F^*_{\text{lower}}$ where spread contracts to $E_{\text{target}} = \text{entry\_credit} - (\text{target\_net} + \text{charges})/Q$ (e.g., `~50%` of Max Net Profit).
     - **Upper GTT Trigger (`No-Loss Profit Lock`)**: Solves for $F^*_{\text{upper}}$ (with `+0.8%` stress IV bump) and adaptively selects limit buffers so that even under **worst-case limit fill (`short_upper_limit - long_upper_limit`)**, Net P&L after charges remains **$\ge ₹0$ (`zero_loss_floor_feasible: true`)**.
   - **Regime A2 — `PROFIT_LOCK_INFEASIBLE` (Slightly Green on LTP/Touch, Cushion Too Thin for Zero-Loss Stop)**:
     - When executable profit is positive (`exec_spread < E_zero`) but smaller than the GTT limit-slippage buffer (`~2.5–6.0 pts`), a resting GTT stop cannot mathematically guarantee zero loss on a fast spike.
     - Explicitly report **`⚠️ PROFIT_LOCK_INFEASIBLE`**, show the exact worst-case limit fill, and offer the user two honest choices: (a) close at market right now to bank the small net profit, or (b) arm a tight damage-cap OCO accepting a bounded small risk.
   - **Regime B — `LOSS_MINIMIZATION_OCO` (Spread Underwater Inside Max-Loss Cap)**:
     - When `exec_spread >= E_zero` (currently in net loss) but inside the max-loss cap (`E_cap`):
     - **Lower GTT Trigger (`Cost-Breakeven Scratch`)**: Targets $E_{\text{zero}} = \text{entry\_credit} - \text{charges}/Q$ so any favorable mean-reversion bounce exits near **`₹0` net loss** (never clamp an unreachable profit target to `1.0 pt`).
     - **Upper GTT Trigger (`Hard Damage Cap`)**: Places the stop at the nearer of the user's max-loss budget $E_{\text{cap}} = \text{entry\_credit} + (\text{max\_loss\_cap} - \text{charges})/Q$ and the pre-strike Gamma wall ($|\Delta_s| < 0.48$) with a `+4.0 pt` marketable limit buffer on the short leg so a fast gap/spike cannot turn a manageable loss into a max-width loss.

6. **Peak-Margin & Premature-Hedge-Exit Protection (Sequenced Exit & `H_min`)**:
   - **Manual / Market Exit Sequence**: Always **BUY back the Short leg FIRST**, and **SELL the Long hedge leg SECOND** so the account never suffers a naked short peak-margin penalty.
   - **Dual Two-Leg (OCO) GTT Sequence**:
     - Zerodha `two-leg` GTTs are independent single-instrument triggers, not atomic spread orders.
     - Always give the **Short leg Upper Stop-Loss Limit price a marketable buffer** (`+1.0 to +4.0 pts` above trigger) so fast adverse spikes fill immediately.
     - Offset the **Long hedge leg GTT triggers by `2.0 pts` wider** than the Short leg's model price at $F^*$ so the Short leg triggers **first** and never leaves an unhedged short option if price reverses.
     - Always display `h_min_after_short_stop_fill` ($H_{\min} = \max(0, L_{\text{short,stop}} - \text{entry\_credit} + (\text{charges} + P_{\text{floor}})/Q)$)—the exact minimum price the Long hedge must be sold at once `SHORT_FLAT_CONFIRMED` (`short qty == 0`) to preserve the protected floor.

7. **Order Confirmation Policy**:
   - Always present the exact strike, quantity, trigger/limit prices, OCO regime (`NO_LOSS_PROFIT_LOCK_OCO`, `PROFIT_LOCK_INFEASIBLE`, or `LOSS_MINIMIZATION_OCO`), and the 4-row Scenario Payoff Table (Normal Trigger Fill & Worst-Case Limit Fill for both Lower and Upper legs, in Gross and Net-After-Charges rupees), and obtain user approval before calling `kite-place_order`, `kite-place_gtt_order`, or `kite-modify_gtt_order`.

---

## Workflow 1: Live Position Audit, Greek Optimization & OCO Design

When the user asks *"check my NIFTY option position / what to do now / place no-loss or loss-minimization OCO"*:

1. **Pre-Flight Auth & Live State Fetch**:
   - Call `kite-get_positions`, `kite-get_orders`, `kite-get_gtts`, `kite-get_margins`, and `kite-get_quotes` for `NSE:NIFTY 50`, `NSE:INDIA VIX`, and the held option symbols (plus ATM CE/PE for implied forward parity). If logged out, trigger `kite-login` immediately (Rule 1).
2. **Run `spread_engine.py` in `evaluate` Mode**:
   ```powershell
   python "$HOME/.copilot/skills/nifty-spread-pilot/spread_engine.py" '{"mode":"evaluate","params":{"forward":22698.45,"t_days":31.05,"opt_type":"PE","short_strike":22400,"short_entry":353.70,"short_ltp":296.00,"long_strike":22200,"long_entry":281.55,"long_ltp":234.30,"lot_size":65,"target_net_rupees":2000}}'
   ```
3. **Present the 3-Part Tactical Dashboard**:
   - **Part A — Live Position & Net-After-Charges Table**: Entry, LTP, Executable Touch Spread, Gross P&L, Itemized Charges, Net P&L in hand, Max Net Profit, Max Net Loss, Terminal PoP %, and Net Breakeven.
   - **Part B — Discounted Black-76 1st & 2nd-Order Greeks & Hedge Burn Check**: Show `IV%`, `Delta`, `Gamma`, `Theta/day`, `Vega/1%`, `Vanna`, `Charm`, Daily $1\sigma$ move vs Theta-Gamma Breakeven move, and highlight if the Long hedge is burning `> 75%` of the Short leg's daily Theta on a far-dated expiry.
   - **Part C — OCO Regime Verdict & Sequenced GTT Table**:
     - State the exact verdict (`HOLD_WITH_NO_LOSS_OCO`, `HOLD_WITH_TIGHT_OCO_OR_BOOK_PROFIT`, `HOLD_WITH_LOSS_MINIMIZATION_OCO`, `ROLL_TO_NEAR_EXPIRY_OR_HOLD_WITH_OCO`, or `🚨 CLOSE_ALL_IMMEDIATELY`).
     - Present the Short Leg (`BUY`) and Long Leg (`SELL`) Two-Leg GTT triggers/limits, `h_min_after_short_stop_fill`, and the 4-row Scenario Payoff Table.

---

## Workflow 2: Pre-Trade Best Bear/Bull Spread Finder

When the user asks *"what is the best Bear/Bull spread right now?"*:

1. Verify Kite session (Rule 1), then fetch `NSE:NIFTY 50`, `NSE:INDIA VIX`, and 6–8 strikes around spot (`CE` for Bear Call, `PE` for Bull Put) via `kite-get_quotes`.
2. Run `spread_engine.py` with `"mode": "rank"` to pre-filter and score candidate `150/200/250-pt` spreads by Credit-to-Width %, Net Theta/day, OTM cushion, and Terminal PoP %.
3. If `verdict == "NO_POSITION_RECOMMENDED"`, tell the user immediately **not to take a trade** and why. Otherwise, present the #1 ranked spread vs. top alternatives with exact breakevens and max profit/loss after statutory charges.

---

## Workflow 3: Proactive Scheduled Monitoring & Fill-Confirmed State Machine (`manage_schedule`)

When the user wants proactive continuous monitoring while a spread or OCO GTT is active:
- Use `manage_schedule` (`action: "create"`, `interval: "5m"`) with prompt:
  `"Run nifty-spread-pilot check on my open NIFTY spread: verify Kite session, fetch live quotes, positions, orders, and GTTs, evaluate Greeks and OCO regime via spread_engine.py, check if the Short leg GTT has filled (SHORT_FLAT_CONFIRMED -> immediately trail or close the remaining Long leg at >= H_min), alert immediately if CLOSE ALL or trailing GTT ratchet is needed, and stop the schedule once both legs are flat (quantity == 0)."`
- As soon as both legs show `quantity == 0`, cancel any remaining orphan GTT (`kite-delete_gtt_order`) and stop the schedule via `manage_schedule` (`action: "stop"`).
