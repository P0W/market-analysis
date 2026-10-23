// ANSI Terminal HUD & Progress Telemetry for the market-quant Copilot CLI Extension

const ESC = "\x1b[";
export const ANSI = {
    reset: `${ESC}0m`,
    bold: `${ESC}1m`,
    dim: `${ESC}2m`,
    italic: `${ESC}3m`,
    cyan: `${ESC}38;5;45m`,
    teal: `${ESC}38;5;43m`,
    green: `${ESC}38;5;41m`,
    red: `${ESC}38;5;196m`,
    amber: `${ESC}38;5;214m`,
    purple: `${ESC}38;5;141m`,
    blue: `${ESC}38;5;75m`,
    gray: `${ESC}38;5;245m`,
    white: `${ESC}38;5;255m`,
    bgDark: `${ESC}48;5;235m`,
    bgBadgeCyan: `${ESC}48;5;24m${ESC}38;5;255m${ESC}1m`,
    bgBadgeGreen: `${ESC}48;5;22m${ESC}38;5;255m${ESC}1m`,
    bgBadgeRed: `${ESC}48;5;52m${ESC}38;5;255m${ESC}1m`,
    bgBadgeAmber: `${ESC}48;5;94m${ESC}38;5;255m${ESC}1m`,
    bgBadgePurple: `${ESC}48;5;54m${ESC}38;5;255m${ESC}1m`,
};

export function badge(label, style = ANSI.bgBadgeCyan) {
    return `${style} ${label} ${ANSI.reset}`;
}

export function colorVal(val, digits = 2, suffix = "", invert = false) {
    if (val === null || val === undefined || Number.isNaN(Number(val))) {
        return `${ANSI.gray}N/A${ANSI.reset}`;
    }
    const num = Number(val);
    const sign = num > 0 ? "+" : "";
    const isGood = invert ? num < 0 : num > 0;
    const isBad = invert ? num > 0 : num < 0;
    const col = isGood ? ANSI.green : isBad ? ANSI.red : ANSI.amber;
    return `${col}${ANSI.bold}${sign}${num.toFixed(digits)}${suffix}${ANSI.reset}`;
}

export function renderBar(value, maxAbs = 0.45, width = 12) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return `${ANSI.gray}${"·".repeat(width)}${ANSI.reset}`;
    }
    const num = Number(value);
    const ratio = Math.min(1, Math.abs(num) / maxAbs);
    const filled = Math.max(1, Math.round(ratio * width));
    const empty = Math.max(0, width - filled);
    const col = num >= 0 ? ANSI.green : ANSI.red;
    const char = num >= 0 ? "█" : "▓";
    return `${col}${char.repeat(filled)}${ANSI.gray}${"░".repeat(empty)}${ANSI.reset}`;
}

export function renderProgressBar(completed, total, width = 16) {
    const safeTotal = Math.max(1, total);
    const ratio = Math.min(1, Math.max(0, completed / safeTotal));
    const filled = Math.round(ratio * width);
    const empty = Math.max(0, width - filled);
    const col = completed >= safeTotal ? ANSI.green : ANSI.cyan;
    return `${col}${"█".repeat(filled)}${ANSI.gray}${"░".repeat(empty)}${ANSI.reset} ${ANSI.bold}${completed}/${safeTotal}${ANSI.reset}`;
}

/**
 * Formats a compact, colorful ANSI terminal scorecard from anomaly_summary.json and data_quality.json.
 */
export function formatQuantHud(summary, quality = null) {
    if (!summary || typeof summary !== "object") {
        return `${badge("MARKET-QUANT", ANSI.bgBadgeRed)} No anomaly_summary.json data provided.`;
    }

    const market = String(summary.market_label || summary.market || quality?.market || "INDIA").toUpperCase();
    const dateTag = summary.date_tag || summary.primary_index_snapshot?.last_date || "latest";
    const sha = quality?.daily_data_sha256_16 || summary.data_quality?.daily_data_sha256_16 || "verified";
    const pKey = summary.primary_index || "PrimaryIndex";
    const pSnap =
        summary.primary_index_snapshot ||
        (Array.isArray(summary.anti_persistent_chop_assets)
            ? summary.anti_persistent_chop_assets.find((x) => x.name === pKey)
            : null) ||
        (Array.isArray(summary.persistent_trend_assets)
            ? summary.persistent_trend_assets.find((x) => x.name === pKey)
            : null) ||
        {};
    const vprof = pSnap.volume_profile_120d || summary.primary_volume_profile || {};
    const fft = summary.fft_harmonic_projection || {};
    const breadth = summary.breadth || {};
    const clock = summary.intraday_cumulative_windows?.[pKey] || summary.intraday_session_clock?.[pKey] || {};
    const pSlots = Array.isArray(summary.intraday_clock_summary?.[pKey]) ? summary.intraday_clock_summary[pKey] : [];
    const vixSlots = Array.isArray(summary.intraday_clock_summary?.IndiaVIX)
        ? summary.intraday_clock_summary.IndiaVIX
        : Array.isArray(summary.intraday_clock_summary?.VIX)
          ? summary.intraday_clock_summary.VIX
          : [];

    const lines = [];
    const border = `${ANSI.cyan}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${ANSI.reset}`;
    lines.push(border);
    lines.push(
        `${badge("⚡ MARKET-QUANT HUD", ANSI.bgBadgeCyan)} ${ANSI.bold}${ANSI.white}${market}${ANSI.reset} ` +
        `${ANSI.gray}│${ANSI.reset} Date: ${ANSI.amber}${dateTag}${ANSI.reset} ` +
        `${ANSI.gray}│${ANSI.reset} SHA256: ${ANSI.teal}${sha}${ANSI.reset}`
    );
    lines.push(border);

    // 1. Primary Index Regime & Microstructure Snapshot
    const hurst = pSnap.hurst_60d;
    const hurstRegime =
        hurst !== null && hurst !== undefined
            ? hurst <= 0.45
                ? `${ANSI.red}Mean-Reverting (${hurst.toFixed(3)})${ANSI.reset}`
                : hurst >= 0.55
                  ? `${ANSI.green}Trending (${hurst.toFixed(3)})${ANSI.reset}`
                  : `${ANSI.amber}Random Walk (${hurst.toFixed(3)})${ANSI.reset}`
            : `${ANSI.gray}Gated${ANSI.reset}`;

    const fftReliable = fft.fft_reliable ?? pSnap.fft_reliable;
    const fftPeriod = fft.selected_periods_days?.[0] ?? pSnap.fft_cycles?.[0]?.period_days ?? "?";
    const fftVar = fft.harmonic_variance_share_pct ?? pSnap.fft_cycles?.[0]?.power_share_pct ?? "?";
    const fftBadge = fftReliable
        ? `${ANSI.green}Reliable (${fftPeriod}d, ${fftVar}% var)${ANSI.reset}`
        : `${ANSI.amber}Suppressed (${fftPeriod}d, ${fftVar}% var — Non-Stationary)${ANSI.reset}`;

    lines.push(
        `${ANSI.bold}${ANSI.cyan}▸ PRIMARY INDEX (${pKey})${ANSI.reset} ` +
        `Close: ${ANSI.bold}${ANSI.white}${pSnap.close ?? "N/A"}${ANSI.reset} ` +
        `(${colorVal(pSnap.ret_1w_pct ?? pSnap.ret_5d_pct, 2, "% 1W")} / ${colorVal(pSnap.ret_1m_pct ?? pSnap.ret_20d_pct, 2, "% 1M")}) ` +
        `│ RSI(14): ${ANSI.bold}${pSnap.rsi14_d ?? "N/A"}${ANSI.reset} ` +
        `│ BBW Pctl: ${ANSI.bold}${pSnap.bb_width_1y_percentile ?? "N/A"}%${ANSI.reset}`
    );
    lines.push(
        `  ${ANSI.gray}├─${ANSI.reset} Fractal Hurst(60D): ${hurstRegime} [R/S=${pSnap.hurst_rs_60d ?? "N/A"}] ` +
        `│ FFT Cycle: ${fftBadge}`
    );
    if (vprof.poc || vprof.poc_price) {
        const poc = vprof.poc ?? vprof.poc_price;
        const val = vprof.val ?? vprof.val_70;
        const vah = vprof.vah ?? vprof.vah_70;
        const airCount = Array.isArray(vprof.lvn_air_pockets) ? vprof.lvn_air_pockets.length : 0;
        lines.push(
            `  ${ANSI.gray}└─${ANSI.reset} 70% Volume Value Area: VAL ${ANSI.amber}${val}${ANSI.reset} ◄── ` +
            `POC ${ANSI.bold}${ANSI.white}${poc}${ANSI.reset} ──► VAH ${ANSI.amber}${vah}${ANSI.reset} ` +
            `(${vprof.va_coverage_pct ?? 70}% cov, ${airCount} LVN Air Pockets)`
        );
    }

    // 2. Spot Index vs Cash-Verified ETF Flow Divergences
    const flowPairs = Array.isArray(summary.spot_vs_etf_divergences)
        ? summary.spot_vs_etf_divergences
        : Array.isArray(summary.spot_vs_etf_flow_divergence)
          ? summary.spot_vs_etf_flow_divergence
          : [];
    if (flowPairs.length > 0) {
        const constCmf = breadth.constituent_equal_cmf20 ?? summary.constituent_equal_weight_cash_cmf20;
        lines.push("");
        lines.push(
            `${ANSI.bold}${ANSI.purple}▸ SPOT INDEX (SYNTHETIC VOL) vs CASH-VERIFIED ETF FLOW (20D CMF)${ANSI.reset} ` +
            `(Constituent Equal-Wt CMF: ${colorVal(constCmf, 3)})`
        );
        for (const pair of flowPairs) {
            const spotName = String(pair.spot || pair.spot_index || "");
            const etfName = String(pair.etf || pair.cash_etf || "");
            const etfCmf = pair.etf_cmf20 ?? pair.etf_cash_cmf20;
            const regimeBadge =
                pair.flow_regime === "real_money_etf_distribution" || pair.flow_regime === "spot_rally_vs_etf_distribution_divergence"
                    ? `${ANSI.red}⚠ ETF DISTRIBUTION${ANSI.reset}`
                    : pair.flow_regime === "real_money_etf_accumulation"
                      ? `${ANSI.green}★ ETF ACCUMULATION${ANSI.reset}`
                      : `${ANSI.gray}● ALIGNED${ANSI.reset}`;
            lines.push(
                `  ${ANSI.gray}•${ANSI.reset} ${ANSI.bold}${spotName.padEnd(11)}${ANSI.reset} ` +
                `Spot: ${colorVal(pair.spot_cmf20, 3)} vs ${ANSI.bold}${etfName.padEnd(10)}${ANSI.reset} ` +
                `Cash: ${colorVal(etfCmf, 3)} ${renderBar(etfCmf, 0.45, 10)} ` +
                `│ Spread: ${colorVal(pair.spread_etf_minus_spot, 3)} ${regimeBadge}`
            );
        }
    }

    // 3. Intraday Smart-Money Session Clock
    const openCum = clock.cum_open_hr_pct ?? clock.opening_hour_cum_pct;
    const midCum = clock.cum_mid_session_pct ?? clock.mid_session_cum_pct;
    const closeCum = clock.cum_close_hr_pct ?? clock.closing_hour_cum_pct;
    if (openCum !== undefined) {
        const openSlotObj = pSlots[0];
        const closeSlotObj = pSlots[pSlots.length - 1];
        lines.push("");
        lines.push(`${ANSI.bold}${ANSI.amber}▸ 60-DAY INTRADAY SMART-MONEY CLOCK (${pKey})${ANSI.reset}`);
        lines.push(
            `  ${ANSI.gray}├─${ANSI.reset} Opening Hour (${openSlotObj?.slot || "09:15"}): ${colorVal(openCum, 2, "%")} ` +
            `(Win: ${openSlotObj?.win_rate_pct ?? clock.opening_hour_win_rate_pct ?? "?"}%) ` +
            `│ Mid-Session Drift: ${colorVal(midCum, 2, "%")} ` +
            `│ Closing Window (≥${clock.close_window_start_slot || "14:15"}): ${colorVal(closeCum, 2, "%")} ` +
            `(Win: ${closeSlotObj?.win_rate_pct ?? clock.closing_hour_win_rate_pct ?? "?"}%)`
        );
        if (vixSlots.length > 0) {
            const openVix = vixSlots[0];
            const pmVix = vixSlots.find((b) => b.slot === "14:15") || vixSlots[vixSlots.length - 1];
            lines.push(
                `  ${ANSI.gray}└─${ANSI.reset} Volatility Clock: Morning Spike (${openVix.slot}) ` +
                `${colorVal(openVix.cum_ret_60d_pct, 1, "%", true)} (${openVix.win_rate_pct}%↑) ` +
                `vs Afternoon VIX Crush (${pmVix.slot}) ${colorVal(pmVix.cum_ret_60d_pct, 1, "%", true)} (${pmVix.win_rate_pct}%↑)`
            );
        }
    }

    // 4. Constituent Divergences (Bull-Trap vs Stealth Accumulation)
    const traps = Array.isArray(summary.bull_traps_high_rsi_neg_cmf)
        ? summary.bull_traps_high_rsi_neg_cmf
        : Array.isArray(summary.bull_trap_divergences)
          ? summary.bull_trap_divergences
          : [];
    const accum = Array.isArray(summary.stealth_accumulation_gems)
        ? summary.stealth_accumulation_gems
        : Array.isArray(summary.stealth_accumulations)
          ? summary.stealth_accumulations
          : [];
    const trueLdr = Array.isArray(summary.true_institutional_breakouts)
        ? summary.true_institutional_breakouts
        : Array.isArray(summary.true_institutional_leaders)
          ? summary.true_institutional_leaders
          : [];
    lines.push("");
    lines.push(
        `${ANSI.bold}${ANSI.teal}▸ CONSTITUENT ORDER-FLOW DIVERGENCES (CLV × VOLUME vs RSI)${ANSI.reset} ` +
        `[Breadth >SMA50: ${breadth.pct_above_sma50 ?? "?"}% │ >SMA200: ${breadth.pct_above_sma200 ?? "?"}%]`
    );
    if (traps.length > 0) {
        const tStr = traps
            .slice(0, 4)
            .map((r) => `${ANSI.bold}${String(r.name).replace(/^STK_/, "")}${ANSI.reset}(RSI:${r.rsi14_d}, CMF:${colorVal(r.cmf20, 2)})`)
            .join(", ");
        lines.push(`  ${ANSI.gray}├─${ANSI.reset} ${ANSI.red}Bull-Trap Distribution:${ANSI.reset} ${tStr}`);
    }
    if (accum.length > 0) {
        const aStr = accum
            .slice(0, 4)
            .map((r) => `${ANSI.bold}${String(r.name).replace(/^STK_/, "")}${ANSI.reset}(RSI:${r.rsi14_d}, CMF:${colorVal(r.cmf20, 2)})`)
            .join(", ");
        lines.push(`  ${ANSI.gray}├─${ANSI.reset} ${ANSI.green}Stealth Accumulation  :${ANSI.reset} ${aStr}`);
    }
    if (trueLdr.length > 0) {
        const lStr = trueLdr
            .slice(0, 4)
            .map((r) => `${ANSI.bold}${String(r.name).replace(/^STK_/, "")}${ANSI.reset}(RSI:${r.rsi14_d}, CMF:${colorVal(r.cmf20, 2)})`)
            .join(", ");
        lines.push(`  ${ANSI.gray}└─${ANSI.reset} ${ANSI.cyan}Institutional Leaders :${ANSI.reset} ${lStr}`);
    }

    lines.push(border);
    return lines.join("\n");
}

/**
 * Formats a live ANSI progress line for multi-agent fleet execution.
 */
export function formatFleetProgress(fleetState) {
    const desks = [
        { id: "desk1", short: "D1:Micro" },
        { id: "desk2", short: "D2:Vol/FFT" },
        { id: "desk3", short: "D3:Macro" },
        { id: "desk4", short: "D4:RedTeam" },
        { id: "desk5", short: "D5:PM" },
    ];
    let doneCount = 0;
    const pills = desks.map((d) => {
        const st = fleetState.get(d.id) || "pending";
        if (st === "done") {
            doneCount += 1;
            return `${ANSI.green}✔ ${d.short}${ANSI.reset}`;
        }
        if (st === "running") {
            return `${ANSI.amber}⟳ ${d.short}${ANSI.reset}`;
        }
        return `${ANSI.gray}○ ${d.short}${ANSI.reset}`;
    });
    const bar = renderProgressBar(doneCount, desks.length, 10);
    return `${badge("FLEET", ANSI.bgBadgePurple)} ${bar} │ ${pills.join("  ")}`;
}
