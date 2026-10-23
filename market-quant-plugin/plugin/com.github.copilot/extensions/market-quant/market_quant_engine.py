#!/usr/bin/env python3
"""
Market Quant & Microstructure Engine (market-quant skill)
Computes 8 institutional quantitative & microstructure lenses across Daily (2Y),
Weekly (5Y), and Intraday 1-Hour (60D) bars, and renders:
  1. data/indices_and_etfs_metrics.csv
  2. data/constituents_quant_matrix.csv
  3. data/anomaly_summary.json (ranked multi-indicator anomalies & social hooks)
  4. reports/intraday_smart_money_clock_<tag>.png (300 DPI)
  5. reports/social_media_quant_infographic_<tag>.png (300 DPI)
  6. reports/market_quant_dashboard_<tag>.html (Clawpilot light/dark interactive dashboard)
"""

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
import warnings
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# UNIFIED SIGNAL SPECIFICATION (SINGLE SOURCE OF TRUTH FOR ENGINE, CHARTS & SKILL)
# ---------------------------------------------------------------------------

SIGNAL_SPEC = {
    "bull_trap_min_rsi": 55.0,
    "bull_trap_rsi_min": 55.0,
    "bull_trap_max_cmf": -0.05,
    "bull_trap_cmf_max": -0.05,
    "true_breakout_min_rsi": 55.0,
    "true_breakout_rsi_min": 55.0,
    "true_breakout_min_cmf": 0.10,
    "true_breakout_cmf_min": 0.10,
    "stealth_accum_max_rsi": 55.0,
    "stealth_accum_rsi_max": 55.0,
    "stealth_accum_min_cmf": 0.10,
    "stealth_accum_cmf_min": 0.10,
    "stealth_accum_min_ud_vol": 1.25,
    "stealth_accum_ud_vol_min": 1.25,
    "heavy_dist_max_cmf": -0.15,
    "heavy_dist_cmf_max": -0.15,
    "bbw_squeeze_max_pct": 20.0,
    "bbw_squeeze_percentile_max": 20.0,
    "hurst_anti_persistent_max": 0.45,
    "hurst_persistent_min": 0.55,
    "hurst_min_zscore": 1.5,
    "cmf_min_nonzero_vol_days_20d": 17,
    "fft_min_variance_share_pct": 15.0,
    "fft_max_vol_regime_ratio_20v60": 1.75,
}

# ---------------------------------------------------------------------------
# UNIVERSE DEFINITIONS
# ---------------------------------------------------------------------------

UNIVERSES = {
    "india": {
        "label": "Indian Stock Market (NSE / Nifty)",
        "primary_index": "Nifty50",
        "secondary_index": "BankNifty",
        "vix_key": "IndiaVIX",
        "open_slot": "09:15",
        "close_slot": "15:15",
        "indices": {
            "Nifty50": "^NSEI",
            "BankNifty": "^NSEBANK",
            "IndiaVIX": "^INDIAVIX",
            "NiftyIT": "^CNXIT",
            "NiftyPharma": "^CNXPHARMA",
            "NiftyMetal": "^CNXMETAL",
            "NiftyAuto": "^CNXAUTO",
            "NiftyFMCG": "^CNXFMCG",
            "NiftyEnergy": "^CNXENERGY",
            "NiftyInfra": "^CNXINFRA",
            "NiftyRealty": "^CNXREALTY",
            "NiftyPSUBank": "^CNXPSUBANK",
            "Sensex": "^BSESN",
            "SP500": "^GSPC",
            "USDINR": "INR=X",
            "BrentCrude": "BZ=F",
            "Gold": "GC=F",
            "US10Y": "^TNX",
            "DXY": "DX-Y.NYB",
        },
        "etfs": {
            "NiftyBees": "NIFTYBEES.NS",
            "JuniorBees_Next50": "JUNIORBEES.NS",
            "Mid150Bees": "MID150BEES.NS",
            "HDFCSmall250": "HDFCSML250.NS",
            "BankBees": "BANKBEES.NS",
            "PSUBankBees": "PSUBNKBEES.NS",
            "ITBees": "ITBEES.NS",
            "PharmaBees": "PHARMABEES.NS",
            "AutoBees": "AUTOBEES.NS",
            "GoldBees": "GOLDBEES.NS",
            "SilverBees": "SILVERBEES.NS",
            "CPSE_ETF": "CPSEETF.NS",
        },
        "stocks": [
            "RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "TCS.NS",
            "BHARTIARTL.NS", "SBIN.NS", "LT.NS", "ITC.NS", "AXISBANK.NS",
            "KOTAKBANK.NS", "HINDUNILVR.NS", "BAJFINANCE.NS", "MARUTI.NS",
            "SUNPHARMA.NS", "NTPC.NS", "M&M.NS", "TATAMOTORS.NS", "HCLTECH.NS",
            "TITAN.NS", "ULTRACEMCO.NS", "POWERGRID.NS", "ASIANPAINT.NS",
            "TRENT.NS", "BEL.NS", "HAL.NS", "ADANIPORTS.NS", "COALINDIA.NS",
            "BAJAJ-AUTO.NS", "TATASTEEL.NS", "JSWSTEEL.NS", "WIPRO.NS",
            "ONGC.NS", "DRREDDY.NS", "CIPLA.NS", "ZOMATO.NS",
        ],
    },
    "us": {
        "label": "US Equity Market (S&P 500 / Nasdaq)",
        "primary_index": "SP500",
        "secondary_index": "Nasdaq100",
        "vix_key": "VIX",
        "open_slot": "09:30",
        "close_slot": "15:30",
        "indices": {
            "SP500": "^GSPC",
            "Nasdaq100": "^NDX",
            "DowJones": "^DJI",
            "Russell2000": "^RUT",
            "VIX": "^VIX",
            "US10Y": "^TNX",
            "DXY": "DX-Y.NYB",
            "WTICrude": "CL=F",
            "Gold": "GC=F",
        },
        "etfs": {
            "SPY": "SPY",
            "QQQ": "QQQ",
            "IWM": "IWM",
            "XLK_Tech": "XLK",
            "XLF_Financials": "XLF",
            "XLV_Health": "XLV",
            "XLE_Energy": "XLE",
            "XLI_Industrials": "XLI",
            "XLY_Discretionary": "XLY",
            "XLP_Staples": "XLP",
            "XLU_Utilities": "XLU",
            "GLD_Gold": "GLD",
        },
        "stocks": [
            "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AVGO",
            "BRK-B", "JPM", "LLY", "V", "UNH", "XOM", "MA", "COST", "HD",
            "PG", "WMT", "NFLX", "JNJ", "CRM", "ABBV", "BAC", "ORCL", "MRK",
            "AMD", "CVX", "PEP", "KO",
        ],
    },
}


# ---------------------------------------------------------------------------
# QUANTITATIVE INDICATOR FUNCTIONS
# ---------------------------------------------------------------------------

def wilder_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Exact Wilder's RSI with arithmetic-mean seed over first `period` diffs and zero-loss protection."""
    s = close.astype(float)
    delta = s.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    rsi = pd.Series(np.nan, index=s.index, dtype=float)
    valid = delta.dropna()
    if len(valid) < period:
        return rsi
    vals_g = gain.values
    vals_l = loss.values
    out = np.full(len(s), np.nan, dtype=float)
    # Find first index with `period` valid diffs
    first_valid_pos = int(np.where(~np.isnan(delta.values))[0][0])
    seed_end = first_valid_pos + period
    if seed_end > len(s):
        return rsi
    avg_g = float(np.nanmean(vals_g[first_valid_pos:seed_end]))
    avg_l = float(np.nanmean(vals_l[first_valid_pos:seed_end]))
    if avg_l == 0.0:
        out[seed_end - 1] = 100.0 if avg_g > 0.0 else 50.0
    else:
        rs = avg_g / avg_l
        out[seed_end - 1] = 100.0 - (100.0 / (1.0 + rs))
    for i in range(seed_end, len(s)):
        g_i = 0.0 if np.isnan(vals_g[i]) else float(vals_g[i])
        l_i = 0.0 if np.isnan(vals_l[i]) else float(vals_l[i])
        avg_g = (avg_g * (period - 1) + g_i) / period
        avg_l = (avg_l * (period - 1) + l_i) / period
        if avg_l == 0.0:
            out[i] = 100.0 if avg_g > 0.0 else 50.0
        else:
            rs = avg_g / avg_l
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return pd.Series(out, index=s.index, dtype=float)


def compute_adx_dmi(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=close.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=close.index)
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr.replace(0, np.nan))
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx = dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return adx, plus_di, minus_di, atr


def chaikin_money_flow(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 20) -> pd.Series:
    hl = (high - low).replace(0, np.nan)
    mfm = ((close - low) - (high - close)) / hl
    mfv = mfm.fillna(0.0) * volume
    return mfv.rolling(period).sum() / volume.rolling(period).sum().replace(0, np.nan)


def hurst_with_se(log_prices: np.ndarray, max_lag: int = 20):
    """
    Lag-Increment Scaling Hurst Estimator (Variogram of log-prices) with regression Standard Error:
    Fits log(std(P[t+tau] - P[t])) vs log(tau).
    Returns (hurst, se).
    H < 0.45: Mean-reverting / anti-persistent; 0.45 <= H <= 0.55: Random Walk; H > 0.55: Persistent trend.
    """
    ts = np.asarray(log_prices, dtype=float)
    ts = ts[~np.isnan(ts)]
    if len(ts) < max_lag + 5:
        return float("nan"), float("nan")
    lags = range(2, max_lag)
    tau = []
    valid_lags = []
    for lag in lags:
        diff = np.subtract(ts[lag:], ts[:-lag])
        std = np.std(diff, ddof=1)
        if std > 0:
            tau.append(std)
            valid_lags.append(lag)
    if len(tau) < 4:
        return float("nan"), float("nan")
    x = np.log(valid_lags)
    y = np.log(tau)
    poly, cov = np.polyfit(x, y, 1, cov=True)
    h_val = float(np.clip(poly[0], 0.01, 0.99))
    h_se = float(np.sqrt(max(0.0, cov[0, 0]))) if cov is not None and cov.shape == (2, 2) else 0.05
    return h_val, h_se


def hurst_exponent(log_prices: np.ndarray, max_lag: int = 20) -> float:
    h_val, _ = hurst_with_se(log_prices, max_lag=max_lag)
    return h_val


def hurst_rs_exponent(log_prices: np.ndarray) -> float:
    """
    Classical Mandelbrot-Wallis Rescaled-Range (R/S) Hurst Estimator on log-returns:
    Subdivides returns into contiguous blocks of size n, computes cumulative demeaned range R(n)
    divided by sample standard deviation S(n), and fits log(E[R/S]) vs log(n).
    """
    ts = np.asarray(log_prices, dtype=float)
    ts = ts[~np.isnan(ts)]
    if len(ts) < 32:
        return float("nan")
    rets = np.diff(ts)
    N = len(rets)
    block_sizes = [n for n in (8, 12, 16, 24, 32, 48, 60) if n <= N // 2]
    if len(block_sizes) < 3:
        block_sizes = [n for n in range(6, max(7, N // 2 + 1), max(1, (N // 2 - 6) // 4)) if n <= N]
    ns_valid = []
    rs_means = []
    for n in block_sizes:
        num_blocks = N // n
        if num_blocks < 1:
            continue
        rs_vals = []
        for b in range(num_blocks):
            sub = rets[b * n : (b + 1) * n]
            s_std = np.std(sub, ddof=1)
            if s_std <= 1e-12:
                continue
            dev = np.cumsum(sub - np.mean(sub))
            r_rng = float(np.max(dev) - np.min(dev))
            if r_rng > 0:
                rs_vals.append(r_rng / s_std)
        if rs_vals:
            ns_valid.append(n)
            rs_means.append(float(np.mean(rs_vals)))
    if len(ns_valid) < 3:
        return float("nan")
    slope = np.polyfit(np.log(ns_valid), np.log(rs_means), 1)[0]
    return float(np.clip(slope, 0.01, 0.99))


def dominant_fft_cycles(close: pd.Series, top_n: int = 3):
    clean_c = close.dropna()
    clean_c = clean_c[clean_c > 0]
    if len(clean_c) < 64:
        return []
    s = np.log(clean_c)
    x = np.arange(len(s))
    trend = np.polyval(np.polyfit(x, s.values, 1), x)
    detrended = (s.values - trend) * np.hanning(len(s))
    fft_vals = np.fft.rfft(detrended)
    freqs = np.fft.rfftfreq(len(s), d=1.0)
    power = np.abs(fft_vals) ** 2
    periods = np.where(freqs > 0, 1.0 / freqs, np.inf)
    valid = (freqs > 0) & (periods <= len(s) / 2.0) & (periods >= 8.0)
    v_freqs = freqs[valid]
    v_power = power[valid]
    total_p = float(np.sum(v_power))
    if len(v_power) == 0 or total_p <= 1e-12:
        return []
    order = np.argsort(v_power)[::-1][:top_n]
    return [
        {
            "period_days": round(float(1.0 / v_freqs[idx]), 1),
            "power_share_pct": round(float(v_power[idx] / total_p * 100.0), 1),
        }
        for idx in order
    ]


def compute_fft_projection(close: pd.Series, window: int = 126, forward_days: int = 25):
    clean_c = close.dropna()
    clean_c = clean_c[clean_c > 0].iloc[-window:]
    n = len(clean_c)
    if n < 64:
        return {}
    s = np.log(clean_c)
    t = np.arange(n)
    poly = np.polyfit(t, s.values, 1)
    detrended = s.values - np.polyval(poly, t)
    fft_c = np.fft.rfft(detrended)
    freqs = np.fft.rfftfreq(n, d=1.0)
    power = np.abs(fft_c) ** 2
    total_power = float(np.sum(power[1:])) if len(power) > 1 else 0.0
    periods = np.where(freqs > 0, 1.0 / freqs, np.inf)
    eligible_idx = np.where((freqs > 0) & (periods >= 20.0) & (periods <= 75.0) & (power > 0))[0]
    if len(eligible_idx) == 0 or total_power <= 1e-12:
        return {}
    sorted_elig = eligible_idx[np.argsort(power[eligible_idx])[::-1]]
    idx_top = sorted_elig[:2]
    top_power_share = round(float(np.sum(power[idx_top]) / total_power * 100.0), 1)

    t_ext = np.arange(n + forward_days)
    recon = np.zeros_like(t_ext, dtype=float)
    for k in idx_top:
        amp = np.abs(fft_c[k]) / n * 2.0
        phase = np.angle(fft_c[k])
        recon += amp * np.cos(2.0 * np.pi * freqs[k] * t_ext + phase)

    # Detect true local extrema inside the forward projection window (including transition from last historical point)
    w_seq = recon[n - 1 :]  # index 0 is last historical point; index 1..forward_days are future days 1..forward_days
    local_crests = []
    local_troughs = []
    for j in range(1, len(w_seq) - 1):
        if w_seq[j] > w_seq[j - 1] and w_seq[j] >= w_seq[j + 1]:
            local_crests.append(j)
        if w_seq[j] < w_seq[j - 1] and w_seq[j] <= w_seq[j + 1]:
            local_troughs.append(j)

    future_slice = recon[n:]
    horizon_max_day = int(np.argmax(future_slice)) + 1
    horizon_min_day = int(np.argmin(future_slice)) + 1
    next_crest = local_crests[0] if local_crests else horizon_max_day
    next_trough = local_troughs[0] if local_troughs else horizon_min_day

    # Volatility regime stability check (20D vs 60D realized vol)
    log_rets = np.diff(s.values)
    rv20_s = float(np.std(log_rets[-20:], ddof=1)) if len(log_rets) >= 20 else 0.0
    rv60_s = float(np.std(log_rets[-60:], ddof=1)) if len(log_rets) >= 60 else rv20_s
    vol_ratio = round(rv20_s / rv60_s, 2) if rv60_s > 1e-9 else 1.0
    fft_reliable = bool(
        top_power_share >= SIGNAL_SPEC["fft_min_variance_share_pct"]
        and vol_ratio <= SIGNAL_SPEC["fft_max_vol_regime_ratio_20v60"]
    )

    return {
        "dates": [str(d)[:10] for d in s.index],
        "close": [round(float(v), 2) for v in clean_c.values],
        "detrended_pct": [round(float(v * 100.0), 3) for v in detrended],
        "harmonic_hist_pct": [round(float(v * 100.0), 3) for v in recon[:n]],
        "harmonic_future_pct": [round(float(v * 100.0), 3) for v in future_slice],
        "selected_periods_days": [round(float(1.0 / freqs[k]), 1) for k in idx_top],
        "harmonic_variance_share_pct": top_power_share,
        "vol_regime_ratio_20v60": vol_ratio,
        "fft_reliable": fft_reliable,
        "next_crest_trading_days": next_crest,
        "next_trough_trading_days": next_trough,
        "next_crest_is_interior_extremum": bool(len(local_crests) > 0),
        "next_trough_is_interior_extremum": bool(len(local_troughs) > 0),
    }


def compute_volume_profile(df: pd.DataFrame, lookback: int = 120, bins: int = 24) -> dict:
    """
    120D Daily-Range-Distributed Volume Profile with contiguous POC-outward 70% Value Area.
    Distributes each daily bar's volume uniformly across bins spanned by [Low, High].
    """
    sub = df.iloc[-lookback:].copy()
    if sub.empty or sub["Volume"].sum() <= 0:
        return {}
    p_min = float(sub["Low"].min())
    p_max = float(sub["High"].max())
    if p_max <= p_min or np.isnan(p_min) or np.isnan(p_max):
        return {}
    edges = np.linspace(p_min, p_max, bins + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    vol_hist = np.zeros(bins, dtype=float)
    for _, row in sub.iterrows():
        v = float(row["Volume"])
        if v <= 0 or np.isnan(v):
            continue
        lo = float(row["Low"])
        hi = float(row["High"])
        b_lo = int(np.clip(np.digitize(lo, edges) - 1, 0, bins - 1))
        b_hi = int(np.clip(np.digitize(hi, edges) - 1, 0, bins - 1))
        if b_hi < b_lo:
            b_lo, b_hi = b_hi, b_lo
        n_spanned = b_hi - b_lo + 1
        vol_hist[b_lo : b_hi + 1] += v / n_spanned

    total_v = float(np.sum(vol_hist))
    if total_v <= 0:
        return {}
    poc_idx = int(np.argmax(vol_hist))
    poc_price = float(centers[poc_idx])

    # Contiguous Market Profile Value Area expansion (70% around POC)
    left_idx = poc_idx
    right_idx = poc_idx
    cum_v = float(vol_hist[poc_idx])
    target_v = 0.70 * total_v
    while cum_v < target_v and (left_idx > 0 or right_idx < bins - 1):
        v_left = vol_hist[left_idx - 1] if left_idx > 0 else -1.0
        v_right = vol_hist[right_idx + 1] if right_idx < bins - 1 else -1.0
        if v_left >= v_right:
            left_idx -= 1
            cum_v += float(vol_hist[left_idx])
        else:
            right_idx += 1
            cum_v += float(vol_hist[right_idx])

    mean_bin_v = total_v / bins
    lvn_bins = [round(float(centers[i]), 2) for i in range(left_idx, right_idx + 1) if vol_hist[i] < 0.45 * mean_bin_v]

    return {
        "poc": round(poc_price, 2),
        "val": round(float(edges[left_idx]), 2),
        "vah": round(float(edges[right_idx + 1]), 2),
        "va_coverage_pct": round(float(cum_v / total_v * 100.0), 1),
        "lvn_air_pockets": lvn_bins[:3],
    }


# ---------------------------------------------------------------------------
# DATA FETCH OR CACHE LOAD (ZERO EXTERNAL API DEPENDENCY — PURE URLLIB)
# ---------------------------------------------------------------------------

def _get_market_tz(tz_name: str, fallback_offset_minutes: int):
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return dt.timezone(dt.timedelta(minutes=fallback_offset_minutes))


def fetch_yahoo_v8(symbol: str, range_str: str = "2y", interval: str = "1d", tz_offset_minutes: int = 330, tz_name: str = "Asia/Kolkata") -> list:
    encoded = urllib.parse.quote(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range={range_str}&interval={interval}"
    raw = None
    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as e:
            last_err = e
            time.sleep(0.15 * (attempt + 1))
    if raw is None:
        raise RuntimeError(f"Failed fetching {symbol}: {last_err}")
    res = raw["chart"]["result"][0]
    ts = res.get("timestamp", [])
    q = res["indicators"]["quote"][0]
    tz_obj = _get_market_tz(tz_name, tz_offset_minutes)
    bars = []
    for i in range(len(ts)):
        c = q["close"][i]
        o = q["open"][i]
        h = q["high"][i]
        l = q["low"][i]
        v = q["volume"][i] if "volume" in q and q["volume"] else 0
        if c is None or o is None or h is None or l is None:
            continue
        dt_utc = dt.datetime.fromtimestamp(ts[i], dt.timezone.utc)
        dt_loc = dt_utc.astimezone(tz_obj)
        bars.append({
            "timestamp": ts[i],
            "date": dt_loc.strftime("%Y-%m-%d"),
            "datetime": dt_loc.strftime("%Y-%m-%d %H:%M"),
            "open": round(float(o), 4),
            "high": round(float(h), 4),
            "low": round(float(l), 4),
            "close": round(float(c), 4),
            "volume": int(v) if v is not None else 0,
        })
    return bars


def fetch_or_load_data(universe: dict, data_dir: str, reuse_data: bool = False):
    daily_path = os.path.join(data_dir, "daily_2y.json")
    weekly_path = os.path.join(data_dir, "weekly_5y.json")
    hourly_path = os.path.join(data_dir, "hourly_60d.json")
    primary_key = universe["primary_index"]

    if reuse_data and os.path.exists(daily_path) and os.path.exists(hourly_path):
        with open(daily_path, "r", encoding="utf-8") as f:
            daily_data = json.load(f)
        if primary_key in daily_data:
            print(f"[market-quant] Reusing cached OHLCV datasets from {data_dir} (verified {primary_key})")
            if os.path.exists(weekly_path):
                with open(weekly_path, "r", encoding="utf-8") as f:
                    weekly_data = json.load(f)
            else:
                weekly_data = {}
            with open(hourly_path, "r", encoding="utf-8") as f:
                hourly_data = json.load(f)
            return daily_data, weekly_data, hourly_data, {"cache_reused": True, "failed_daily": [], "failed_hourly": []}
        else:
            print(f"[market-quant] Cached dataset does not contain {primary_key}; fetching fresh universe data...")

    is_india = "Nifty" in primary_key
    tz_offset = 330 if is_india else -240
    tz_name = "Asia/Kolkata" if is_india else "America/New_York"
    all_map = {}
    all_map.update(universe["indices"])
    all_map.update(universe["etfs"])
    for st in universe["stocks"]:
        clean_key = st.replace(".NS", "").replace(".BO", "")
        all_map[f"STK_{clean_key}"] = st

    print(f"[market-quant] Downloading 2Y daily, 5Y weekly, and 60D 1H bars for {len(all_map)} symbols via Yahoo v8...")
    daily_data = {}
    weekly_data = {}
    failed_daily = []
    failed_hourly = []
    for name, sym in all_map.items():
        try:
            bars = fetch_yahoo_v8(sym, range_str="2y", interval="1d", tz_offset_minutes=tz_offset, tz_name=tz_name)
            if bars:
                daily_data[name] = {"symbol": sym, "bars": bars}
            else:
                failed_daily.append({"name": name, "symbol": sym, "reason": "empty_bars"})
            time.sleep(0.03)
        except Exception as e:
            failed_daily.append({"name": name, "symbol": sym, "reason": str(e)})
            print(f"  [WARN Daily] {name} ({sym}): {e}")
        try:
            w_bars = fetch_yahoo_v8(sym, range_str="5y", interval="1wk", tz_offset_minutes=tz_offset, tz_name=tz_name)
            if w_bars:
                weekly_data[name] = w_bars
            time.sleep(0.02)
        except Exception:
            pass

    hourly_keys = [
        universe["primary_index"],
        universe["secondary_index"],
        universe["vix_key"],
    ] + list(universe["etfs"].keys())[:5]
    hourly_data = {}
    for k in hourly_keys:
        if k in all_map:
            try:
                h_bars = fetch_yahoo_v8(all_map[k], range_str="60d", interval="1h", tz_offset_minutes=tz_offset, tz_name=tz_name)
                if h_bars:
                    hourly_data[k] = h_bars
                else:
                    failed_hourly.append({"name": k, "symbol": all_map[k], "reason": "empty_bars"})
            except Exception as e:
                failed_hourly.append({"name": k, "symbol": all_map[k], "reason": str(e)})
                print(f"  [WARN Hourly] {k}: {e}")

    with open(daily_path, "w", encoding="utf-8") as f:
        json.dump(daily_data, f)
    with open(weekly_path, "w", encoding="utf-8") as f:
        json.dump(weekly_data, f)
    with open(hourly_path, "w", encoding="utf-8") as f:
        json.dump(hourly_data, f)

    return daily_data, weekly_data, hourly_data, {
        "cache_reused": False,
        "failed_daily": failed_daily,
        "failed_hourly": failed_hourly,
    }


def dict_to_df(d, asof_date: str = "") -> pd.DataFrame:
    if isinstance(d, dict) and "bars" in d:
        rows = d["bars"]
    elif isinstance(d, list):
        rows = d
    else:
        rows = d
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    col_map = {c: c.capitalize() for c in df.columns if c.lower() in ("open", "high", "low", "close", "volume", "date", "datetime")}
    df = df.rename(columns=col_map)
    date_col = "Datetime" if "Datetime" in df.columns else ("Date" if "Date" in df.columns else df.columns[0])
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col).sort_index()
    if asof_date:
        cutoff = pd.to_datetime(asof_date + " 23:59:59")
        df = df[df.index <= cutoff]
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = 0.0
    return df.dropna(subset=["Close"])


# ---------------------------------------------------------------------------
# CORE ANALYSIS PIPELINE
# ---------------------------------------------------------------------------

def analyze_single_asset(name: str, df_d: pd.DataFrame, df_w: pd.DataFrame = None, is_index: bool = False) -> dict:
    if len(df_d) < 55:
        return {}
    c = df_d["Close"]
    h = df_d["High"]
    l = df_d["Low"]
    o = df_d["Open"]
    v = df_d["Volume"].fillna(0)

    sma20 = c.rolling(20).mean()
    sma50 = c.rolling(50).mean()
    sma200 = c.rolling(200).mean()
    rsi14 = wilder_rsi(c, 14)
    adx14, pdi14, mdi14, atr14 = compute_adx_dmi(h, l, c, 14)

    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd_hist = (ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()

    bb_std = c.rolling(20).std()
    bb_width = ((4.0 * bb_std) / sma20) * 100.0
    bb_w_rank = float((bb_width.iloc[-252:] < bb_width.iloc[-1]).mean() * 100.0) if len(bb_width.dropna()) >= 60 else float("nan")

    # Volume-Quality Gate for CMF-20 and Up/Down Volume Ratio
    v_last20 = v.iloc[-20:]
    nonzero_vol_days_20d = int((v_last20 > 0).sum())
    median_vol_20d = float(v_last20.median()) if len(v_last20) > 0 else 0.0
    cmf20_valid = bool(
        nonzero_vol_days_20d >= SIGNAL_SPEC["cmf_min_nonzero_vol_days_20d"]
        and median_vol_20d > 0
        and not is_index
    )
    # Note: some indices on Yahoo report aggregate constituent volume; record raw index CMF separately if non-zero
    cmf20_ser = chaikin_money_flow(h, l, c, v, 20)
    raw_cmf20 = round(float(cmf20_ser.iloc[-1]), 3) if not np.isnan(cmf20_ser.iloc[-1]) else None
    cmf20_val = raw_cmf20 if (cmf20_valid or (nonzero_vol_days_20d >= 17 and median_vol_20d > 0)) else None

    ret = c.pct_change()
    up_vol = v.where(ret > 0, 0.0).rolling(20).sum()
    dn_vol = v.where(ret < 0, 0.0).rolling(20).sum()
    ud_vol_ratio = float((up_vol / dn_vol.replace(0, np.nan)).iloc[-1]) if (v.sum() > 0 and nonzero_vol_days_20d >= 17) else float("nan")
    rvol_20v100 = float((v.rolling(20).mean() / v.rolling(100).mean().replace(0, np.nan)).iloc[-1]) if (v.sum() > 0 and nonzero_vol_days_20d >= 17) else float("nan")

    rv20 = float(np.log(c / c.shift(1)).rolling(20).std().iloc[-1] * np.sqrt(252) * 100.0)
    rv60 = float(np.log(c / c.shift(1)).rolling(60).std().iloc[-1] * np.sqrt(252) * 100.0)
    h60, h60_se = hurst_with_se(np.log(c.iloc[-60:].values), max_lag=15)
    h120, _ = hurst_with_se(np.log(c.iloc[-120:].values), max_lag=22)
    h_rs60 = hurst_rs_exponent(np.log(c.iloc[-90:].values))
    h_zscore = abs(h60 - 0.50) / h60_se if (not np.isnan(h60) and not np.isnan(h60_se) and h60_se > 1e-6) else 0.0
    hurst_usable = bool(h_zscore >= SIGNAL_SPEC["hurst_min_zscore"])
    if np.isnan(h60):
        hurst_regime = "unknown"
    elif h60 < SIGNAL_SPEC["hurst_anti_persistent_max"]:
        hurst_regime = "anti_persistent_mean_reverting"
    elif h60 > SIGNAL_SPEC["hurst_persistent_min"]:
        hurst_regime = "persistent_trend"
    else:
        hurst_regime = "random_walk_noise"

    wk_rsi = float(wilder_rsi(df_w["Close"], 14).iloc[-1]) if (df_w is not None and len(df_w) >= 20) else float("nan")
    vp = compute_volume_profile(df_d, lookback=120, bins=24) if nonzero_vol_days_20d >= 10 else {}
    cycles = dominant_fft_cycles(c.iloc[-252:], top_n=2)

    last_c = float(c.iloc[-1])
    high_52w = float(h.iloc[-252:].max())
    low_52w = float(l.iloc[-252:].min())

    def pct_ret(days):
        return round(float((last_c / float(c.iloc[-1 - days]) - 1.0) * 100.0), 2) if len(c) > days else None

    return {
        "name": name,
        "last_date": str(df_d.index[-1])[:10],
        "close": round(last_c, 2),
        "ret_1w_pct": pct_ret(5),
        "ret_1m_pct": pct_ret(21),
        "ret_3m_pct": pct_ret(63),
        "ret_6m_pct": pct_ret(126),
        "ret_1y_pct": pct_ret(252),
        "dist_52w_high_pct": round((last_c / high_52w - 1.0) * 100.0, 2),
        "dist_52w_low_pct": round((last_c / low_52w - 1.0) * 100.0, 2),
        "dist_sma20_pct": round((last_c / float(sma20.iloc[-1]) - 1.0) * 100.0, 2) if not np.isnan(sma20.iloc[-1]) else None,
        "dist_sma50_pct": round((last_c / float(sma50.iloc[-1]) - 1.0) * 100.0, 2) if not np.isnan(sma50.iloc[-1]) else None,
        "dist_sma200_pct": round((last_c / float(sma200.iloc[-1]) - 1.0) * 100.0, 2) if not np.isnan(sma200.iloc[-1]) else None,
        "rsi14_d": round(float(rsi14.iloc[-1]), 2) if not np.isnan(rsi14.iloc[-1]) else None,
        "rsi14_w": round(wk_rsi, 2) if not np.isnan(wk_rsi) else None,
        "adx14": round(float(adx14.iloc[-1]), 2) if not np.isnan(adx14.iloc[-1]) else None,
        "plus_di14": round(float(pdi14.iloc[-1]), 2) if not np.isnan(pdi14.iloc[-1]) else None,
        "minus_di14": round(float(mdi14.iloc[-1]), 2) if not np.isnan(mdi14.iloc[-1]) else None,
        "macd_hist": round(float(macd_hist.iloc[-1]), 3) if not np.isnan(macd_hist.iloc[-1]) else None,
        "bb_width_pct": round(float(bb_width.iloc[-1]), 2) if not np.isnan(bb_width.iloc[-1]) else None,
        "bb_width_1y_percentile": round(bb_w_rank, 1) if not np.isnan(bb_w_rank) else None,
        "rv20_ann_pct": round(rv20, 2) if not np.isnan(rv20) else None,
        "rv60_ann_pct": round(rv60, 2) if not np.isnan(rv60) else None,
        "cmf20": cmf20_val,
        "cmf20_cash_verified": cmf20_valid,
        "nonzero_vol_days_20d": nonzero_vol_days_20d,
        "up_down_vol_ratio_20d": round(ud_vol_ratio, 2) if not np.isnan(ud_vol_ratio) else None,
        "rvol_20d_vs_100d": round(rvol_20v100, 2) if not np.isnan(rvol_20v100) else None,
        "hurst_60d": round(h60, 3) if not np.isnan(h60) else None,
        "hurst_60d_se": round(h60_se, 3) if not np.isnan(h60_se) else None,
        "hurst_rs_60d": round(h_rs60, 3) if not np.isnan(h_rs60) else None,
        "hurst_usable": hurst_usable,
        "hurst_regime": hurst_regime,
        "hurst_120d": round(h120, 3) if not np.isnan(h120) else None,
        "fft_cycles": cycles,
        "volume_profile_120d": vp,
    }


def analyze_intraday_clock(hourly_data: dict, primary_key: str, secondary_key: str, vix_key: str, open_slot: str = "09:15", close_slot: str = "15:15", asof_date: str = ""):
    series_out = {}
    slots_out = {}
    is_india = open_slot == "09:15"
    # Final active institutional execution window starts at 14:15 IST (India) or 15:00 ET (US)
    close_window_start = "14:15" if is_india else "15:00"

    for key in [primary_key, secondary_key, vix_key]:
        if key not in hourly_data:
            continue
        raw_h = hourly_data[key]
        rows = raw_h["bars"] if isinstance(raw_h, dict) and "bars" in raw_h else raw_h
        df = pd.DataFrame(rows)
        if df.empty:
            continue
        col_map = {c: c.capitalize() for c in df.columns if c.lower() in ("open", "high", "low", "close", "volume", "date", "datetime")}
        df = df.rename(columns=col_map)
        date_col = "Datetime" if "Datetime" in df.columns else ("Date" if "Date" in df.columns else df.columns[0])
        dt_ser = pd.to_datetime(df[date_col])
        df["dt_local"] = dt_ser
        if asof_date:
            df = df[df["dt_local"] <= pd.to_datetime(asof_date + " 23:59:59")]
        df["day"] = df["dt_local"].dt.strftime("%Y-%m-%d")
        df["slot"] = df["dt_local"].dt.strftime("%H:%M")
        for c in ["Open", "High", "Low", "Close", "Volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce") if c in df.columns else 0.0
        df = df.dropna(subset=["Close"]).sort_values("dt_local")

        # Filter out flat zero-volume terminal quote markers (e.g., NSE 15:30 quote row where High == Low and Volume == 0)
        is_flat_terminal_quote = (df["slot"] > close_slot) & ((df["High"] - df["Low"]).abs() <= 1e-6) & (df["Volume"] <= 0)
        df = df[~is_flat_terminal_quote].copy()
        df["bar_ret_pct"] = (df["Close"] / df["Open"] - 1.0) * 100.0

        slot_stats = []
        for sl, grp in df.groupby("slot"):
            if len(grp) < 10:
                continue
            r_dec = grp["bar_ret_pct"] / 100.0
            comp_ret = float((np.prod(1.0 + r_dec.values) - 1.0) * 100.0)
            slot_stats.append({
                "slot": sl,
                "count": int(len(grp)),
                "mean_ret_pct": round(float(grp["bar_ret_pct"].mean()), 4),
                "cum_ret_pct": round(float(grp["bar_ret_pct"].sum()), 2),
                "compounded_ret_pct": round(comp_ret, 2),
                "win_rate_pct": round(float((grp["bar_ret_pct"] > 0).mean() * 100.0), 1),
                "avg_range_pct": round(float(((grp["High"] - grp["Low"]) / grp["Open"] * 100.0).mean()), 3),
            })
        slots_out[key] = sorted(slot_stats, key=lambda x: x["slot"])

        # Daily session decomposition: Overnight Gap vs Opening Hour vs Mid-Session vs Closing Window
        daily_rows = []
        prev_close = None
        for day, grp in df.groupby("day"):
            grp = grp.sort_values("dt_local")
            first_bar = grp.iloc[0]
            day_open = float(first_bar["Open"])
            day_close = float(grp.iloc[-1]["Close"])
            overnight_gap = (day_open / prev_close - 1.0) * 100.0 if prev_close else 0.0

            open_bars = grp[grp["slot"] <= open_slot]
            if open_bars.empty:
                open_bars = grp.iloc[:1]
            open_end_price = float(open_bars.iloc[-1]["Close"])
            open_hr = (open_end_price / day_open - 1.0) * 100.0

            close_bars = grp[grp["slot"] >= close_window_start]
            if close_bars.empty and len(grp) > 1:
                close_bars = grp.iloc[-1:]
            if not close_bars.empty:
                close_start_price = float(close_bars.iloc[0]["Open"])
                close_hr = (day_close / close_start_price - 1.0) * 100.0
            else:
                close_start_price = day_close
                close_hr = 0.0

            mid_bars = grp[(grp["slot"] > open_slot) & (grp["slot"] < close_window_start)]
            if not mid_bars.empty:
                mid_ret = (float(mid_bars.iloc[-1]["Close"]) / float(mid_bars.iloc[0]["Open"]) - 1.0) * 100.0
            else:
                mid_ret = (close_start_price / open_end_price - 1.0) * 100.0 if open_end_price > 0 else 0.0

            intraday_ret = (day_close / day_open - 1.0) * 100.0
            total_ret = (day_close / prev_close - 1.0) * 100.0 if prev_close else intraday_ret
            prev_close = day_close

            daily_rows.append({
                "day": day,
                "overnight_gap": overnight_gap,
                "open_hr": open_hr,
                "mid_session": mid_ret,
                "close_hr": close_hr,
                "intraday_only": intraday_ret,
                "total": total_ret,
            })
        ddf = pd.DataFrame(daily_rows)
        if not ddf.empty:
            def _comp_curve(series_pct):
                return ((1.0 + series_pct / 100.0).cumprod() - 1.0) * 100.0

            series_out[key] = {
                "days": ddf["day"].tolist(),
                "close_window_start_slot": close_window_start,
                "cum_overnight_gap": np.cumsum(ddf["overnight_gap"]).round(2).tolist(),
                "cum_open_hr": np.cumsum(ddf["open_hr"]).round(2).tolist(),
                "cum_mid_session": np.cumsum(ddf["mid_session"]).round(2).tolist(),
                "cum_close_hr": np.cumsum(ddf["close_hr"]).round(2).tolist(),
                "cum_intraday_only": np.cumsum(ddf["intraday_only"]).round(2).tolist(),
                "cum_total": np.cumsum(ddf["total"]).round(2).tolist(),
                "compounded_overnight_gap": _comp_curve(ddf["overnight_gap"]).round(2).tolist(),
                "compounded_open_hr": _comp_curve(ddf["open_hr"]).round(2).tolist(),
                "compounded_mid_session": _comp_curve(ddf["mid_session"]).round(2).tolist(),
                "compounded_close_hr": _comp_curve(ddf["close_hr"]).round(2).tolist(),
                "compounded_total": _comp_curve(ddf["total"]).round(2).tolist(),
            }

    return {"slots": slots_out, "cumulative": series_out}


# ---------------------------------------------------------------------------
# CHART & HTML ARTIFACT GENERATORS
# ---------------------------------------------------------------------------

def render_intraday_clock_png(clock_data: dict, primary_key: str, secondary_key: str, vix_key: str, out_png: str, date_label: str):
    slots = clock_data.get("slots", {})
    cum = clock_data.get("cumulative", {})
    if primary_key not in cum or primary_key not in slots:
        return

    fig = plt.figure(figsize=(16, 10.5), dpi=240, facecolor="#f7f4ef")
    gs = fig.add_gridspec(2, 2, hspace=0.35, wspace=0.24, left=0.06, right=0.96, top=0.88, bottom=0.07)

    fig.suptitle(f"INTRADAY SMART-MONEY CLOCK & VOLATILITY CRUSH ({date_label})", fontsize=15, fontweight="bold", color="#242424", y=0.955)
    fig.text(0.5, 0.92, f"60-Day 1-Hour Session Decomposition: {primary_key} • {secondary_key} • {vix_key}", ha="center", fontsize=10.5, color="#5c5c5c")

    # Panel A: Primary Index Cumulative Session Curves
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor("#ffffff")
    p_cum = cum[primary_key]
    x = np.arange(len(p_cum["days"]))
    ax1.plot(x, p_cum["cum_close_hr"], color="#16a34a", linewidth=2.5, label=f"Closing Hour ({p_cum['cum_close_hr'][-1]:+.2f}%)")
    ax1.plot(x, p_cum["cum_mid_session"], color="#0078d4", linewidth=1.8, linestyle="--", label=f"Mid-Day Drift ({p_cum['cum_mid_session'][-1]:+.2f}%)")
    ax1.plot(x, p_cum["cum_open_hr"], color="#dc2626", linewidth=2.2, label=f"Opening Hour ({p_cum['cum_open_hr'][-1]:+.2f}%)")
    ax1.plot(x, p_cum["cum_total"], color="#242424", linewidth=1.4, alpha=0.7, label=f"Net Total ({p_cum['cum_total'][-1]:+.2f}%)")
    ax1.axhline(0, color="#919191", linewidth=0.8)
    step = max(1, len(x) // 6)
    ax1.set_xticks(x[::step])
    ax1.set_xticklabels([d[5:] for d in p_cum["days"][::step]], fontsize=8)
    ax1.set_title(f"A. {primary_key}: Cumulative 60D Return by Intraday Window", fontsize=11, fontweight="bold", color="#242424")
    ax1.set_ylabel("Cumulative Return (%)", fontsize=9, color="#5c5c5c")
    ax1.legend(loc="best", fontsize=8, framealpha=0.92)
    ax1.grid(True, linestyle=":", alpha=0.45)

    # Panel B: Hourly Bar Return Profile
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor("#ffffff")
    p_slots = slots[primary_key]
    s_labels = [s["slot"] for s in p_slots]
    s_vals = [s["cum_ret_pct"] for s in p_slots]
    s_wins = [s["win_rate_pct"] for s in p_slots]
    colors = ["#16a34a" if v >= 0 else "#dc2626" for v in s_vals]
    bars = ax2.bar(np.arange(len(s_labels)), s_vals, color=colors, width=0.58, edgecolor="#242424", linewidth=0.7)
    ax2.axhline(0, color="#242424", linewidth=0.9)
    for b, v, w in zip(bars, s_vals, s_wins):
        off = 0.15 if v >= 0 else -0.35
        ax2.text(b.get_x() + b.get_width() / 2, v + off, f"{v:+.2f}%\n({w:.0f}%W)", ha="center", va="bottom" if v >= 0 else "top", fontsize=7.5, fontweight="bold")
    ax2.set_xticks(np.arange(len(s_labels)))
    ax2.set_xticklabels(s_labels, fontsize=8.5, fontweight="bold")
    ax2.set_ylim(min(s_vals) - 1.6, max(s_vals) + 1.6)
    ax2.set_title(f"B. {primary_key} Hourly Clock: 60D Cumulative Return & Win Rate", fontsize=11, fontweight="bold", color="#242424")
    ax2.set_ylabel("60D Sum of Bar Returns (%)", fontsize=9, color="#5c5c5c")
    ax2.grid(True, axis="y", linestyle=":", alpha=0.45)

    # Panel C: VIX Hourly Profile
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.set_facecolor("#ffffff")
    if vix_key in slots and len(slots[vix_key]) > 0:
        v_slots = slots[vix_key]
        vl = [s["slot"] for s in v_slots]
        vv = [s["cum_ret_pct"] for s in v_slots]
        vw = [s["win_rate_pct"] for s in v_slots]
        vc = ["#f59e0b" if v >= 0 else "#16a34a" for v in vv]
        vbars = ax3.bar(np.arange(len(vl)), vv, color=vc, width=0.58, edgecolor="#242424", linewidth=0.7)
        ax3.axhline(0, color="#242424", linewidth=0.9)
        for b, v, w in zip(vbars, vv, vw):
            off = 0.8 if v >= 0 else -1.2
            ax3.text(b.get_x() + b.get_width() / 2, v + off, f"{v:+.1f}%\n({w:.0f}%↑)", ha="center", va="bottom" if v >= 0 else "top", fontsize=7.5, fontweight="bold")
        ax3.set_xticks(np.arange(len(vl)))
        ax3.set_xticklabels(vl, fontsize=8.5, fontweight="bold")
        ax3.set_ylim(min(vv) - 11.0, max(vv) + 12.0)
    ax3.set_title(f"C. {vix_key} Hourly Clock: Morning Spike vs Afternoon VIX Crush", fontsize=11, fontweight="bold", color="#242424")
    ax3.set_ylabel("60D Cumulative VIX Change (%)", fontsize=9, color="#5c5c5c")
    ax3.grid(True, axis="y", linestyle=":", alpha=0.45)

    # Panel D: Secondary Index Session Comparison
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.set_facecolor("#ffffff")
    if secondary_key in cum:
        s_cum = cum[secondary_key]
        xs = np.arange(len(s_cum["days"]))
        ax4.plot(xs, s_cum["cum_close_hr"], color="#16a34a", linewidth=2.5, label=f"Closing Hour ({s_cum['cum_close_hr'][-1]:+.2f}%)")
        ax4.plot(xs, s_cum["cum_mid_session"], color="#0078d4", linewidth=1.8, linestyle="--", label=f"Mid-Day Drift ({s_cum['cum_mid_session'][-1]:+.2f}%)")
        ax4.plot(xs, s_cum["cum_open_hr"], color="#dc2626", linewidth=2.2, label=f"Opening Hour ({s_cum['cum_open_hr'][-1]:+.2f}%)")
        ax4.axhline(0, color="#919191", linewidth=0.8)
        ax4.set_xticks(xs[::step])
        ax4.set_xticklabels([d[5:] for d in s_cum["days"][::step]], fontsize=8)
        ax4.legend(loc="best", fontsize=8, framealpha=0.92)
    ax4.set_title(f"D. {secondary_key}: Opening Liquidation vs Closing Institutional Bid", fontsize=11, fontweight="bold", color="#242424")
    ax4.set_ylabel("Cumulative Return (%)", fontsize=9, color="#5c5c5c")
    ax4.grid(True, linestyle=":", alpha=0.45)

    fig.savefig(out_png, dpi=300)
    plt.close(fig)


def render_social_infographic_png(idx_list: list, stk_list: list, fft_proj: dict, primary_key: str, out_png: str, date_label: str):
    stk_df = pd.DataFrame([s for s in stk_list if s.get("cmf20") is not None and s.get("rsi14_d") is not None])
    idx_df = pd.DataFrame([i for i in idx_list if i.get("cmf20") is not None or i.get("hurst_60d") is not None])

    fig = plt.figure(figsize=(16.5, 11.5), dpi=240, facecolor="#f7f4ef")
    gs = fig.add_gridspec(2, 2, hspace=0.36, wspace=0.27, left=0.055, right=0.955, top=0.87, bottom=0.07)

    fig.suptitle(f"BEYOND CANDLESTICKS: 4 HIDDEN QUANTITATIVE SIGNALS ({date_label})", fontsize=15.5, fontweight="bold", color="#242424", y=0.955)
    fig.text(0.5, 0.918, "Multi-Factor Microstructure Scan: Chaikin Money Flow (CLV×Vol) vs RSI(14) • Spot vs ETF Order Flow • Hurst Fractal Regime • FFT Harmonic Wave", ha="center", fontsize=10.2, color="#5c5c5c")

    # Panel A: RSI(14) vs CMF(20)
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor("#ffffff")
    rsi_split = SIGNAL_SPEC["bull_trap_min_rsi"]
    if not stk_df.empty:
        ax1.axvline(rsi_split, color="#5c5c5c", linestyle="--", linewidth=1.0, alpha=0.7)
        ax1.axhline(0.0, color="#5c5c5c", linestyle="--", linewidth=1.0, alpha=0.7)
        ax1.axvspan(rsi_split, 85, ymin=0.0, ymax=0.52, color="#dc2626", alpha=0.06)
        ax1.axvspan(20, rsi_split, ymin=0.52, ymax=1.0, color="#16a34a", alpha=0.06)
        ax1.axvspan(rsi_split, 85, ymin=0.52, ymax=1.0, color="#0078d4", alpha=0.06)

        for _, r in stk_df.iterrows():
            ud_val = r.get("up_down_vol_ratio_20d") or 1.0
            col = "#0078d4" if (r["rsi14_d"] >= rsi_split and r["cmf20"] >= SIGNAL_SPEC["true_breakout_min_cmf"]) else (
                "#dc2626" if (r["rsi14_d"] >= rsi_split and r["cmf20"] <= SIGNAL_SPEC["bull_trap_max_cmf"]) else (
                "#16a34a" if (r["rsi14_d"] < rsi_split and r["cmf20"] >= SIGNAL_SPEC["stealth_accum_min_cmf"] and ud_val >= SIGNAL_SPEC["stealth_accum_min_ud_vol"]) else (
                "#d63939" if r["cmf20"] <= SIGNAL_SPEC["heavy_dist_max_cmf"] else "#7a7a7a")))
            sz = max(35, min(220, ud_val * 65))
            ax1.scatter(r["rsi14_d"], r["cmf20"], s=sz, color=col, alpha=0.88, edgecolors="#242424", linewidth=0.7, zorder=4)

        # Label extreme outliers automatically without overlap
        extremes = pd.concat([
            stk_df.nlargest(2, "cmf20"),
            stk_df.nsmallest(2, "cmf20"),
            stk_df[stk_df["rsi14_d"] >= rsi_split].nsmallest(2, "cmf20"),
        ]).drop_duplicates(subset=["name"])
        placed = []
        for i_row, (_, r) in enumerate(extremes.iterrows()):
            dy = 9 if r["cmf20"] >= 0 else -13
            dx = -35 if r["rsi14_d"] > 62 else 8
            for px, py in placed:
                if abs(r["rsi14_d"] - px) < 6.0 and abs(r["cmf20"] - py) < 0.06:
                    dx = -68
                    dy = 6 if dy < 0 else -14
            placed.append((r["rsi14_d"], r["cmf20"]))
            ax1.annotate(f"{r['name'].replace('STK_','')} ({r['cmf20']:+.2f})", (r["rsi14_d"], r["cmf20"]),
                         xytext=(dx, dy), textcoords="offset points", fontsize=7.4, fontweight="bold",
                         bbox=dict(boxstyle="round,pad=0.2", fc="#fcfbf8", ec="#dedede", lw=0.6), zorder=6)
        ax1.set_ylim(float(stk_df["cmf20"].min()) - 0.07, float(stk_df["cmf20"].max()) + 0.07)
        ax1.set_xlim(max(15.0, float(stk_df["rsi14_d"].min()) - 6.0), min(88.0, float(stk_df["rsi14_d"].max()) + 8.0))

    ax1.set_title("A. The 'RSI Lie': Momentum RSI(14) vs Institutional Money Flow CMF(20)", fontsize=11, fontweight="bold")
    ax1.set_xlabel("14-Day Wilder RSI (Close-to-Close Momentum)", fontsize=9)
    ax1.set_ylabel("20-Day Chaikin Money Flow (CLV × Vol)", fontsize=9)
    ax1.grid(True, linestyle=":", alpha=0.45)

    # Panel B: Benchmark & ETF CMF Bar Ranking
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor("#ffffff")
    cmf_sub = idx_df.dropna(subset=["cmf20"]).copy()
    if not cmf_sub.empty:
        cmf_sub = pd.concat([cmf_sub.nlargest(4, "cmf20"), cmf_sub.nsmallest(5, "cmf20")]).drop_duplicates(subset=["name"]).sort_values("cmf20")
        y_pos = np.arange(len(cmf_sub))
        b_cols = ["#16a34a" if v >= 0 else "#dc2626" for v in cmf_sub["cmf20"]]
        bars = ax2.barh(y_pos, cmf_sub["cmf20"], color=b_cols, height=0.6, edgecolor="#242424", linewidth=0.6)
        ax2.axvline(0, color="#242424", linewidth=1.0)
        for bar, v in zip(bars, cmf_sub["cmf20"]):
            off = 0.012 if v >= 0 else -0.012
            ax2.text(v + off, bar.get_y() + bar.get_height() / 2, f"{v:+.3f}", va="center", ha="left" if v >= 0 else "right", fontsize=8, fontweight="bold")
        ax2.set_yticks(y_pos)
        ax2.set_yticklabels(cmf_sub["name"].tolist(), fontsize=8.5, fontweight="bold")
        ax2.set_xlim(min(-0.48, float(cmf_sub["cmf20"].min()) - 0.08), max(0.35, float(cmf_sub["cmf20"].max()) + 0.08))
    ax2.set_title("B. Spot Index vs Real-Money ETF Order Flow (20D CMF)", fontsize=11, fontweight="bold")
    ax2.set_xlabel("20-Day Chaikin Money Flow (+ = Accumulation, - = Distribution)", fontsize=8.5)
    ax2.grid(True, axis="x", linestyle=":", alpha=0.45)

    # Panel C: Hurst Exponent vs 1Y Bollinger Bandwidth Percentile
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.set_facecolor("#ffffff")
    h_sub = idx_df.dropna(subset=["hurst_60d", "bb_width_1y_percentile"]).copy()
    if not h_sub.empty:
        ax3.axvline(SIGNAL_SPEC["hurst_anti_persistent_max"], color="#dc2626", linestyle=":", linewidth=1.0, alpha=0.7)
        ax3.axvline(SIGNAL_SPEC["hurst_persistent_min"], color="#16a34a", linestyle=":", linewidth=1.0, alpha=0.7)
        ax3.axhline(SIGNAL_SPEC["bbw_squeeze_max_pct"], color="#f59e0b", linestyle="--", linewidth=1.0, alpha=0.7)
        ax3.axhspan(0, SIGNAL_SPEC["bbw_squeeze_max_pct"], color="#f59e0b", alpha=0.08)
        for _, r in h_sub.iterrows():
            col = "#16a34a" if r["hurst_60d"] >= SIGNAL_SPEC["hurst_persistent_min"] else (
                "#f59e0b" if r["bb_width_1y_percentile"] <= SIGNAL_SPEC["bbw_squeeze_max_pct"] else (
                "#dc2626" if r["hurst_60d"] <= SIGNAL_SPEC["hurst_anti_persistent_max"] else "#6b7280"))
            ax3.scatter(r["hurst_60d"], r["bb_width_1y_percentile"], s=95, color=col, edgecolors="#242424", linewidth=0.8, zorder=4)

        label_picks = pd.concat([
            h_sub[h_sub["name"].isin([primary_key, "BankNifty", "NiftyBees", "NiftyIT"])],
            h_sub.nlargest(2, "hurst_60d"),
            h_sub.nsmallest(2, "hurst_60d"),
            h_sub.nsmallest(2, "bb_width_1y_percentile"),
        ]).drop_duplicates(subset=["name"])
        offsets = [(7, 6), (7, -11), (-48, 8), (7, 5), (-52, -11), (7, -10), (-45, 7), (7, 6), (-45, -10)]
        for idx_l, (_, r) in enumerate(label_picks.iterrows()):
            ox, oy = offsets[idx_l % len(offsets)]
            if r["hurst_60d"] > 0.50:
                ox = -58
            ax3.annotate(
                f"{r['name']} (H={r['hurst_60d']:.2f})",
                (r["hurst_60d"], r["bb_width_1y_percentile"]),
                xytext=(ox, oy),
                textcoords="offset points",
                fontsize=7.2,
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.18", fc="#fcfbf8", ec="#dedede", lw=0.6),
                zorder=6,
            )
        ax3.set_xlim(max(0.08, float(h_sub["hurst_60d"].min()) - 0.04), min(0.66, float(h_sub["hurst_60d"].max()) + 0.06))
        ax3.set_ylim(-2, 105)
    ax3.set_title("C. Fractal Hurst Exponent (H) vs 1Y Bollinger Bandwidth Percentile", fontsize=11, fontweight="bold")
    ax3.set_xlabel("60-Day Hurst Exponent (H < 0.45 = Mean-Reverting | 0.45-0.55 = Walk | H > 0.55 = Trend)", fontsize=8.5)
    ax3.set_ylabel("1-Year Bollinger BandWidth Percentile (%)", fontsize=9)
    ax3.grid(True, linestyle=":", alpha=0.45)

    # Panel D: FFT Harmonic Cycle & Projection
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.set_facecolor("#ffffff")
    if fft_proj and "close" in fft_proj:
        closes = np.array(fft_proj["close"])
        hist_w = np.array(fft_proj["harmonic_hist_pct"])
        fut_w = np.array(fft_proj["harmonic_future_pct"])
        n_h = len(closes)
        n_f = len(fut_w)
        x_h = np.arange(n_h)
        x_f = np.arange(n_h - 1, n_h + n_f)
        ax4.plot(x_h, closes, color="#242424", linewidth=1.8, label=f"{primary_key} Close (Left)")
        ax4_r = ax4.twinx()
        ax4_r.plot(x_h, hist_w, color="#0078d4", linewidth=2.1, label="FFT Harmonic Wave")
        ax4_r.plot(x_f, np.concatenate([[hist_w[-1]], fut_w]), color="#dc2626", linewidth=2.2, linestyle="--", label="25D Forward Projection")
        ax4_r.axhline(0, color="#919191", linestyle=":", linewidth=0.8)
        ax4_r.set_ylabel("Detrended Harmonic Cycle (%)", fontsize=9, color="#0078d4")
    rel_tag = "Reliable" if fft_proj.get("fft_reliable") else "Low-Var/Vol-Spike Watch"
    ax4.set_title(f"D. {primary_key} Dominant Fourier (FFT) Wave & 25D Projection ({rel_tag})", fontsize=11, fontweight="bold")
    ax4.grid(True, linestyle=":", alpha=0.45)

    fig.savefig(out_png, dpi=300)
    plt.close(fig)


# ---------------------------------------------------------------------------
# STRUCTURED ANOMALY EXTRACTOR
# ---------------------------------------------------------------------------

def extract_anomaly_summary(idx_list: list, stk_list: list, clock_data: dict, fft_proj: dict, primary_key: str) -> dict:
    stk_df = pd.DataFrame([s for s in stk_list if s.get("cmf20") is not None and s.get("rsi14_d") is not None])
    idx_df = pd.DataFrame(idx_list)

    rsi_min = SIGNAL_SPEC["bull_trap_min_rsi"]
    if not stk_df.empty:
        ud_col = stk_df["up_down_vol_ratio_20d"].fillna(1.0)
        # 1. Bull traps: High RSI (>=55) and negative CMF (<= -0.05)
        bull_traps = stk_df[(stk_df["rsi14_d"] >= rsi_min) & (stk_df["cmf20"] <= SIGNAL_SPEC["bull_trap_max_cmf"])].sort_values("cmf20").to_dict(orient="records")
        # 2. True Institutional Breakouts: High RSI (>=55) and strong positive CMF (>=0.10)
        true_breakouts = stk_df[(stk_df["rsi14_d"] >= rsi_min) & (stk_df["cmf20"] >= SIGNAL_SPEC["true_breakout_min_cmf"])].sort_values("cmf20", ascending=False).to_dict(orient="records")
        # 3. Stealth Accumulation: Moderate/Low RSI (<55), strong positive CMF (>=0.10), and Up/Down Volume >= 1.25x
        stealth_accum = stk_df[
            (stk_df["rsi14_d"] < SIGNAL_SPEC["stealth_accum_max_rsi"])
            & (stk_df["cmf20"] >= SIGNAL_SPEC["stealth_accum_min_cmf"])
            & (ud_col >= SIGNAL_SPEC["stealth_accum_min_ud_vol"])
        ].sort_values("cmf20", ascending=False).to_dict(orient="records")
        # 4. Heavy Institutional Liquidation: CMF <= -0.15
        heavy_dist = stk_df[stk_df["cmf20"] <= SIGNAL_SPEC["heavy_dist_max_cmf"]].sort_values("cmf20").to_dict(orient="records")
    else:
        bull_traps, true_breakouts, stealth_accum, heavy_dist = [], [], [], []

    # 5. Volatility Squeeze Coils (<= 20th percentile 1Y BBW)
    coils = idx_df[idx_df["bb_width_1y_percentile"].notna() & (idx_df["bb_width_1y_percentile"] <= SIGNAL_SPEC["bbw_squeeze_max_pct"])].sort_values("bb_width_1y_percentile").to_dict(orient="records") if not idx_df.empty else []
    # 6. Persistent Trend Leaders (Hurst >= 0.55)
    trend_leaders = idx_df[idx_df["hurst_60d"].notna() & (idx_df["hurst_60d"] >= SIGNAL_SPEC["hurst_persistent_min"])].sort_values("hurst_60d", ascending=False).to_dict(orient="records") if not idx_df.empty else []
    # 7. Anti-Persistent Mean-Reversion Regimes (Hurst <= 0.45)
    chop_regimes = idx_df[idx_df["hurst_60d"].notna() & (idx_df["hurst_60d"] <= SIGNAL_SPEC["hurst_anti_persistent_max"])].sort_values("hurst_60d").to_dict(orient="records") if not idx_df.empty else []

    # 8. Cross-sectional breadth & cash-constituent CMF benchmark
    n_tot = len(stk_df)
    constituent_equal_cmf20 = round(float(stk_df["cmf20"].mean()), 3) if n_tot else 0.0
    constituent_median_cmf20 = round(float(stk_df["cmf20"].median()), 3) if n_tot else 0.0
    breadth = {
        "total_constituents": n_tot,
        "pct_above_sma20": round(float((stk_df["dist_sma20_pct"] > 0).mean() * 100.0), 1) if n_tot else 0.0,
        "pct_above_sma50": round(float((stk_df["dist_sma50_pct"] > 0).mean() * 100.0), 1) if n_tot else 0.0,
        "pct_above_sma200": round(float((stk_df["dist_sma200_pct"] > 0).mean() * 100.0), 1) if n_tot else 0.0,
        "pct_positive_cmf20": round(float((stk_df["cmf20"] > 0).mean() * 100.0), 1) if n_tot else 0.0,
        "constituent_equal_cmf20": constituent_equal_cmf20,
        "constituent_median_cmf20": constituent_median_cmf20,
    }

    # 9. Spot vs ETF Order-Flow Divergences (Cash-Verified ETF CMF vs Spot Return & Constituent Cash CMF)
    spot_vs_etf = []
    pairs = [
        ("Nifty50", "NiftyBees"),
        ("BankNifty", "BankBees"),
        ("NiftyIT", "ITBees"),
        ("NiftyPharma", "PharmaBees"),
        ("NiftyAuto", "AutoBees"),
        ("NiftyPSUBank", "PSUBankBees"),
        ("SP500", "SPY"),
        ("Nasdaq100", "QQQ"),
    ]
    idx_map = {x["name"]: x for x in idx_list}
    for sp, etf in pairs:
        if sp in idx_map and etf in idx_map:
            s_obj = idx_map[sp]
            e_obj = idx_map[etf]
            s_cmf = s_obj.get("cmf20")
            e_cmf = e_obj.get("cmf20")
            if e_cmf is not None:
                ref_cmf = s_cmf if s_cmf is not None else constituent_equal_cmf20
                spot_ret_1m = s_obj.get("ret_1m_pct") or 0.0
                if spot_ret_1m >= 2.0 and e_cmf <= -0.10:
                    flow_regime = "spot_rally_vs_etf_distribution_divergence"
                elif e_cmf >= 0.10:
                    flow_regime = "real_money_etf_accumulation"
                elif e_cmf <= -0.10:
                    flow_regime = "real_money_etf_distribution"
                else:
                    flow_regime = "neutral_cash_flow"
                spot_vs_etf.append({
                    "spot": sp,
                    "etf": etf,
                    "spot_ret_1m_pct": spot_ret_1m,
                    "spot_rsi14": s_obj.get("rsi14_d"),
                    "spot_cmf20": s_cmf,
                    "spot_cmf20_note": "index_feed_volume" if s_cmf is not None else "no_cash_index_volume_use_constituent_or_etf",
                    "constituent_equal_cmf20": constituent_equal_cmf20,
                    "etf_cmf20": e_cmf,
                    "etf_cmf20_cash_verified": e_obj.get("cmf20_cash_verified", True),
                    "spread_etf_minus_spot": round(e_cmf - s_cmf, 3) if s_cmf is not None else None,
                    "spread_etf_minus_constituents": round(e_cmf - constituent_equal_cmf20, 3),
                    "flow_regime": flow_regime,
                    "etf_rsi14": e_obj.get("rsi14_d"),
                    "etf_hurst60": e_obj.get("hurst_60d"),
                })

    cmf_invalid_symbols = [
        x["name"] for x in (idx_list + stk_list) if x.get("cmf20") is None
    ]

    return {
        "primary_index": primary_key,
        "primary_index_snapshot": idx_map.get(primary_key),
        "signal_spec": SIGNAL_SPEC,
        "cmf_invalid_symbols": cmf_invalid_symbols,
        "breadth": breadth,
        "spot_vs_etf_divergences": spot_vs_etf,
        "bull_traps_high_rsi_neg_cmf": bull_traps[:8],
        "true_institutional_breakouts": true_breakouts[:8],
        "stealth_accumulation_gems": stealth_accum[:8],
        "heavy_institutional_liquidation": heavy_dist[:8],
        "volatility_squeeze_coils": coils,
        "persistent_trend_assets": trend_leaders,
        "anti_persistent_chop_assets": chop_regimes,
        "fft_harmonic_projection": {
            "selected_periods_days": fft_proj.get("selected_periods_days", []),
            "harmonic_variance_share_pct": fft_proj.get("harmonic_variance_share_pct"),
            "vol_regime_ratio_20v60": fft_proj.get("vol_regime_ratio_20v60"),
            "fft_reliable": fft_proj.get("fft_reliable"),
            "next_crest_trading_days": fft_proj.get("next_crest_trading_days"),
            "next_trough_trading_days": fft_proj.get("next_trough_trading_days"),
        },
        "intraday_clock_summary": clock_data.get("slots", {}),
        "intraday_cumulative_windows": {
            k: {
                "close_window_start_slot": v.get("close_window_start_slot"),
                "cum_overnight_gap_pct": v["cum_overnight_gap"][-1] if v.get("cum_overnight_gap") else None,
                "cum_open_hr_pct": v["cum_open_hr"][-1] if v.get("cum_open_hr") else None,
                "cum_mid_session_pct": v["cum_mid_session"][-1] if v.get("cum_mid_session") else None,
                "cum_close_hr_pct": v["cum_close_hr"][-1] if v.get("cum_close_hr") else None,
                "cum_total_pct": v["cum_total"][-1] if v.get("cum_total") else None,
                "compounded_open_hr_pct": v["compounded_open_hr"][-1] if v.get("compounded_open_hr") else None,
                "compounded_close_hr_pct": v["compounded_close_hr"][-1] if v.get("compounded_close_hr") else None,
                "compounded_total_pct": v["compounded_total"][-1] if v.get("compounded_total") else None,
            }
            for k, v in clock_data.get("cumulative", {}).items()
        },
    }


def _sanitize_json_value(obj):
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    if isinstance(obj, (np.floating,)):
        val = float(obj)
        return None if (np.isnan(val) or np.isinf(val)) else val
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_json_value(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_json_value(v) for v in obj]
    return obj


def _date_normalized_returns(d, asof_date: str = "") -> pd.Series:
    df = dict_to_df(d, asof_date=asof_date)
    if df.empty:
        return pd.Series(dtype=float)
    df = df.copy()
    df["cal_date"] = df.index.strftime("%Y-%m-%d")
    df = df.groupby("cal_date").last().sort_index()
    return df["Close"].pct_change().dropna()


def compute_macro_correlations(daily_data: dict, primary_key: str, allowed_keys: set, window: int = 60, asof_date: str = "") -> dict:
    if primary_key not in daily_data:
        return {}
    base_ret = _date_normalized_returns(daily_data[primary_key], asof_date=asof_date).iloc[-window:]
    corrs = {}
    details = {}
    for k, d in daily_data.items():
        if k == primary_key or k not in allowed_keys:
            continue
        sub_ret = _date_normalized_returns(d, asof_date=asof_date)
        aligned = pd.concat([base_ret.rename("base"), sub_ret.rename("sub")], axis=1, join="inner").dropna()
        if len(aligned) >= 20:
            same_day = float(aligned["base"].corr(aligned["sub"]))
            # Lag-1 correlation: prior macro day (t-1) vs primary index return today (t)
            lag1_aligned = pd.concat([base_ret.rename("base"), sub_ret.shift(1).rename("sub_lag1")], axis=1, join="inner").dropna()
            lag1_corr = float(lag1_aligned["base"].corr(lag1_aligned["sub_lag1"])) if len(lag1_aligned) >= 20 else float("nan")
            if not np.isnan(same_day):
                corrs[k] = round(same_day, 3)
                details[k] = {
                    "same_day_corr": round(same_day, 3),
                    "macro_lag1_corr": round(lag1_corr, 3) if not np.isnan(lag1_corr) else None,
                    "sample_days": int(len(aligned)),
                }
    sorted_corrs = dict(sorted(corrs.items(), key=lambda kv: abs(kv[1]), reverse=True))
    sorted_details = {k: details[k] for k in sorted_corrs}
    return {"same_day": sorted_corrs, "detailed": sorted_details}


def render_clawpilot_html_dashboard(summary: dict, idx_list: list, stk_list: list, clock_png_name: str, social_png_name: str, out_html: str, date_label: str):
    b = summary["breadth"]
    traps = summary["bull_traps_high_rsi_neg_cmf"]
    breakouts = summary["true_institutional_breakouts"]
    stealth = summary["stealth_accumulation_gems"]
    dist = summary["heavy_institutional_liquidation"]

    def rows_html(items):
        if not items:
            return "<tr><td colspan='5'>None flagged in current scan</td></tr>"
        out = []
        for x in items[:6]:
            nm = x["name"].replace("STK_", "")
            ret = x.get("ret_1m_pct") if x.get("ret_1m_pct") is not None else 0.0
            rsi = x.get("rsi14_d") if x.get("rsi14_d") is not None else 0.0
            cmf = x.get("cmf20") if x.get("cmf20") is not None else 0.0
            ud = x.get("up_down_vol_ratio_20d") if x.get("up_down_vol_ratio_20d") is not None else 1.0
            r_cls = "pos" if ret >= 0 else "neg"
            c_cls = "pos" if cmf >= 0 else "neg"
            out.append(f"<tr><td><strong>{nm}</strong></td><td class='{r_cls}'>{ret:+.2f}%</td><td>{rsi:.1f}</td><td class='{c_cls}'>{cmf:+.3f}</td><td>{ud:.2f}x</td></tr>")
        return "\n".join(out)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Market Quant & Microstructure Dashboard ({date_label})</title>
  <script>
    (() => {{
      const param = new URLSearchParams(window.location.search).get("clawpilotTheme");
      const theme =
        param || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      document.documentElement.setAttribute("data-theme", theme);
    }})();
  </script>
  <style>
    :root {{
      color-scheme: light;
      --cp-bg: #f7f4ef;
      --cp-bg-elevated: #fcfbf8;
      --cp-surface: #ffffff;
      --cp-surface-soft: #f5f5f5;
      --cp-border: #dedede;
      --cp-border-strong: #919191;
      --cp-text: #242424;
      --cp-text-muted: #5c5c5c;
      --cp-text-soft: #6f6f6f;
      --cp-accent: #b11f4b;
      --cp-accent-hover: #9a1a41;
      --cp-accent-soft: rgba(177, 31, 75, 0.08);
      --cp-accent-fg: #ffffff;
      --cp-success: #16a34a;
      --cp-danger: #dc2626;
      --cp-warning: #f59e0b;
      --cp-link: #0078d4;
      --cp-shadow: 0 18px 48px rgba(0, 0, 0, 0.12);
      --cp-overlay: rgba(255, 255, 255, 0.8);
      --cp-panel: rgba(255, 255, 255, 0.86);
      --cp-panel-strong: rgba(255, 255, 255, 0.96);
      --cp-sheen: rgba(255, 255, 255, 0.55);
      --cp-highlight: rgba(177, 31, 75, 0.12);
    }}
    html[data-theme="dark"] {{
      color-scheme: dark;
      --cp-bg: #3d3b3a;
      --cp-bg-elevated: #343231;
      --cp-surface: #292929;
      --cp-surface-soft: #2e2e2e;
      --cp-border: #474747;
      --cp-border-strong: #5f5f5f;
      --cp-text: #dedede;
      --cp-text-muted: #919191;
      --cp-text-soft: #b0b0b0;
      --cp-accent: #fd8ea1;
      --cp-accent-hover: #fb7b91;
      --cp-accent-soft: rgba(253, 142, 161, 0.14);
      --cp-accent-fg: #1a1a1a;
      --cp-success: #4ade80;
      --cp-danger: #f87171;
      --cp-warning: #fbbf24;
      --cp-link: #4da6ff;
      --cp-shadow: 0 18px 48px rgba(0, 0, 0, 0.32);
      --cp-overlay: rgba(41, 41, 41, 0.88);
      --cp-panel: rgba(41, 41, 41, 0.72);
      --cp-panel-strong: rgba(41, 41, 41, 0.96);
      --cp-sheen: rgba(255, 255, 255, 0.04);
      --cp-highlight: rgba(253, 142, 161, 0.12);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--cp-bg);
      color: var(--cp-text);
      font-family: "Segoe UI", Aptos, Calibri, -apple-system, BlinkMacSystemFont, sans-serif;
      padding: 24px;
      line-height: 1.5;
    }}
    .container {{ max-width: 1380px; margin: 0 auto; }}
    .header {{
      background: var(--cp-surface);
      border: 1px solid var(--cp-border);
      border-radius: 16px;
      padding: 20px 26px;
      margin-bottom: 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }}
    .badge {{
      display: inline-block;
      background: var(--cp-accent-soft);
      color: var(--cp-accent);
      font-family: Consolas, "Courier New", monospace;
      font-size: 12px;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 0.625rem;
      margin-bottom: 6px;
    }}
    .btn {{
      background: var(--cp-surface-soft);
      color: var(--cp-text);
      border: 1px solid var(--cp-border-strong);
      padding: 8px 14px;
      border-radius: 0.625rem;
      cursor: pointer;
      font-weight: 600;
      font-size: 13px;
    }}
    .kpi-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }}
    .kpi {{ background: var(--cp-surface); border: 1px solid var(--cp-border); border-radius: 16px; padding: 16px 20px; }}
    .kpi .lbl {{ font-size: 12px; color: var(--cp-text-muted); }}
    .kpi .val {{ font-size: 24px; font-weight: 700; font-family: Consolas, monospace; margin-top: 4px; color: var(--cp-accent); }}
    .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin-bottom: 24px; }}
    .card {{ background: var(--cp-surface); border: 1px solid var(--cp-border); border-radius: 16px; padding: 20px; }}
    .card h2 {{ font-size: 16px; margin-bottom: 10px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 7px 9px; text-align: left; border-bottom: 1px solid var(--cp-border); }}
    th {{ background: var(--cp-surface-soft); color: var(--cp-text-muted); }}
    .pos {{ color: var(--cp-success); font-weight: 700; font-family: Consolas, monospace; }}
    .neg {{ color: var(--cp-danger); font-weight: 700; font-family: Consolas, monospace; }}
    .img-card {{ background: var(--cp-surface); border: 1px solid var(--cp-border); border-radius: 16px; padding: 20px; margin-bottom: 20px; text-align: center; }}
    .img-card img {{ max-width: 100%; height: auto; border-radius: 10px; border: 1px solid var(--cp-border); margin-top: 10px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <span class="badge">MARKET-QUANT SKILL • MICROSTRUCTURE ENGINE</span>
        <h1>{summary['primary_index']} Institutional Quant & Microstructure Scan ({date_label})</h1>
      </div>
      <button class="btn" onclick="const h=document.documentElement; h.setAttribute('data-theme', h.getAttribute('data-theme')==='dark'?'light':'dark')">Toggle Light / Dark Theme</button>
    </div>

    <div class="kpi-row">
      <div class="kpi"><div class="lbl">% Above 20-DMA</div><div class="val">{b['pct_above_sma20']}%</div></div>
      <div class="kpi"><div class="lbl">% Above 50-DMA</div><div class="val">{b['pct_above_sma50']}%</div></div>
      <div class="kpi"><div class="lbl">% Above 200-DMA</div><div class="val">{b['pct_above_sma200']}%</div></div>
      <div class="kpi"><div class="lbl">% Positive 20D CMF (Order Flow)</div><div class="val">{b['pct_positive_cmf20']}%</div></div>
    </div>

    <div class="grid">
      <div class="card">
        <h2>Stealth Accumulation (Moderate/Low RSI + High Positive CMF)</h2>
        <table><thead><tr><th>Stock</th><th>1M Ret</th><th>RSI(14)</th><th>CMF(20)</th><th>Up/Dn Vol</th></tr></thead><tbody>{rows_html(stealth)}</tbody></table>
      </div>
      <div class="card">
        <h2>Bull Traps / Upper-Wick Dumps (High RSI + Negative CMF)</h2>
        <table><thead><tr><th>Stock</th><th>1M Ret</th><th>RSI(14)</th><th>CMF(20)</th><th>Up/Dn Vol</th></tr></thead><tbody>{rows_html(traps)}</tbody></table>
      </div>
      <div class="card">
        <h2>True Institutional Breakouts (High RSI + High Positive CMF)</h2>
        <table><thead><tr><th>Stock</th><th>1M Ret</th><th>RSI(14)</th><th>CMF(20)</th><th>Up/Dn Vol</th></tr></thead><tbody>{rows_html(breakouts)}</tbody></table>
      </div>
      <div class="card">
        <h2>Heavy Institutional Liquidation (Lowest 20D CMF)</h2>
        <table><thead><tr><th>Stock</th><th>1M Ret</th><th>RSI(14)</th><th>CMF(20)</th><th>Up/Dn Vol</th></tr></thead><tbody>{rows_html(dist)}</tbody></table>
      </div>
    </div>

    <div class="img-card">
      <h2>Social Media 4-Panel Quant Infographic</h2>
      <img src="{social_png_name}" alt="Social Media Quant Infographic" />
    </div>
    <div class="img-card">
      <h2>Intraday Smart-Money Clock & Volatility Crush</h2>
      <img src="{clock_png_name}" alt="Intraday Smart Money Clock" />
    </div>
  </div>
</body>
</html>"""
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)


def scaffold_multi_model_agent_briefs(workspace: str, summary: dict, market: str, idx_list: list = None):
    agents_dir = os.path.join(workspace, "agents")
    briefs_dir = os.path.join(agents_dir, "briefs")
    results_dir = os.path.join(agents_dir, "results")
    bb_dir = os.path.join(agents_dir, "blackboard")
    for d in [briefs_dir, results_dir, bb_dir]:
        os.makedirs(d, exist_ok=True)

    data_dir = os.path.join(workspace, "data")
    summary_path = os.path.join(data_dir, "anomaly_summary.json")
    dq_path = os.path.join(data_dir, "data_quality.json")
    idx_csv = os.path.join(data_dir, "indices_and_etfs_metrics.csv")
    stk_csv = os.path.join(data_dir, "constituents_quant_matrix.csv")
    events_path = os.path.join(bb_dir, "events.jsonl")

    # Seed blackboard events.jsonl
    init_event = {
        "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "phase": "phase_1_engine",
        "event": "blackboard_seeded",
        "market": market,
        "primary_index": summary.get("primary_index"),
        "summary_path": summary_path,
    }
    with open(events_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(init_event) + "\n")

    # Build compact desk-specific JSON slices so Wave 1 agents have immediate zero-latency context
    vp_slice = []
    for x in (idx_list or []):
        vp = x.get("volume_profile_120d") or {}
        if vp:
            vp_slice.append({
                "name": x["name"],
                "close": x["close"],
                "poc": vp.get("poc"),
                "val": vp.get("val"),
                "vah": vp.get("vah"),
                "lvn_air_pockets": vp.get("lvn_air_pockets", []),
            })

    orderflow_slice = json.dumps({
        "signal_spec": summary.get("signal_spec"),
        "breadth": summary.get("breadth"),
        "spot_vs_etf_divergences": summary.get("spot_vs_etf_divergences", []),
        "bull_traps_high_rsi_neg_cmf": summary.get("bull_traps_high_rsi_neg_cmf", [])[:6],
        "true_institutional_breakouts": summary.get("true_institutional_breakouts", [])[:6],
        "stealth_accumulation_gems": summary.get("stealth_accumulation_gems", [])[:6],
        "heavy_institutional_liquidation": summary.get("heavy_institutional_liquidation", [])[:6],
    }, indent=2)

    clock_slice = json.dumps({
        "intraday_cumulative_windows": summary.get("intraday_cumulative_windows", {}),
        "intraday_clock_summary": summary.get("intraday_clock_summary", {}),
        "volume_profile_120d": vp_slice[:8],
    }, indent=2)

    regime_slice = json.dumps({
        "signal_spec": summary.get("signal_spec"),
        "volatility_squeeze_coils": summary.get("volatility_squeeze_coils", []),
        "persistent_trend_assets": summary.get("persistent_trend_assets", []),
        "anti_persistent_chop_assets": summary.get("anti_persistent_chop_assets", [])[:8],
        "fft_harmonic_projection": summary.get("fft_harmonic_projection", {}),
    }, indent=2)

    macro_slice = json.dumps({
        "macro_correlations": summary.get("macro_correlations", {}),
        "spot_vs_etf_divergences": summary.get("spot_vs_etf_divergences", []),
    }, indent=2)

    wave1_ctx_template = (
        f"Shared context files: `{summary_path}`, `{dq_path}`, `{idx_csv}`, `{stk_csv}`. "
        f"IMPORTANT: As a Wave 1 specialist desk, run independently and do NOT read or wait for peer results in `{results_dir}`."
    )
    wave2_ctx_template = (
        f"Shared context files: `{summary_path}`, `{dq_path}`, `{idx_csv}`, `{stk_csv}`; "
        f"Wave 1 peer results to audit: `{results_dir}\\*.result.md`; "
        f"write output to `{results_dir}\\skeptical_risk_officer.result.md`."
    )

    briefs = {
        "microstructure_orderflow_desk": f"""# Role: Microstructure & Order-Flow Desk (`microstructure_orderflow_desk`)
- **Wave**: `Wave 1 (Parallel Specialist)`
- **Capability Band**: `strong` / `workhorse`
- **Market**: `{market}` (`{summary.get('primary_index')}`)
- **Shared Context**: {wave1_ctx_template}
- **Output Path**: `{os.path.join(results_dir, 'microstructure_orderflow_desk.result.md')}`

## Mission
Analyze institutional accumulation vs distribution beneath the surface price action using `SIGNAL_SPEC` thresholds:
1. **The "RSI Lie" Quadrant (`RSI-14` vs `Chaikin Money Flow CMF-20` & `20D Up/Down Volume Ratio`)**:
   - Inspect `bull_traps_high_rsi_neg_cmf` (`RSI >= 55, CMF <= -0.05`), `true_institutional_breakouts` (`RSI >= 55, CMF >= +0.10`), `stealth_accumulation_gems` (`RSI < 55, CMF >= +0.10, Up/Down Vol >= 1.25x`), and `heavy_institutional_liquidation` (`CMF <= -0.15`). Verify full constituent metrics in `{stk_csv}`.
   - Explain why high-RSI negative-CMF stocks experience upper-wick institutional selling into retail breakout buying, and why moderate-RSI high-CMF stocks represent institutional stealth accumulation.
2. **Spot Index Mirage vs Real-Money ETF Order Flow (`spot_vs_etf_divergences`)**:
   - Compare cash-verified ETF `etf_cmf20` (`BeES` / `SPDR`) against `spot_ret_1m_pct`, `constituent_equal_cmf20`, and `spot_cmf20`. Note `cmf_invalid_symbols` where index volume is non-cash.
   - Identify sectors where futures/index rallies diverge from ETF cash redemptions vs sectors with genuine cash-market institutional sponsorship.

## Pre-Sliced Desk Data
```json
{orderflow_slice}
```

## Required Output Format (no preamble)
### topic: orderflow.rsi_vs_cmf_anomalies
### topic: orderflow.spot_vs_etf_divergences
### topic: orderflow.high_conviction_setups
""",
        "intraday_volatility_clock_desk": f"""# Role: Intraday Execution & Volatility Clock Desk (`intraday_volatility_clock_desk`)
- **Wave**: `Wave 1 (Parallel Specialist)`
- **Capability Band**: `workhorse`
- **Market**: `{market}` (`{summary.get('primary_index')}`)
- **Shared Context**: {wave1_ctx_template}
- **Output Path**: `{os.path.join(results_dir, 'intraday_volatility_clock_desk.result.md')}`

## Mission
Analyze the intraday microstructure and volume-at-price geometry:
1. **60-Day Intraday Smart-Money Clock (`intraday_cumulative_windows` & `intraday_clock_summary`)**:
   - Contrast Overnight Gap (`cum_overnight_gap_pct`), Opening Hour (`cum_open_hr_pct`), Mid-Session drift (`cum_mid_session_pct`), and the Final-Hour institutional VWAP execution window (`cum_close_hr_pct` & `compounded_close_hr_pct`).
   - Quantify the return spread, win-rate asymmetry, and volatility range across hours.
2. **Afternoon VIX Crush & Systematic Short-Vol Supply**:
   - Analyze hourly volatility changes across the trading day and explain what systematic afternoon VIX compression reveals about dealer gamma and institutional hedging.
3. **120-Day Range-Distributed Volume Profile (`poc`, `val`, `vah`, `lvn_air_pockets`)**:
   - Map where spot indices trade relative to their 120-day Point of Control (`POC`), Value Area Low (`VAL`), Value Area High (`VAH`), and Low-Volume Node (`LVN`) air pockets.

## Pre-Sliced Desk Data
```json
{clock_slice}
```

## Required Output Format (no preamble)
### topic: microstructure.intraday_smart_money_clock
### topic: microstructure.afternoon_vix_crush
### topic: microstructure.volume_profile_air_pockets
""",
        "cycles_fractal_regime_desk": f"""# Role: Nonlinear Cycles & Fractal Regime Desk (`cycles_fractal_regime_desk`)
- **Wave**: `Wave 1 (Parallel Specialist)`
- **Capability Band**: `strong` / `workhorse`
- **Market**: `{market}` (`{summary.get('primary_index')}`)
- **Shared Context**: {wave1_ctx_template}
- **Output Path**: `{os.path.join(results_dir, 'cycles_fractal_regime_desk.result.md')}`

## Mission
Analyze fractal market memory, volatility compression coils, and spectral harmonic cycles:
1. **Fractal Hurst Exponent (`hurst_60d`, `hurst_60d_se`, `hurst_rs_60d`, `hurst_usable`) vs 1-Year Bollinger Bandwidth Percentile (`bb_width_1y_percentile`)**:
   - Identify indices/ETFs in anti-persistent mean-reverting chop (`H <= 0.45`), random walk (`0.45 < H < 0.55`), and persistent trend (`H >= 0.55`), checking `hurst_usable` (`|H - 0.50| / SE >= 1.5`) and classical R/S confirmation (`hurst_rs_60d`).
   - Flag assets in extreme volatility compression coils (`bb_width_1y_percentile <= 20%`) and determine whether order flow (`cmf20`) favors an upward or downward expansion.
2. **Fast Fourier Transform (`FFT`) Spectral Decomposition & 25-Day Forward Harmonic Wave (`fft_harmonic_projection`)**:
   - Evaluate the dominant `[25D–75D]` detrended harmonic cycles, `harmonic_variance_share_pct`, `vol_regime_ratio_20v60`, `fft_reliable` gating flag, and projected trading days to the next harmonic crest and trough.

## Pre-Sliced Desk Data
```json
{regime_slice}
```

## Required Output Format (no preamble)
### topic: regime.hurst_vs_bbw_coil_map
### topic: regime.fft_harmonic_projection
### topic: regime.nonlinear_timing_triggers
""",
        "macro_catalyst_correlator_desk": f"""# Role: Cross-Asset Macro & Catalyst Correlator Desk (`macro_catalyst_correlator_desk`)
- **Wave**: `Wave 1 (Parallel Specialist)`
- **Capability Band**: `workhorse`
- **Market**: `{market}` (`{summary.get('primary_index')}`)
- **Shared Context**: {wave1_ctx_template}
- **Output Path**: `{os.path.join(results_dir, 'macro_catalyst_correlator_desk.result.md')}`

## Mission
Connect statistical cross-asset correlations with fundamental/macro catalysts:
1. **60-Day Date-Normalized Cross-Asset Correlation Regime (`macro_correlations`)**:
   - Inspect both `same_day_corr` and `macro_lag1_corr` (prior-day US/global close vs today's local session) across Crude Oil, Currency (`USDINR`/`DXY`), `US10Y` Yields, Gold, VIX, and Global Indices.
   - Explain which macro factor acts as the primary tail-risk driver or tailwind for equities.
2. **Catalyst & Flow Corroboration (`web_search` if available)**:
   - Use `web_search` (when available) to corroborate top statistical anomalies (sector rotation, FII/DII institutional flows, central bank policy, commodity shocks, or earnings surprises) with recent verifiable headlines.

## Pre-Sliced Desk Data
```json
{macro_slice}
```

## Required Output Format (no preamble)
### topic: macro.cross_asset_correlations
### topic: macro.catalyst_corroboration
### topic: macro.tail_risk_matrix
""",
        "skeptical_risk_officer": f"""# Role: Skeptical Quant Risk Officer (`skeptical_risk_officer` — Wave 2 Adversarial Auditor)
- **Wave**: `Wave 2 (Adversarial Audit & Cross-Check)`
- **Capability Band**: `synthesis` / `strong` (MUST use a distinct model family from Wave 1 desks when available)
- **Market**: `{market}` (`{summary.get('primary_index')}`)
- **Shared Context**: {wave2_ctx_template}
- **Output Path**: `{os.path.join(results_dir, 'skeptical_risk_officer.result.md')}`

## Mission
Perform a ruthless adversarial audit of all Wave 1 specialist findings (`{results_dir}\\*.result.md`) against the raw CSV/JSON data (`{summary_path}`, `{dq_path}`, `{idx_csv}`, `{stk_csv}`):
1. **Exact Numerical Verification**:
   - Cross-check every cited ticker metric (`RSI-14`, `CMF-20`, `Up/Down Vol Ratio`, `Hurst-60D`, `Hurst SE`, `1Y BBW %ile`, `POC/VAL/VAH`, `FFT cycle days`) against `{idx_csv}` and `{stk_csv}`. Flag and correct any discrepancy.
2. **Statistical & Microstructure Caveats**:
   - Challenge bull/bear hypotheses: enforce `cmf_invalid_symbols` volume-quality gates, check `hurst_usable` standard-error bounds, check `fft_reliable` variance-share gates, and specify exact price invalidation levels.
3. **Calibrated Conviction Scoring**:
   - Rank the top 5 institutional insights by conviction (`[0.00–1.00]`) after accounting for cross-desk corroboration and risk caveats.

## Required Output Format (no preamble)
### topic: audit.verified_and_corrected_numbers
### topic: audit.statistical_caveats_and_invalidation_levels
### topic: audit.ranked_institutional_theses
""",
    }

    for role, content in briefs.items():
        with open(os.path.join(briefs_dir, f"{role}.md"), "w", encoding="utf-8") as f:
            f.write(content)

    # Emit machine-readable fleet_dispatch.json and quorum_grounding.json
    fleet_dispatch = {
        "market": market,
        "primary_index": summary.get("primary_index"),
        "workspace": workspace,
        "wave_1_parallel_desks": [
            {
                "role": r,
                "capability_band": "strong" if r in ("microstructure_orderflow_desk", "cycles_fractal_regime_desk") else "workhorse",
                "brief_path": os.path.join(briefs_dir, f"{r}.md"),
                "result_path": os.path.join(results_dir, f"{r}.result.md"),
            }
            for r in [
                "microstructure_orderflow_desk",
                "intraday_volatility_clock_desk",
                "cycles_fractal_regime_desk",
                "macro_catalyst_correlator_desk",
            ]
        ],
        "wave_2_adversarial_auditor": {
            "role": "skeptical_risk_officer",
            "capability_band": "synthesis",
            "must_differ_model_family_from_wave_1": True,
            "brief_path": os.path.join(briefs_dir, "skeptical_risk_officer.md"),
            "result_path": os.path.join(results_dir, "skeptical_risk_officer.result.md"),
        },
        "blackboard_events_jsonl": events_path,
    }
    with open(os.path.join(agents_dir, "fleet_dispatch.json"), "w", encoding="utf-8") as f:
        json.dump(fleet_dispatch, f, indent=2)

    quorum_grounding = {
        "topic": f"Which 5 institutional quantitative and microstructure anomalies in {market.upper()} ({summary.get('primary_index')}) have the highest risk-adjusted conviction?",
        "roles": [
            "microstructure_orderflow_desk",
            "intraday_volatility_clock_desk",
            "cycles_fractal_regime_desk",
            "macro_catalyst_correlator_desk",
            "skeptical_risk_officer",
        ],
        "verified_facts": {
            "signal_spec": summary.get("signal_spec"),
            "breadth": summary.get("breadth"),
            "intraday_cumulative_windows": summary.get("intraday_cumulative_windows"),
            "fft_harmonic_projection": summary.get("fft_harmonic_projection"),
            "cmf_invalid_symbols": summary.get("cmf_invalid_symbols"),
        },
    }
    with open(os.path.join(agents_dir, "quorum_grounding.json"), "w", encoding="utf-8") as f:
        json.dump(quorum_grounding, f, indent=2)

    return briefs_dir, results_dir, bb_dir


# ---------------------------------------------------------------------------
# MAIN CLI ENTRYPOINT
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Market Quant & Microstructure Engine")
    parser.add_argument("--market", choices=["india", "us"], default="india", help="Target market universe (default: india)")
    parser.add_argument("--tickers", type=str, default="", help="Optional comma-separated custom tickers to add/analyze")
    parser.add_argument("--workspace", type=str, default="", help="Target workspace folder (default: C:\\temp\\market-analysis\\dd-mm-yy)")
    parser.add_argument("--asof", type=str, default="", help="Optional historical cutoff date YYYY-MM-DD for reproducible backtests")
    parser.add_argument("--reuse-data", action="store_true", help="Reuse cached JSON OHLCV files in workspace/data if present")
    parser.add_argument("--skip-charts", action="store_true", help="Skip re-rendering PNG/HTML charts if only refreshing data & agent briefs")
    parser.add_argument("--emit-fleet-plan-only", action="store_true", help="Only emit data + agent briefs + fleet_dispatch.json without rendering charts")
    args = parser.parse_args()

    today_tag = dt.datetime.now().strftime("%d-%m-%y")
    workspace = args.workspace or os.path.join(r"C:\temp\market-analysis", today_tag)
    tag = os.path.basename(os.path.normpath(workspace))

    data_dir = os.path.join(workspace, "data")
    reports_dir = os.path.join(workspace, "reports")
    scripts_dir = os.path.join(workspace, "scripts")
    for d in [data_dir, reports_dir, scripts_dir]:
        os.makedirs(d, exist_ok=True)

    universe = json.loads(json.dumps(UNIVERSES[args.market]))
    if args.tickers:
        extra = [t.strip() for t in args.tickers.split(",") if t.strip()]
        universe["stocks"].extend([t for t in extra if t not in universe["stocks"]])

    daily_data, weekly_data, hourly_data, fetch_diag = fetch_or_load_data(universe, data_dir, reuse_data=args.reuse_data)

    idx_only_keys = set(universe["indices"].keys())
    idx_and_etf_keys = idx_only_keys | set(universe["etfs"].keys())
    idx_list = []
    stk_list = []
    for k, d_dict in daily_data.items():
        df_d = dict_to_df(d_dict, asof_date=args.asof)
        df_w = dict_to_df(weekly_data[k], asof_date=args.asof) if k in weekly_data else None
        res = analyze_single_asset(k, df_d, df_w, is_index=(k in idx_only_keys))
        if not res:
            continue
        if k.startswith("STK_") or k not in idx_and_etf_keys:
            stk_list.append(res)
        else:
            idx_list.append(res)

    # Save CSVs using union of all fieldnames across rows
    def save_csv(rows, path):
        if not rows:
            return
        flat = []
        all_fields = []
        seen_fields = set()
        for r in rows:
            item = {k: v for k, v in r.items() if not isinstance(v, (dict, list))}
            if r.get("volume_profile_120d"):
                item["vp_poc"] = r["volume_profile_120d"].get("poc")
                item["vp_val"] = r["volume_profile_120d"].get("val")
                item["vp_vah"] = r["volume_profile_120d"].get("vah")
            if r.get("fft_cycles"):
                item["fft_cycle_1_days"] = r["fft_cycles"][0]["period_days"]
                item["fft_cycle_1_var_pct"] = r["fft_cycles"][0].get("var_share_pct")
            for fk in item.keys():
                if fk not in seen_fields:
                    seen_fields.add(fk)
                    all_fields.append(fk)
            flat.append(item)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_fields)
            writer.writeheader()
            writer.writerows(flat)

    save_csv(idx_list, os.path.join(data_dir, "indices_and_etfs_metrics.csv"))
    save_csv(stk_list, os.path.join(data_dir, "constituents_quant_matrix.csv"))

    # Intraday clock & FFT projection
    p_key = universe["primary_index"]
    s_key = universe["secondary_index"]
    v_key = universe["vix_key"]
    open_slot = universe.get("open_slot", "09:15")
    close_slot = universe.get("close_slot", "15:15")
    clock_data = analyze_intraday_clock(hourly_data, p_key, s_key, v_key, open_slot=open_slot, close_slot=close_slot, asof_date=args.asof)
    fft_proj = compute_fft_projection(dict_to_df(daily_data[p_key], asof_date=args.asof)["Close"]) if p_key in daily_data else {}

    anomaly_summary = extract_anomaly_summary(idx_list, stk_list, clock_data, fft_proj, p_key)
    anomaly_summary["market"] = args.market
    anomaly_summary["date_tag"] = tag
    anomaly_summary["macro_correlations"] = compute_macro_correlations(daily_data, p_key, idx_and_etf_keys, asof_date=args.asof)
    anomaly_summary = _sanitize_json_value(anomaly_summary)
    summary_path = os.path.join(data_dir, "anomaly_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(anomaly_summary, f, indent=2, allow_nan=False)

    # Emit data_quality.json with SHA-256 dataset hash and diagnostics
    daily_hash = hashlib.sha256(json.dumps(daily_data, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    data_quality = {
        "market": args.market,
        "primary_index": p_key,
        "asof_filter": args.asof or "latest",
        "daily_data_sha256_16": daily_hash,
        "cache_reused": fetch_diag.get("cache_reused", False),
        "failed_daily_symbols": fetch_diag.get("failed_daily", []),
        "failed_hourly_symbols": fetch_diag.get("failed_hourly", []),
        "analyzed_indices_and_etfs_count": len(idx_list),
        "analyzed_constituents_count": len(stk_list),
        "cmf_invalid_symbols": anomaly_summary.get("cmf_invalid_symbols", []),
        "fft_reliable": fft_proj.get("fft_reliable"),
        "fft_harmonic_variance_share_pct": fft_proj.get("harmonic_variance_share_pct"),
    }
    dq_path = os.path.join(data_dir, "data_quality.json")
    with open(dq_path, "w", encoding="utf-8") as f:
        json.dump(data_quality, f, indent=2)

    briefs_dir, results_dir, bb_dir = scaffold_multi_model_agent_briefs(workspace, anomaly_summary, args.market, idx_list=idx_list)

    clock_png = os.path.join(reports_dir, f"intraday_smart_money_clock_{tag}.png")
    social_png = os.path.join(reports_dir, f"social_media_quant_infographic_{tag}.png")
    dash_html = os.path.join(reports_dir, f"market_quant_dashboard_{tag}.html")

    if not args.skip_charts and not args.emit_fleet_plan_only:
        render_intraday_clock_png(clock_data, p_key, s_key, v_key, clock_png, tag)
        render_social_infographic_png(idx_list, stk_list, fft_proj, p_key, social_png, tag)
        render_clawpilot_html_dashboard(anomaly_summary, idx_list, stk_list, os.path.basename(clock_png), os.path.basename(social_png), dash_html, tag)

    print(f"[market-quant] Completed successfully!")
    print(f"  - Anomaly Summary JSON : {summary_path}")
    print(f"  - Data Quality JSON    : {dq_path} (sha256={daily_hash})")
    print(f"  - Indices & ETFs CSV   : {os.path.join(data_dir, 'indices_and_etfs_metrics.csv')}")
    print(f"  - Constituents CSV     : {os.path.join(data_dir, 'constituents_quant_matrix.csv')}")
    print(f"  - Agent Briefs Dir     : {briefs_dir}")
    print(f"  - Fleet Dispatch JSON  : {os.path.join(workspace, 'agents', 'fleet_dispatch.json')}")
    print(f"  - Agent Results Dir    : {results_dir}")
    if not args.skip_charts and not args.emit_fleet_plan_only:
        print(f"  - Intraday Clock PNG   : {clock_png}")
        print(f"  - Social Quant PNG     : {social_png}")
        print(f"  - Interactive HTML     : {dash_html}")


if __name__ == "__main__":
    main()
