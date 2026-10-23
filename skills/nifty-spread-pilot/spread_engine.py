"""
NIFTY Spread Pilot — Pure-Python Discounted Black-76 Greeks, Dynamic Charges,
Non-Linear F* Root-Finder & Regime-Aware OCO Engine (No-Loss Lock vs Loss-Minimization).

Zero external dependencies (uses Python stdlib math.erf / math.erfc; sub-millisecond execution).

HOW THIS ENGINE WORKS (HIGH-LEVEL OVERVIEW):
1. Discounted Put-Call Parity (`implied_forward_from_pair`):
   Computes the true implied NIFTY futures price F from an ATM Call/Put pair:
       F = K + e^(r*T) * (Call - Put)
   Why: NIFTY European options price off the implied forward F (which includes futures cost-of-carry),
   not raw spot. Using raw spot misstates Put/Call IVs and Deltas.

2. Exact Zerodha + NSE Statutory Charges (`compute_zerodha_nse_charges`):
   Itemizes Brokerage (Rs 20/order), STT on sell premium, NSE exchange turnover charges,
   SEBI/IPFT fees, Stamp Duty on buy premium, and 18% GST.
   Why: A trade that looks +Rs 80 profitable on gross LTP is actually a net loss after ~Rs 117 charges.

3. Safeguarded Black-76 IV & 1st/2nd-Order Greeks (`implied_vol_with_status`, `compute_greeks`):
   Uses a fast Newton-Raphson + bisection hybrid with @lru_cache to solve Implied Volatility in <0.05 ms,
   checks no-arbitrage bounds (rejecting bad/illiquid ticks), and outputs 1st-order Greeks
   (Delta, Gamma, Theta/day, Vega/1%) plus 2nd-order Greeks (Vanna, Charm, Vomma).

4. Non-Linear Forward Root-Finder (`solve_forward_for_spread_value`):
   Instead of assuming option legs move linearly by Delta, solves via bisection for the exact
   underlying forward level F* where the Black-76 spread value equals the target spread:
       |P_short(F*, K_s, T, iv_s + bump) - P_long(F*, K_l, T, iv_l + bump)| = Target_Spread
   Why: Near the short strike, Gamma curves sharply; solving for F* gives exact individual leg GTT prices.

5. Three-Regime OCO State Machine (`evaluate_live_credit_spread`):
   - Regime A1 (`NO_LOSS_PROFIT_LOCK_OCO`): Position is in net profit AND has enough cushion to absorb
     worst-case GTT limit-order slippage while still locking >= Rs 0 net profit after charges.
   - Regime A2 (`PROFIT_LOCK_INFEASIBLE`): Position is slightly green on LTP, but too close to breakeven
     to fund GTT limit-order slippage buffers without risking a net loss on a spike.
   - Regime B (`LOSS_MINIMIZATION_OCO`): Position is underwater (in loss) but inside the max-loss cap.
     Sets the Lower GTT trigger to Cost-Breakeven Scratch (E_zero -> Rs 0 net loss on a bounce) and
     the Upper GTT trigger to cap maximum loss before the short-strike Gamma wall.
   - Priority Kill-Switch (`CLOSE_ALL_IMMEDIATELY`): Fires if target is already hit on executable touch,
     max-loss cap is breached, Short |Delta| >= 0.48, structural spot level breaks, or >= 15:15 IST intraday.
"""

from __future__ import annotations

import json
import math
import sys
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple


LOT_SIZE_DEFAULT = 65
TICK_SIZE_DEFAULT = 0.05
RISK_FREE_RATE_DEFAULT = 0.067  # 6.70% annualized India 91D T-bill / MIBOR proxy
LEGACY_FLAT_CHARGES_PER_LOT = 117.0

# Zerodha + NSE F&O Options statutory fee schedule (configurable rates)
BROKERAGE_PER_ORDER = 20.0
STT_SELL_RATE_DEFAULT = 0.0010       # 0.10% on sell premium (configurable to 0.0015 per circular)
NSE_TXN_RATE_DEFAULT = 0.0003503     # 0.03503% NSE options exchange turnover charge
SEBI_IPFT_RATE_DEFAULT = 0.0000060   # Rs 10/Cr SEBI + Rs 50/Cr IPFT = 0.0006%
STAMP_BUY_RATE_DEFAULT = 0.00003     # 0.003% on buy premium
GST_RATE_DEFAULT = 0.18              # 18% on (Brokerage + Exchange Txn + SEBI/IPFT)


def norm_cdf(x: float) -> float:
    """High-precision standard normal CDF using math.erfc for tail stability."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def round_to_tick(price: float, tick: float = TICK_SIZE_DEFAULT, direction: str = "nearest") -> float:
    """
    Rounds an option price to valid NSE tick size (0.05).
    direction: 'nearest' | 'down' (floor) | 'up' (ceil)
    """
    if tick <= 0:
        return round(price, 2)
    scaled = price / tick
    if direction == "down":
        steps = math.floor(scaled + 1e-9)
    elif direction == "up":
        steps = math.ceil(scaled - 1e-9)
    else:
        steps = round(scaled)
    return round(max(tick, steps * tick), 2)


def validate_opt_type(opt_type: str) -> str:
    clean = str(opt_type).strip().upper()
    if clean not in ("CE", "PE"):
        raise ValueError(f"Invalid option type '{opt_type}'. Must be 'CE' or 'PE'.")
    return clean


def implied_forward_from_pair(
    strike: float,
    call_price: float,
    put_price: float,
    t_days: float,
    r: float = RISK_FREE_RATE_DEFAULT,
    call_bid: Optional[float] = None,
    call_ask: Optional[float] = None,
    put_bid: Optional[float] = None,
    put_ask: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Discounted Put-Call Parity:
      C - P = e^{-rT} (F - K)  =>  F = K + e^{rT} (C - P)
    """
    T = max(0.0, float(t_days)) / 365.0
    df = math.exp(-r * T)
    inv_df = math.exp(r * T)
    f_mid = strike + inv_df * (call_price - put_price)
    result: Dict[str, Any] = {
        "forward": round(f_mid, 2),
        "discount_factor": round(df, 6),
        "strike_used": strike,
        "t_days": t_days,
    }
    if all(v is not None and v > 0 for v in (call_bid, call_ask, put_bid, put_ask)):
        f_min = strike + inv_df * (float(call_bid) - float(put_ask))
        f_max = strike + inv_df * (float(call_ask) - float(put_bid))
        result["forward_bid_ask_band"] = [round(f_min, 2), round(f_max, 2)]
    return result


def compute_zerodha_nse_charges(
    buy_turnover_rs: float,
    sell_turnover_rs: float,
    num_orders: int = 4,
    stt_sell_rate: float = STT_SELL_RATE_DEFAULT,
    nse_txn_rate: float = NSE_TXN_RATE_DEFAULT,
) -> Dict[str, float]:
    """
    Computes itemized Zerodha + NSE statutory F&O option charges for a round-trip spread.
    Scales accurately with actual premium turnover, quantity, and executed order count.
    """
    B = max(0.0, float(buy_turnover_rs))
    S = max(0.0, float(sell_turnover_rs))
    total_turnover = B + S

    brokerage = BROKERAGE_PER_ORDER * max(0, int(num_orders))
    stt = S * stt_sell_rate
    exchange_txn = total_turnover * nse_txn_rate
    sebi_ipft = total_turnover * SEBI_IPFT_RATE_DEFAULT
    stamp_duty = B * STAMP_BUY_RATE_DEFAULT
    gst = GST_RATE_DEFAULT * (brokerage + exchange_txn + sebi_ipft)
    total = brokerage + stt + exchange_txn + sebi_ipft + stamp_duty + gst

    return {
        "brokerage_rs": round(brokerage, 2),
        "stt_rs": round(stt, 2),
        "exchange_txn_rs": round(exchange_txn, 2),
        "sebi_ipft_rs": round(sebi_ipft, 2),
        "stamp_duty_rs": round(stamp_duty, 2),
        "gst_rs": round(gst, 2),
        "total_charges_rs": round(total, 2),
    }


def bs76_price(
    F: float,
    K: float,
    T: float,
    sigma: float,
    opt_type: str = "CE",
    r: float = RISK_FREE_RATE_DEFAULT,
) -> float:
    """
    Discounted Black-76 option price:
      Call = e^{-rT} [F N(d1) - K N(d2)]
      Put  = e^{-rT} [K N(-d2) - F N(-d1)]
    """
    kind = validate_opt_type(opt_type)
    if F <= 0 or K <= 0:
        raise ValueError("Forward F and Strike K must be positive.")
    if T <= 0:
        return max(0.0, F - K) if kind == "CE" else max(0.0, K - F)
    df = math.exp(-r * T)
    if sigma <= 0:
        return df * (max(0.0, F - K) if kind == "CE" else max(0.0, K - F))

    sqrt_T = math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    if kind == "CE":
        return df * (F * norm_cdf(d1) - K * norm_cdf(d2))
    return df * (K * norm_cdf(-d2) - F * norm_cdf(-d1))


@lru_cache(maxsize=4096)
def implied_vol_with_status(
    F: float,
    K: float,
    T: float,
    price: float,
    opt_type: str = "CE",
    r: float = RISK_FREE_RATE_DEFAULT,
) -> Tuple[float, bool, str]:
    """
    Safeguarded Newton-Raphson + Bisection hybrid IV solver with strict no-arbitrage bounds.
    Returns (iv_decimal, iv_reliable, status_msg).
    Cached via @lru_cache for sub-millisecond chain ranking.
    """
    kind = validate_opt_type(opt_type)
    if T <= 0 or F <= 0 or K <= 0 or price <= 0 or not math.isfinite(price):
        return 0.0, False, "NON_POSITIVE_TIME_OR_PRICE"

    df = math.exp(-r * T)
    intrinsic_disc = df * (max(0.0, F - K) if kind == "CE" else max(0.0, K - F))
    upper_bound = df * F if kind == "CE" else df * K

    if price >= upper_bound:
        return 0.0, False, "PRICE_EXCEEDS_UPPER_NO_ARB_BOUND"
    if price < intrinsic_disc - TICK_SIZE_DEFAULT:
        return 0.0, False, "PRICE_BELOW_DISCOUNTED_INTRINSIC"
    if price <= intrinsic_disc + TICK_SIZE_DEFAULT:
        return 0.01, False, "AT_OR_NEAR_INTRINSIC_LOW_VEGA"

    low, high = 0.005, 5.0
    p_low = bs76_price(F, K, T, low, kind, r)
    p_high = bs76_price(F, K, T, high, kind, r)
    if price <= p_low:
        return low, False, "BELOW_MIN_VOL_BOUND"
    if price >= p_high:
        return high, False, "ABOVE_MAX_VOL_BOUND"

    # Brenner-Subrahmanyam seed clamped near ATM, else log-moneyness heuristic
    sqrt_T = math.sqrt(T)
    bs_seed = math.sqrt(2.0 * math.pi / T) * (price / (df * F))
    sigma = max(0.05, min(1.5, bs_seed))

    for _ in range(28):
        p_mid = bs76_price(F, K, T, sigma, kind, r)
        diff = p_mid - price
        if abs(diff) < 1e-6:
            return sigma, True, "CONVERGED"
        if diff > 0:
            high = sigma
        else:
            low = sigma

        d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / (sigma * sqrt_T)
        vega_raw = df * F * norm_pdf(d1) * sqrt_T
        if vega_raw > 1e-5:
            cand = sigma - diff / vega_raw
            if low < cand < high:
                sigma = cand
                continue
        sigma = 0.5 * (low + high)
        if (high - low) < 1e-7:
            break

    return sigma, True, "CONVERGED"


def implied_vol(
    F: float,
    K: float,
    T: float,
    price: float,
    opt_type: str = "CE",
    r: float = RISK_FREE_RATE_DEFAULT,
) -> float:
    iv, _, _ = implied_vol_with_status(F, K, T, price, opt_type, r)
    return max(0.01, iv)


def compute_greeks(
    F: float,
    K: float,
    T_days: float,
    price: float,
    opt_type: str = "CE",
    r: float = RISK_FREE_RATE_DEFAULT,
) -> Dict[str, Any]:
    """
    Computes discounted Black-76 1st-order and 2nd-order Greeks:
      Delta, Gamma, Theta (calendar day), Vega (per 1% IV),
      Vanna (dDelta / dIV per 1% IV), Charm (-dDelta / dT per day), Vomma (dVega / dIV per 1% IV).
    """
    kind = validate_opt_type(opt_type)
    if T_days <= 0:
        intrinsic = max(0.0, F - K) if kind == "CE" else max(0.0, K - F)
        in_money = (F > K) if kind == "CE" else (F < K)
        return {
            "strike": K,
            "type": kind,
            "ltp": round(price, 2),
            "iv_pct": 0.0,
            "iv_reliable": False,
            "iv_status": "EXPIRED",
            "delta": (1.0 if kind == "CE" else -1.0) if in_money else 0.0,
            "gamma": 0.0,
            "theta_pts_day": 0.0,
            "vega_pts_1pct": 0.0,
            "vanna_per_1pct_iv": 0.0,
            "charm_delta_per_day": 0.0,
            "vomma_pts_1pct2": 0.0,
            "intrinsic_pts": round(intrinsic, 2),
        }

    T = float(T_days) / 365.0
    df = math.exp(-r * T)
    iv, iv_ok, iv_status = implied_vol_with_status(F, K, T, price, kind, r)
    sigma = max(iv, 0.01)
    sqrt_T = math.sqrt(T)

    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    pdf_d1 = norm_pdf(d1)

    eta = 1.0 if kind == "CE" else -1.0
    delta = eta * df * norm_cdf(eta * d1)
    gamma = df * pdf_d1 / (F * sigma * sqrt_T)
    vega_raw = df * F * pdf_d1 * sqrt_T
    vega_1pct = vega_raw / 100.0

    # Discounted Black-76 calendar theta (annualized -> divided by 365)
    model_price = bs76_price(F, K, T, sigma, kind, r)
    theta_annual = r * model_price - (df * F * pdf_d1 * sigma) / (2.0 * sqrt_T)
    theta_day = theta_annual / 365.0

    # Second-order Greeks
    vanna_1pct = -(df * pdf_d1 * d2 / sigma) / 100.0
    vomma_1pct2 = (vega_raw * d1 * d2 / sigma) / 10000.0
    charm_annual = r * delta + df * pdf_d1 * d2 / (2.0 * T)
    charm_day = charm_annual / 365.0

    return {
        "strike": K,
        "type": kind,
        "ltp": round(price, 2),
        "iv_pct": round(sigma * 100.0, 2),
        "iv_reliable": iv_ok,
        "iv_status": iv_status,
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "theta_pts_day": round(theta_day, 2),
        "vega_pts_1pct": round(vega_1pct, 2),
        "vanna_per_1pct_iv": round(vanna_1pct, 4),
        "charm_delta_per_day": round(charm_day, 4),
        "vomma_pts_1pct2": round(vomma_1pct2, 4),
    }


def detect_vertical_strategy(opt_type: str, short_strike: float, long_strike: float) -> Dict[str, Any]:
    """
    Classifies all 4 vertical option spreads:
      - BEAR_CALL (Credit): CE, short_strike < long_strike, favorable move = DOWN
      - BULL_PUT  (Credit): PE, short_strike > long_strike, favorable move = UP
      - BULL_CALL (Debit):  CE, long_strike < short_strike, favorable move = UP
      - BEAR_PUT  (Debit):  PE, long_strike > short_strike, favorable move = DOWN
    """
    kind = validate_opt_type(opt_type)
    if abs(short_strike - long_strike) < 1e-6:
        raise ValueError("short_strike and long_strike must be distinct.")

    if kind == "CE":
        if short_strike < long_strike:
            return {
                "strategy_code": "BEAR_CALL",
                "spread_style": "CREDIT",
                "favorable_direction": "DOWN",
                "adverse_direction": "UP",
            }
        return {
            "strategy_code": "BULL_CALL",
            "spread_style": "DEBIT",
            "favorable_direction": "UP",
            "adverse_direction": "DOWN",
        }
    else:
        if short_strike > long_strike:
            return {
                "strategy_code": "BULL_PUT",
                "spread_style": "CREDIT",
                "favorable_direction": "UP",
                "adverse_direction": "DOWN",
            }
        return {
            "strategy_code": "BEAR_PUT",
            "spread_style": "DEBIT",
            "favorable_direction": "DOWN",
            "adverse_direction": "UP",
        }


def solve_forward_for_spread_value(
    target_spread_pts: float,
    forward_now: float,
    short_strike: float,
    long_strike: float,
    T: float,
    iv_short: float,
    iv_long: float,
    opt_type: str,
    r: float = RISK_FREE_RATE_DEFAULT,
    stress_iv_bump: float = 0.0,
) -> Optional[Dict[str, float]]:
    """
    Solves non-linearly for F* such that:
      |P_short(F*, Ks, T, iv_s + bump) - P_long(F*, Kl, T, iv_l + bump)| == target_spread_pts
    Respects full Black-76 Gamma convexity and inter-strike IV skew.
    Returns None if target_spread_pts is outside (0, width * e^{-rT}).
    """
    kind = validate_opt_type(opt_type)
    width = abs(long_strike - short_strike)
    df = math.exp(-r * T)
    max_theoretical = width * df

    if target_spread_pts <= 0.15 or target_spread_pts >= max_theoretical - 0.15:
        return None

    sig_s = max(0.01, min(3.0, iv_short + stress_iv_bump))
    sig_l = max(0.01, min(3.0, iv_long + stress_iv_bump))

    def spread_abs(f_val: float) -> float:
        ps = bs76_price(f_val, short_strike, T, sig_s, kind, r)
        pl = bs76_price(f_val, long_strike, T, sig_l, kind, r)
        return abs(ps - pl)

    f_low = max(1000.0, forward_now * 0.65)
    f_high = forward_now * 1.45
    s_low = spread_abs(f_low)
    s_high = spread_abs(f_high)

    # For CE verticals, spread_abs increases with F; for PE verticals, spread_abs decreases with F
    if kind == "CE":
        if not (s_low <= target_spread_pts <= s_high):
            return None
        lo, hi = f_low, f_high
        for _ in range(45):
            mid = 0.5 * (lo + hi)
            if spread_abs(mid) < target_spread_pts:
                lo = mid
            else:
                hi = mid
        f_star = 0.5 * (lo + hi)
    else:
        if not (s_high <= target_spread_pts <= s_low):
            return None
        lo, hi = f_low, f_high
        for _ in range(45):
            mid = 0.5 * (lo + hi)
            if spread_abs(mid) > target_spread_pts:
                lo = mid
            else:
                hi = mid
        f_star = 0.5 * (lo + hi)

    p_short_star = bs76_price(f_star, short_strike, T, sig_s, kind, r)
    p_long_star = bs76_price(f_star, long_strike, T, sig_l, kind, r)
    return {
        "f_star": round(f_star, 2),
        "short_model_price": round(p_short_star, 2),
        "long_model_price": round(p_long_star, 2),
        "model_spread": round(abs(p_short_star - p_long_star), 2),
    }


def evaluate_live_credit_spread(
    forward: float,
    t_days: float,
    opt_type: str,
    short_strike: float,
    short_entry: float,
    short_ltp: float,
    long_strike: float,
    long_entry: float,
    long_ltp: float,
    lot_size: int = LOT_SIZE_DEFAULT,
    target_net_rupees: float = 2000.0,
    max_loss_net_rupees: Optional[float] = None,
    short_bid: Optional[float] = None,
    short_ask: Optional[float] = None,
    long_bid: Optional[float] = None,
    long_ask: Optional[float] = None,
    structural_spot_level: Optional[float] = None,
    spot_price: Optional[float] = None,
    same_day_exit_mandate: bool = False,
    current_ist_hour_float: Optional[float] = None,
    r: float = RISK_FREE_RATE_DEFAULT,
    charges_override_rs: Optional[float] = None,
    num_orders: int = 4,
    locked_profit_floor_rs: float = 0.0,
) -> Dict[str, Any]:
    """
    Holistic evaluation of a live NIFTY vertical spread (Credit or Debit).
    Implements:
      - Exact discounted Black-76 1st & 2nd order Greeks
      - Dynamic Zerodha + NSE turnover charges (with optional override)
      - Non-linear F* root solver for OCO triggers (no linear delta_ratio artifacts)
      - Strict 3-Regime OCO classification:
          * Regime A1: NO_LOSS_PROFIT_LOCK_OCO (Profitable & worst-case limit fill >= Rs 0 net)
          * Regime A2: PROFIT_LOCK_INFEASIBLE (Green on LTP/touch, but cushion cannot absorb limit buffers + charges)
          * Regime B:  LOSS_MINIMIZATION_OCO (Underwater inside risk cap -> Scratch Breakeven Lower Trigger + Hard Damage-Cap Upper Trigger)
          * Kill-Switch: CLOSE_ALL_IMMEDIATELY (Target achieved, Max-loss breached, Pre-strike Gamma wall breached, Structural level breached, or >= 15:15 IST same-day mandate)
    """
    kind = validate_opt_type(opt_type)
    strat = detect_vertical_strategy(kind, short_strike, long_strike)
    is_credit = strat["spread_style"] == "CREDIT"
    Q = int(lot_size)
    if Q <= 0:
        raise ValueError("lot_size (quantity) must be positive.")

    T_years = max(float(t_days), 0.0) / 365.0
    df = math.exp(-r * T_years) if T_years > 0 else 1.0

    g_short = compute_greeks(forward, short_strike, t_days, short_ltp, kind, r)
    g_long = compute_greeks(forward, long_strike, t_days, long_ltp, kind, r)

    width = abs(long_strike - short_strike)

    # Executable touch prices (conservative ask for buying back short, bid for selling long)
    exec_short_buy = float(short_ask) if (short_ask is not None and short_ask > 0) else float(short_ltp)
    exec_long_sell = float(long_bid) if (long_bid is not None and long_bid > 0) else float(long_ltp)

    # Dynamic statutory charges on entry + current exit turnover
    buy_turnover = (long_entry + exec_short_buy) * Q
    sell_turnover = (short_entry + exec_long_sell) * Q
    charges_breakdown = compute_zerodha_nse_charges(buy_turnover, sell_turnover, num_orders=num_orders)
    charges_rs = float(charges_override_rs) if charges_override_rs is not None else charges_breakdown["total_charges_rs"]

    # Signed proceeds: E = short_entry - long_entry, S_ltp = short_ltp - long_ltp, S_exec = exec_short_buy - exec_long_sell
    E_signed = round(short_entry - long_entry, 2)
    S_ltp_signed = round(short_ltp - long_ltp, 2)
    S_exec_signed = round(exec_short_buy - exec_long_sell, 2)

    captured_pts_ltp = round(E_signed - S_ltp_signed, 2)
    captured_pts_exec = round(E_signed - S_exec_signed, 2)

    gross_pnl_rs = round(captured_pts_ltp * Q, 2)
    net_pnl_rs = round(gross_pnl_rs - charges_rs, 2)
    exec_net_pnl_rs = round(captured_pts_exec * Q - charges_rs, 2)

    if is_credit:
        entry_credit = E_signed
        live_spread = S_ltp_signed
        exec_spread = S_exec_signed
        max_profit_net = round(entry_credit * Q - charges_rs, 2)
        max_loss_net = round((width - entry_credit) * Q + charges_rs, 2)
        breakeven_expiry = (
            round(short_strike + entry_credit - charges_rs / Q, 2)
            if kind == "CE"
            else round(short_strike - entry_credit + charges_rs / Q, 2)
        )
    else:
        entry_debit = round(long_entry - short_entry, 2)
        entry_credit = -entry_debit
        live_spread = round(long_ltp - short_ltp, 2)
        exec_spread = round(exec_long_sell - exec_short_buy, 2)
        max_profit_net = round((width - entry_debit) * Q - charges_rs, 2)
        max_loss_net = round(entry_debit * Q + charges_rs, 2)
        breakeven_expiry = (
            round(long_strike + entry_debit + charges_rs / Q, 2)
            if kind == "CE"
            else round(long_strike - entry_debit - charges_rs / Q, 2)
        )

    # Portfolio Greeks (Short = -1, Long = +1)
    net_delta = round(-g_short["delta"] + g_long["delta"], 4)
    net_gamma = round(-g_short["gamma"] + g_long["gamma"], 6)
    net_theta_pts = round(-g_short["theta_pts_day"] + g_long["theta_pts_day"], 2)
    net_vega_pts = round(-g_short["vega_pts_1pct"] + g_long["vega_pts_1pct"], 2)
    net_vanna = round(-g_short["vanna_per_1pct_iv"] + g_long["vanna_per_1pct_iv"], 4)
    net_charm = round(-g_short["charm_delta_per_day"] + g_long["charm_delta_per_day"], 4)

    short_theta_abs = abs(g_short["theta_pts_day"])
    long_theta_abs = abs(g_long["theta_pts_day"])
    hedge_theta_burn_ratio = round((long_theta_abs / short_theta_abs) * 100.0, 1) if short_theta_abs > 0 else 0.0

    # Daily Gamma-Theta breakeven move vs 1-sigma daily move
    iv_short_dec = max(0.01, g_short["iv_pct"] / 100.0)
    iv_long_dec = max(0.01, g_long["iv_pct"] / 100.0)
    daily_1sigma_pts = round(forward * iv_short_dec / math.sqrt(365.0), 1)
    theta_gamma_be_pts = (
        round(math.sqrt(2.0 * abs(net_theta_pts) / max(abs(net_gamma), 1e-8)), 1)
        if net_theta_pts > 0 and abs(net_gamma) > 1e-8
        else 0.0
    )

    # Risk-neutral terminal PoP at net-after-charges breakeven
    if T_years > 0 and breakeven_expiry > 0:
        d1_be = (math.log(forward / breakeven_expiry) + 0.5 * iv_short_dec**2 * T_years) / (
            iv_short_dec * math.sqrt(T_years)
        )
        d2_be = d1_be - iv_short_dec * math.sqrt(T_years)
        pop_terminal_pct = round(
            (norm_cdf(-d2_be) if strat["favorable_direction"] == "DOWN" else norm_cdf(d2_be)) * 100.0, 1
        )
    else:
        pop_terminal_pct = 0.0

    # Target validation (never clamp an unreachable target into 1.0 pt!)
    target_reachable = target_net_rupees <= max_profit_net
    effective_target_net_rs = (
        float(target_net_rupees) if target_reachable else round(0.50 * max(0.0, max_profit_net), 2)
    )

    reasons: List[str] = []
    if not target_reachable:
        reasons.append(
            f"Requested target (Rs {target_net_rupees:.0f} net) exceeds Max Possible Net Profit (Rs {max_profit_net:.0f}); "
            f"auto-calibrated OCO target to 50% of Max Net Profit (Rs {effective_target_net_rs:.0f} net)."
        )

    # Exact Spread Thresholds for Credit Spreads (and Debit equivalents)
    # For Credit Spread: Net = (entry_credit - exit_spread) * Q - charges_rs
    default_loss_cap_rs = (
        float(max_loss_net_rupees)
        if max_loss_net_rupees is not None
        else round(min(max_loss_net, max(1500.0, 0.35 * max_loss_net)), 2)
    )

    if is_credit:
        E_zero = round(entry_credit - charges_rs / Q, 2)
        E_lock = round(entry_credit - (max(0.0, locked_profit_floor_rs) + charges_rs) / Q, 2)
        E_target = round(entry_credit - (effective_target_net_rs + charges_rs) / Q, 2)
        E_cap = round(entry_credit + (default_loss_cap_rs - charges_rs) / Q, 2)
    else:
        # For Debit Spread: Net = (exit_spread - entry_debit) * Q - charges_rs
        entry_debit = round(long_entry - short_entry, 2)
        E_zero = round(entry_debit + charges_rs / Q, 2)
        E_lock = round(entry_debit + (max(0.0, locked_profit_floor_rs) + charges_rs) / Q, 2)
        E_target = round(entry_debit + (effective_target_net_rs + charges_rs) / Q, 2)
        E_cap = round(max(0.5, entry_debit - (default_loss_cap_rs - charges_rs) / Q), 2)

    # Check Kill-Switches First (Priority 1)
    kill_switch = False
    # 1. Target already achieved on executable prices
    if target_reachable and exec_net_pnl_rs >= target_net_rupees:
        kill_switch = True
        reasons.append(
            f"TARGET ACHIEVED: Executable Net P&L (Rs {exec_net_pnl_rs:.0f}) >= Target (Rs {target_net_rupees:.0f} net after Rs {charges_rs:.0f} charges). Close both legs now!"
        )

    # 2. Max loss budget breached
    if exec_net_pnl_rs <= -abs(default_loss_cap_rs):
        kill_switch = True
        reasons.append(
            f"LOSS CAP BREACHED: Executable Net P&L (Rs {exec_net_pnl_rs:.0f}) breached risk cap (-Rs {abs(default_loss_cap_rs):.0f} net). Close immediately to prevent deeper loss!"
        )

    # 3. Pre-strike Gamma wall / Short strike breach (for Credit Spreads)
    if is_credit:
        adverse_cushion = (short_strike - forward) if kind == "CE" else (forward - short_strike)
        gamma_wall_pts = max(15.0, round(0.22 * daily_1sigma_pts, 1))
        if adverse_cushion <= 0 or abs(g_short["delta"]) >= 0.48:
            kill_switch = True
            reasons.append(
                f"GAMMA WALL / STRIKE BREACH: Forward ({forward:.1f}) has breached/reached short strike ({short_strike:.0f}) "
                f"with Short |Delta| = {abs(g_short['delta']):.2f} (>= 0.48 limit). Exit immediately before Gamma accelerates loss!"
            )
        elif adverse_cushion <= gamma_wall_pts and exec_net_pnl_rs < 0:
            kill_switch = True
            reasons.append(
                f"PRE-STRIKE GAMMA DANGER ZONE: Cushion ({adverse_cushion:.1f} pts) <= Gamma wall ({gamma_wall_pts:.1f} pts) while underwater."
            )

    # 4. Explicit structural spot invalidation level
    ref_spot = float(spot_price) if spot_price is not None else forward
    if structural_spot_level is not None:
        if strat["adverse_direction"] == "UP" and ref_spot >= structural_spot_level:
            kill_switch = True
            reasons.append(
                f"STRUCTURAL LEVEL BREACHED: Spot/Ref ({ref_spot:.1f}) >= invalidation level ({structural_spot_level:.1f})."
            )
        elif strat["adverse_direction"] == "DOWN" and ref_spot <= structural_spot_level:
            kill_switch = True
            reasons.append(
                f"STRUCTURAL LEVEL BREACHED: Spot/Ref ({ref_spot:.1f}) <= invalidation level ({structural_spot_level:.1f})."
            )

    # 5. Same-day exit clock mandate (>= 15:15 IST)
    if same_day_exit_mandate and current_ist_hour_float is not None and current_ist_hour_float >= 15.25:
        kill_switch = True
        reasons.append("MANDATORY INTRADAY EXIT WINDOW (>= 15:15 IST): Close both legs before 15:30 close.")

    # Solve non-linear OCO levels depending on Zone (Profitable vs Underwater)
    oco_regime = "CLOSE_ALL_IMMEDIATELY" if kill_switch else "UNCLASSIFIED"
    floor_feasible = False
    sequenced_gtt_plan: Dict[str, Any] = {}

    if g_short["iv_reliable"] and g_long["iv_reliable"] and T_years > 0:
        if is_credit:
            in_profit_on_touch = exec_spread < E_zero

            # Solve Lower Trigger (Profit Target in Zone A, or Scratch Breakeven E_zero in Zone B)
            desired_favorable_spread = E_target if in_profit_on_touch else E_zero
            fav_sol = solve_forward_for_spread_value(
                desired_favorable_spread,
                forward,
                short_strike,
                long_strike,
                T_years,
                iv_short_dec,
                iv_long_dec,
                kind,
                r,
                stress_iv_bump=-0.005,  # mild IV relaxation on favorable rally/drop
            )
            if fav_sol is not None and fav_sol["short_model_price"] < short_ltp - 1.0:
                short_lower_trig = round_to_tick(fav_sol["short_model_price"], direction="up")
                short_lower_lim = round_to_tick(short_lower_trig + 1.5, direction="up")
                long_lower_trig = round_to_tick(max(0.5, fav_sol["long_model_price"] - 2.0), direction="down")
                long_lower_lim = round_to_tick(max(0.25, long_lower_trig - 1.5), direction="down")
                f_star_lower = fav_sol["f_star"]
            else:
                short_lower_trig = round_to_tick(max(1.0, short_ltp * 0.55), direction="up")
                short_lower_lim = round_to_tick(short_lower_trig + 1.5, direction="up")
                long_lower_trig = round_to_tick(max(0.5, long_ltp * 0.50 - 2.0), direction="down")
                long_lower_lim = round_to_tick(max(0.25, long_lower_trig - 1.5), direction="down")
                f_star_lower = round(forward, 2)

            if in_profit_on_touch:
                # REGIME A: Position is in Net Profit after charges -> Attempt NO_LOSS_PROFIT_LOCK_OCO
                cushion_pts = E_lock - exec_spread
                adv_target_spread = round(min(E_lock - 1.5, exec_spread + max(2.5, 0.55 * cushion_pts)), 2)

                if adv_target_spread > exec_spread + 1.0:
                    adv_sol = solve_forward_for_spread_value(
                        adv_target_spread,
                        forward,
                        short_strike,
                        long_strike,
                        T_years,
                        iv_short_dec,
                        iv_long_dec,
                        kind,
                        r,
                        stress_iv_bump=0.008,
                    )
                else:
                    adv_sol = None

                if adv_sol is not None and adv_sol["short_model_price"] > exec_short_buy + 1.5:
                    s_trig = round_to_tick(adv_sol["short_model_price"], direction="down")
                    l_model = adv_sol["long_model_price"]
                    chosen_s_lim = None
                    chosen_l_trig = None
                    chosen_l_lim = None
                    for s_buf, l_buf in ((4.0, 2.0), (2.5, 1.5), (1.5, 1.0), (1.0, 0.5)):
                        cand_s_lim = round_to_tick(s_trig + s_buf, direction="up")
                        cand_l_trig = round_to_tick(l_model + l_buf, direction="up")
                        cand_l_lim = round_to_tick(max(0.5, cand_l_trig - l_buf), direction="down")
                        worst_spread = cand_s_lim - cand_l_lim
                        worst_net = round((entry_credit - worst_spread) * Q - charges_rs, 2)
                        if worst_net >= locked_profit_floor_rs:
                            chosen_s_lim = cand_s_lim
                            chosen_l_trig = cand_l_trig
                            chosen_l_lim = cand_l_lim
                            floor_feasible = True
                            break

                    if floor_feasible and chosen_s_lim is not None:
                        short_upper_trig = s_trig
                        short_upper_lim = chosen_s_lim
                        long_upper_trig = chosen_l_trig
                        long_upper_lim = chosen_l_lim
                        f_star_upper = adv_sol["f_star"]
                        if not kill_switch:
                            oco_regime = "NO_LOSS_PROFIT_LOCK_OCO"
                    else:
                        short_upper_trig = s_trig
                        short_upper_lim = round_to_tick(s_trig + 2.0, direction="up")
                        long_upper_trig = round_to_tick(l_model + 1.5, direction="up")
                        long_upper_lim = round_to_tick(max(0.5, long_upper_trig - 1.5), direction="down")
                        f_star_upper = adv_sol["f_star"]
                        if not kill_switch:
                            oco_regime = "PROFIT_LOCK_INFEASIBLE"
                            reasons.append(
                                f"PROFIT_LOCK_INFEASIBLE: Current executable net profit (Rs {exec_net_pnl_rs:.0f}) is too small to fund GTT limit-slippage buffers without risking a small loss on a fast spike. Consider closing at market to bank Rs {exec_net_pnl_rs:.0f} net or holding with a tight damage cap."
                            )
                else:
                    short_upper_trig = round_to_tick(exec_short_buy + 4.0, direction="down")
                    short_upper_lim = round_to_tick(short_upper_trig + 2.0, direction="up")
                    long_upper_trig = round_to_tick(exec_long_sell + 3.5, direction="up")
                    long_upper_lim = round_to_tick(max(0.5, long_upper_trig - 1.5), direction="down")
                    f_star_upper = round(forward, 2)
                    if not kill_switch:
                        oco_regime = "PROFIT_LOCK_INFEASIBLE"
                        reasons.append(
                            f"PROFIT_LOCK_INFEASIBLE: Executable spread ({exec_spread:.2f}) is only {E_zero - exec_spread:.2f} pts away from breakeven ({E_zero:.2f}); a resting GTT stop cannot guarantee zero loss after slippage."
                        )
            else:
                # REGIME B: Position is Underwater (exec_spread >= E_zero) -> LOSS_MINIMIZATION_OCO
                cap_spread = min(width * 0.62, max(exec_spread + 3.0, E_cap - 2.5))
                adv_sol = solve_forward_for_spread_value(
                    cap_spread,
                    forward,
                    short_strike,
                    long_strike,
                    T_years,
                    iv_short_dec,
                    iv_long_dec,
                    kind,
                    r,
                    stress_iv_bump=0.012,
                )
                if adv_sol is not None and adv_sol["short_model_price"] > exec_short_buy + 1.0:
                    short_upper_trig = round_to_tick(adv_sol["short_model_price"], direction="down")
                    short_upper_lim = round_to_tick(short_upper_trig + 4.0, direction="up")
                    long_upper_trig = round_to_tick(adv_sol["long_model_price"] + 2.0, direction="up")
                    long_upper_lim = round_to_tick(max(0.5, long_upper_trig - 2.0), direction="down")
                    f_star_upper = adv_sol["f_star"]
                else:
                    short_upper_trig = round_to_tick(exec_short_buy + 8.0, direction="down")
                    short_upper_lim = round_to_tick(short_upper_trig + 4.0, direction="up")
                    long_upper_trig = round_to_tick(exec_long_sell + 6.5, direction="up")
                    long_upper_lim = round_to_tick(max(0.5, long_upper_trig - 2.0), direction="down")
                    f_star_upper = round(forward, 2)

                if not kill_switch:
                    oco_regime = "LOSS_MINIMIZATION_OCO"
                    reasons.append(
                        f"LOSS_MINIMIZATION_OCO: Spread is currently underwater (Rs {exec_net_pnl_rs:.0f} net). Lower GTT trigger is set to Cost-Breakeven Scratch (spread {E_zero:.2f} pts => Rs 0 net loss) and Upper GTT trigger caps maximum loss before the short-strike Gamma wall."
                    )

            target_trig_spread = round(short_lower_trig - long_lower_trig, 2)
            target_lim_spread = round(short_lower_lim - long_lower_lim, 2)
            stop_trig_spread = round(short_upper_trig - long_upper_trig, 2)
            stop_lim_spread = round(short_upper_lim - long_upper_lim, 2)

            target_trig_net_rs = round((entry_credit - target_trig_spread) * Q - charges_rs, 2)
            target_lim_net_rs = round((entry_credit - target_lim_spread) * Q - charges_rs, 2)
            stop_trig_net_rs = round((entry_credit - stop_trig_spread) * Q - charges_rs, 2)
            stop_lim_net_rs = round((entry_credit - stop_lim_spread) * Q - charges_rs, 2)
            h_min_for_zero_loss = round(max(0.0, short_upper_lim - entry_credit + charges_rs / Q), 2)
        else:
            # DEBIT SPREAD (`BULL_CALL` or `BEAR_PUT`):
            # Favorable move WIDENS (long - short) toward E_target -> both option premiums RISE!
            # Adverse move SHRINKS (long - short) toward E_lock (if profitable) or E_cap (if underwater) -> option premiums FALL!
            entry_debit = round(long_entry - short_entry, 2)
            in_profit_on_touch = exec_spread > E_zero
            desired_fav_spread = E_target if in_profit_on_touch else E_zero
            desired_adv_spread = (
                round(max(E_lock + 1.5, exec_spread - 0.55 * (exec_spread - E_lock)), 2)
                if in_profit_on_touch
                else E_cap
            )

            fav_sol = solve_forward_for_spread_value(
                desired_fav_spread, forward, short_strike, long_strike, T_years, iv_short_dec, iv_long_dec, kind, r
            )
            adv_sol = solve_forward_for_spread_value(
                desired_adv_spread, forward, short_strike, long_strike, T_years, iv_short_dec, iv_long_dec, kind, r
            )

            # In a debit spread, Upper GTT slot is the Profit/Scratch Target (higher premiums),
            # and Lower GTT slot is the Stop-Loss / Profit-Lock (lower premiums).
            if fav_sol is not None:
                short_upper_trig = round_to_tick(fav_sol["short_model_price"], direction="down")
                short_upper_lim = round_to_tick(short_upper_trig + 2.0, direction="up")
                long_upper_trig = round_to_tick(fav_sol["long_model_price"] + 2.0, direction="up")
                long_upper_lim = round_to_tick(max(0.5, long_upper_trig - 1.5), direction="down")
                f_star_upper = fav_sol["f_star"]
            else:
                short_upper_trig = round_to_tick(short_ltp * 1.35, direction="down")
                short_upper_lim = round_to_tick(short_upper_trig + 2.0, direction="up")
                long_upper_trig = round_to_tick(long_ltp * 1.35 + 2.0, direction="up")
                long_upper_lim = round_to_tick(max(0.5, long_upper_trig - 1.5), direction="down")
                f_star_upper = round(forward, 2)

            if adv_sol is not None:
                short_lower_trig = round_to_tick(adv_sol["short_model_price"], direction="up")
                short_lower_lim = round_to_tick(short_lower_trig + 1.5, direction="up")
                long_lower_trig = round_to_tick(max(0.5, adv_sol["long_model_price"] - 2.0), direction="down")
                long_lower_lim = round_to_tick(max(0.25, long_lower_trig - 1.5), direction="down")
                f_star_lower = adv_sol["f_star"]
            else:
                short_lower_trig = round_to_tick(max(1.0, short_ltp * 0.70), direction="up")
                short_lower_lim = round_to_tick(short_lower_trig + 1.5, direction="up")
                long_lower_trig = round_to_tick(max(0.5, long_ltp * 0.70 - 2.0), direction="down")
                long_lower_lim = round_to_tick(max(0.25, long_lower_trig - 1.5), direction="down")
                f_star_lower = round(forward, 2)

            stop_lim_spread = round(long_lower_lim - short_lower_lim, 2)
            stop_trig_spread = round(long_lower_trig - short_lower_trig, 2)
            target_trig_spread = round(long_upper_trig - short_upper_trig, 2)
            target_lim_spread = round(long_upper_lim - short_upper_lim, 2)

            target_trig_net_rs = round((target_trig_spread - entry_debit) * Q - charges_rs, 2)
            target_lim_net_rs = round((target_lim_spread - entry_debit) * Q - charges_rs, 2)
            stop_trig_net_rs = round((stop_trig_spread - entry_debit) * Q - charges_rs, 2)
            stop_lim_net_rs = round((stop_lim_spread - entry_debit) * Q - charges_rs, 2)
            floor_feasible = in_profit_on_touch and (stop_lim_net_rs >= locked_profit_floor_rs)
            if not kill_switch:
                oco_regime = (
                    "NO_LOSS_PROFIT_LOCK_OCO"
                    if floor_feasible
                    else ("PROFIT_LOCK_INFEASIBLE" if in_profit_on_touch else "LOSS_MINIMIZATION_OCO")
                )
            h_min_for_zero_loss = round(max(0.0, short_lower_lim + entry_debit + charges_rs / Q), 2)

        sequenced_gtt_plan = {
            "oco_regime": oco_regime,
            "zero_loss_floor_feasible": floor_feasible,
            "execution_warning": (
                "Kite two-leg GTTs are independent single-instrument limit triggers, not atomic spread orders. "
                "SAFEST EXECUTION: Arm the Short-Leg BUY OCO GTT first; once SHORT_FLAT_CONFIRMED (qty == 0), "
                f"sell the Long hedge at >= Rs {h_min_for_zero_loss:.2f} (H_min for zero-loss floor)."
            ),
            "thresholds_spread_pts": {
                "E_zero_breakeven_pts": E_zero,
                "E_lock_floor_pts": E_lock,
                "E_target_pts": E_target,
                "E_cap_max_loss_pts": E_cap,
            },
            "short_leg_buy_gtt": {
                "strike": short_strike,
                "transaction_type": "BUY",
                "lower_target_trigger": short_lower_trig,
                "lower_target_limit": short_lower_lim,
                "lower_f_star": f_star_lower,
                "upper_stop_trigger": short_upper_trig,
                "upper_stop_limit": short_upper_lim,
                "upper_f_star": f_star_upper,
            },
            "long_leg_sell_gtt": {
                "strike": long_strike,
                "transaction_type": "SELL",
                "lower_target_trigger": long_lower_trig,
                "lower_target_limit": long_lower_lim,
                "upper_stop_trigger": long_upper_trig,
                "upper_stop_limit": long_upper_lim,
                "h_min_after_short_stop_fill": h_min_for_zero_loss,
            },
            "scenario_payoffs_rs": {
                "lower_target_normal_fill": {
                    "exit_spread_pts": target_trig_spread,
                    "gross_pnl_rs": round(target_trig_net_rs + charges_rs, 2),
                    "net_pnl_rs": target_trig_net_rs,
                },
                "lower_target_worst_limit_fill": {
                    "exit_spread_pts": target_lim_spread,
                    "gross_pnl_rs": round(target_lim_net_rs + charges_rs, 2),
                    "net_pnl_rs": target_lim_net_rs,
                },
                "upper_stop_normal_fill": {
                    "exit_spread_pts": stop_trig_spread,
                    "gross_pnl_rs": round(stop_trig_net_rs + charges_rs, 2),
                    "net_pnl_rs": stop_trig_net_rs,
                },
                "upper_stop_worst_limit_fill": {
                    "exit_spread_pts": stop_lim_spread,
                    "gross_pnl_rs": round(stop_lim_net_rs + charges_rs, 2),
                    "net_pnl_rs": stop_lim_net_rs,
                },
            },
        }

    # Final Verdict Assignment
    if kill_switch:
        verdict = "CLOSE_ALL_IMMEDIATELY"
    elif oco_regime == "LOSS_MINIMIZATION_OCO":
        verdict = "HOLD_WITH_LOSS_MINIMIZATION_OCO"
    elif net_theta_pts < 0.50 and t_days > 14:
        verdict = "ROLL_TO_NEAR_EXPIRY_OR_HOLD_WITH_OCO"
        reasons.append(
            f"LOW NET THETA WARNING: Hedge {int(long_strike)} {kind} burns {hedge_theta_burn_ratio:.1f}% of short leg's Theta "
            f"(Net Theta is only +{net_theta_pts:.2f} pts/day = +Rs {net_theta_pts * Q:.0f}/day at {t_days:.1f} DTE). "
            "Keep the No-Loss OCO active, or switch to the nearest weekly/monthly expiry for 10x+ faster Theta decay."
        )
    else:
        verdict = "HOLD_WITH_NO_LOSS_OCO" if floor_feasible else "HOLD_WITH_TIGHT_OCO_OR_BOOK_PROFIT"
        if not reasons:
            reasons.append(
                f"Position healthy ({oco_regime}): Net Theta +{net_theta_pts:.2f} pts/day (+Rs {net_theta_pts * Q:.0f}/day), "
                f"OTM Cushion {abs(short_strike - forward):.0f} pts, Terminal PoP {pop_terminal_pct:.1f}%."
            )

    return {
        "verdict": verdict,
        "oco_regime": oco_regime,
        "strategy": strat,
        "reasons": reasons,
        "summary": {
            "quantity": Q,
            "entry_credit_pts": E_signed,
            "live_spread_ltp_pts": S_ltp_signed,
            "executable_spread_touch_pts": S_exec_signed,
            "captured_pts_ltp": captured_pts_ltp,
            "captured_pts_exec": captured_pts_exec,
            "gross_pnl_rs": gross_pnl_rs,
            "charges_rs": charges_rs,
            "charges_breakdown": charges_breakdown,
            "net_pnl_ltp_rs": net_pnl_rs,
            "net_pnl_executable_rs": exec_net_pnl_rs,
            "max_profit_net_rs": max_profit_net,
            "max_loss_net_rs": max_loss_net,
            "breakeven_expiry_net": breakeven_expiry,
            "pop_terminal_pct": pop_terminal_pct,
            "target_net_requested_rs": target_net_rupees,
            "target_reachable": target_reachable,
            "target_exit_spread_pts": E_target,
        },
        "greeks": {
            "discount_factor": round(df, 6),
            "short_leg": g_short,
            "long_leg": g_long,
            "net_delta_per_pt": net_delta,
            "net_delta_lot_qty": round(net_delta * Q, 2),
            "net_gamma": net_gamma,
            "net_theta_pts_day": net_theta_pts,
            "net_theta_rs_day": round(net_theta_pts * Q, 0),
            "net_vega_pts_1pct": net_vega_pts,
            "net_vega_rs_1pct": round(net_vega_pts * Q, 0),
            "net_vanna_per_1pct_iv": net_vanna,
            "net_charm_delta_day": net_charm,
            "hedge_theta_burn_pct": hedge_theta_burn_ratio,
            "daily_1sigma_move_pts": daily_1sigma_pts,
            "theta_gamma_breakeven_move_pts": theta_gamma_be_pts,
        },
        "sequenced_gtt_plan": sequenced_gtt_plan,
    }


def rank_candidate_spreads(
    forward: float,
    t_days: float,
    bias: str,
    chain: List[Dict[str, float]],
    lot_size: int = LOT_SIZE_DEFAULT,
    r: float = RISK_FREE_RATE_DEFAULT,
) -> Dict[str, Any]:
    """
    Ranks candidate 150/200/250-pt spreads from option chain quotes.
    Filters ELIGIBLE candidates FIRST (fixes late-filtering bug where a high-score candidate
    failing a gate blocked valid passing candidates), and enforces a strict NO_POSITION gate.
    """
    b_clean = str(bias).strip().lower()
    if b_clean in ("bear", "bear_call", "bearish", "ce"):
        opt_type = "CE"
    elif b_clean in ("bull", "bull_put", "bullish", "pe"):
        opt_type = "PE"
    else:
        raise ValueError(f"Unsupported bias '{bias}'. Use 'bear_call' or 'bull_put'.")

    quotes = {
        int(row["strike"]): float(row["ltp"])
        for row in chain
        if str(row["type"]).strip().upper() == opt_type and float(row["ltp"]) > 0
    }
    strikes = sorted(quotes.keys())
    all_candidates: List[Dict[str, Any]] = []
    eligible_candidates: List[Dict[str, Any]] = []

    Q = int(lot_size)
    T_years = max(float(t_days), 0.01) / 365.0

    for s_short in strikes:
        for width in (150, 200, 250):
            s_long = s_short + width if opt_type == "CE" else s_short - width
            if s_long not in quotes:
                continue
            p_short, p_long = quotes[s_short], quotes[s_long]
            credit = round(p_short - p_long, 2)
            if credit <= 12.0:
                continue

            g_s = compute_greeks(forward, s_short, t_days, p_short, opt_type, r)
            g_l = compute_greeks(forward, s_long, t_days, p_long, opt_type, r)
            if not (g_s["iv_reliable"] and g_l["iv_reliable"]):
                continue
            if not (0.16 <= abs(g_s["delta"]) <= 0.42):
                continue

            charges = compute_zerodha_nse_charges(
                buy_turnover_rs=(p_long + p_short * 0.5) * Q,
                sell_turnover_rs=(p_short + p_long * 0.5) * Q,
                num_orders=4,
            )["total_charges_rs"]

            net_theta = round(-g_s["theta_pts_day"] + g_l["theta_pts_day"], 2)
            net_gamma = round(-g_s["gamma"] + g_l["gamma"], 6)
            max_prof_net = round(credit * Q - charges, 0)
            max_loss_net = round((width - credit) * Q + charges, 0)
            rr_pct = round((credit / width) * 100.0, 1)
            distance_pts = round((s_short - forward) if opt_type == "CE" else (forward - s_short), 1)
            if distance_pts <= 0:
                continue

            # Breakeven and Terminal PoP
            be = round(s_short + credit - charges / Q, 2) if opt_type == "CE" else round(s_short - credit + charges / Q, 2)
            iv_s = max(0.01, g_s["iv_pct"] / 100.0)
            d1_be = (math.log(forward / be) + 0.5 * iv_s**2 * T_years) / (iv_s * math.sqrt(T_years))
            d2_be = d1_be - iv_s * math.sqrt(T_years)
            pop_pct = round((norm_cdf(-d2_be) if opt_type == "CE" else norm_cdf(d2_be)) * 100.0, 1)

            passes_gate = rr_pct >= 18.0 and net_theta >= 1.5 and distance_pts >= 40.0
            score = round(rr_pct + net_theta * 3.5 + (distance_pts / 25.0) + (pop_pct * 0.15), 2)

            cand = {
                "strategy": f"{'Bear Call' if opt_type == 'CE' else 'Bull Put'} {s_short}/{s_long} {opt_type}",
                "short_strike": s_short,
                "long_strike": s_long,
                "width": width,
                "net_credit_pts": credit,
                "estimated_charges_rs": charges,
                "max_profit_net_rs": max_prof_net,
                "max_loss_net_rs": max_loss_net,
                "breakeven_expiry": be,
                "pop_terminal_pct": pop_pct,
                "credit_to_width_pct": rr_pct,
                "short_delta": g_s["delta"],
                "net_delta": round(-g_s["delta"] + g_l["delta"], 3),
                "net_gamma": net_gamma,
                "net_theta_pts_day": net_theta,
                "net_theta_rs_day": round(net_theta * Q, 0),
                "otm_cushion_pts": distance_pts,
                "passes_edge_gate": passes_gate,
                "score": score,
            }
            all_candidates.append(cand)
            if passes_gate:
                eligible_candidates.append(cand)

    all_candidates.sort(key=lambda x: x["score"], reverse=True)
    eligible_candidates.sort(key=lambda x: x["score"], reverse=True)

    if not eligible_candidates:
        return {
            "verdict": "NO_POSITION_RECOMMENDED",
            "reason": (
                "No candidate spread passes all edge gates (requires >= 18% credit-to-width ratio, "
                ">= +1.5 pts/day net Theta, >= 40 pts OTM cushion, and 0.16-0.42 short |Delta|)."
            ),
            "top_candidates": all_candidates[:3],
        }

    return {
        "verdict": "ENTER_BEST_SPREAD",
        "best_spread": eligible_candidates[0],
        "alternatives": eligible_candidates[1:4],
    }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        payload = json.loads(sys.argv[1])
        mode = payload.get("mode", "evaluate")
        if mode == "evaluate":
            res = evaluate_live_credit_spread(**payload["params"])
        elif mode == "parity":
            res = implied_forward_from_pair(**payload["params"])
        elif mode == "charges":
            res = compute_zerodha_nse_charges(**payload["params"])
        else:
            res = rank_candidate_spreads(**payload["params"])
        print(json.dumps(res, indent=2))
