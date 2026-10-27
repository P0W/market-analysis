import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
    ANSI,
    badge,
    colorVal,
    renderBar,
    renderProgressBar,
    formatQuantHud,
    formatFleetProgress,
} from "./plugin/com.github.copilot/extensions/market-quant/ansi-hud.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));

describe("market-quant ANSI HUD & Telemetry", () => {
    it("renders positive and negative colorVal with ANSI codes", () => {
        const pos = colorVal(1.234, 2, "%");
        const neg = colorVal(-2.5, 2, "%");
        assert.ok(pos.includes("+1.23%"));
        assert.ok(neg.includes("-2.50%"));
        assert.ok(pos.includes(ANSI.green));
        assert.ok(neg.includes(ANSI.red));
    });

    it("renders institutional order-flow bar and fleet progress bar", () => {
        const bar = renderBar(-0.25, 0.45, 10);
        assert.ok(bar.includes("▓"));
        const prog = renderProgressBar(3, 5, 10);
        assert.ok(prog.includes("3/5"));
    });

    it("renders complete formatQuantHud scorecard from anomaly_summary schema", () => {
        const mockSummary = {
            market: "india",
            date_tag: "22-10-26",
            primary_index: "Nifty50",
            primary_index_snapshot: {
                close: 22687.65,
                ret_1w_pct: -0.15,
                ret_1m_pct: -2.82,
                rsi14_d: 44.14,
                bb_width_1y_percentile: 63.5,
                hurst_60d: 0.26,
                hurst_rs_60d: 0.544,
                volume_profile_120d: {
                    poc: 24071.65,
                    val: 23369.0,
                    vah: 24450.0,
                    va_coverage_pct: 70.1,
                    lvn_air_pockets: [23810.5],
                },
            },
            breadth: {
                pct_above_sma50: 26.3,
                pct_above_sma200: 21.1,
                constituent_equal_cmf20: -0.026,
            },
            fft_harmonic_projection: {
                selected_periods_days: [42.0, 25.2],
                harmonic_variance_share_pct: 6.4,
                fft_reliable: false,
            },
            spot_vs_etf_divergences: [
                {
                    spot: "Nifty50",
                    etf: "NiftyBees",
                    spot_cmf20: 0.086,
                    etf_cmf20: -0.167,
                    spread_etf_minus_spot: -0.253,
                    flow_regime: "real_money_etf_distribution",
                },
            ],
            intraday_cumulative_windows: {
                Nifty50: {
                    close_window_start_slot: "14:15",
                    cum_open_hr_pct: -4.11,
                    cum_mid_session_pct: -4.92,
                    cum_close_hr_pct: 6.21,
                },
            },
            intraday_clock_summary: {
                Nifty50: [
                    { slot: "09:15", win_rate_pct: 36.8 },
                    { slot: "15:15", win_rate_pct: 63.2 },
                ],
                IndiaVIX: [
                    { slot: "09:15", cum_ret_60d_pct: 25.0, win_rate_pct: 52.6 },
                    { slot: "14:15", cum_ret_60d_pct: -39.4, win_rate_pct: 22.8 },
                ],
            },
            bull_traps_high_rsi_neg_cmf: [{ name: "STK_WIPRO", rsi14_d: 73.66, cmf20: -0.198 }],
            stealth_accumulation_gems: [{ name: "STK_NTPC", rsi14_d: 53.55, cmf20: 0.253 }],
            true_institutional_breakouts: [{ name: "STK_DRREDDY", rsi14_d: 58.45, cmf20: 0.27 }],
        };
        const hud = formatQuantHud(mockSummary, { daily_data_sha256_16: "090093c336e64222" });
        assert.ok(hud.includes("MARKET-QUANT HUD"));
        assert.ok(hud.includes("22687.65"));
        assert.ok(hud.includes("NiftyBees"));
        assert.ok(hud.includes("WIPRO"));
        assert.ok(hud.includes("NTPC"));
        assert.ok(hud.includes("DRREDDY"));
    });

    it("renders multi-agent fleet progress bar accurately", () => {
        const state = new Map([
            ["desk1", "done"],
            ["desk2", "running"],
            ["desk3", "pending"],
        ]);
        const line = formatFleetProgress(state);
        assert.ok(line.includes("1/5"));
        assert.ok(line.includes("✔ D1:Micro"));
        assert.ok(line.includes("⟳ D2:Vol/FFT"));
    });

    it("keeps SKILL.md frontmatter description within Copilot CLI 1024-char limit", () => {
        const skillPath = join(__dirname, "plugin", "skills", "market-quant", "SKILL.md");
        const raw = readFileSync(skillPath, "utf8");
        const match = raw.match(/^---\r?\n([\s\S]*?)\r?\n---/);
        assert.ok(match, "SKILL.md must have YAML frontmatter");
        const descLine = match[1]
            .split(/\r?\n/)
            .find((l) => l.startsWith("description:"));
        assert.ok(descLine, "SKILL.md frontmatter must include description");
        const desc = descLine.replace(/^description:\s*/, "").trim();
        assert.ok(
            desc.length > 0 && desc.length <= 1024,
            `SKILL.md description length (${desc.length}) must be <= 1024 chars for Copilot CLI slash command registration`,
        );
    });

    it("maintains a single canonical market_quant_engine.py under plugin/skills/market-quant", () => {
        const canonicalEngine = join(__dirname, "plugin", "skills", "market-quant", "market_quant_engine.py");
        const duplicateExtensionCopy = join(
            __dirname,
            "plugin",
            "com.github.copilot",
            "extensions",
            "market-quant",
            "market_quant_engine.py",
        );
        assert.ok(existsSync(canonicalEngine), "Canonical market_quant_engine.py must exist under plugin/skills/market-quant");
        assert.ok(!existsSync(duplicateExtensionCopy), "Duplicate market_quant_engine.py should not exist in extension directory");
    });
});
