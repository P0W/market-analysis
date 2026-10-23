// Extension: market-quant
// Institutional Market Quantitative & Microstructure Multi-Model Research Extension

import { spawn, exec } from "node:child_process";
import { existsSync, readFileSync, appendFileSync, mkdirSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { performance } from "node:perf_hooks";
import { defineWorkflow, joinSession } from "@github/copilot-sdk/extension";
import { ANSI, badge, formatQuantHud, formatFleetProgress, renderProgressBar } from "./ansi-hud.mjs";

const extensionDir = dirname(fileURLToPath(import.meta.url));
let activeWorkspace = null;
const fleetState = new Map();
const deskStartTimes = new Map();

function defaultDateTag() {
    const now = new Date();
    const dd = String(now.getDate()).padStart(2, "0");
    const mm = String(now.getMonth() + 1).padStart(2, "0");
    const yy = String(now.getFullYear()).slice(-2);
    return `${dd}-${mm}-${yy}`;
}

function defaultWorkspacePath() {
    const tag = defaultDateTag();
    return process.platform === "win32"
        ? `C:\\temp\\market-analysis\\${tag}`
        : `/tmp/market-analysis/${tag}`;
}

function resolveEngineScript() {
    const candidates = [
        join(extensionDir, "market_quant_engine.py"),
        join(extensionDir, "..", "..", "..", "skills", "market-quant", "market_quant_engine.py"),
        join(extensionDir, "..", "..", "skills", "market-quant", "market_quant_engine.py"),
        join(homedir(), ".copilot", "skills", "market-quant", "market_quant_engine.py"),
    ];
    for (const candidate of candidates) {
        if (existsSync(candidate)) {
            return candidate;
        }
    }
    throw new Error(
        `market_quant_engine.py not found. Checked: ${candidates.join(", ")}`
    );
}

function safeReadJson(filePath) {
    try {
        if (!existsSync(filePath)) return null;
        const raw = readFileSync(filePath, "utf8").replace(
            /:\s*(NaN|-?Infinity)\b/g,
            ": null"
        );
        return JSON.parse(raw);
    } catch {
        return null;
    }
}

function appendBlackboardEvent(workspace, eventObj) {
    if (!workspace) return;
    try {
        const bbDir = join(workspace, "agents", "blackboard");
        mkdirSync(bbDir, { recursive: true });
        const eventsFile = join(bbDir, "events.jsonl");
        appendFileSync(
            eventsFile,
            JSON.stringify({ timestamp: new Date().toISOString(), ...eventObj }) + "\n",
            "utf8"
        );
    } catch {
        // Non-fatal telemetry write
    }
}

function matchDeskKey(agentName = "", agentDesc = "") {
    const combined = `${agentName} ${agentDesc}`.toLowerCase();
    if (combined.includes("desk1") || combined.includes("desk 1") || combined.includes("microstructure")) return "desk1";
    if (combined.includes("desk2") || combined.includes("desk 2") || combined.includes("volatility") || combined.includes("fourier")) return "desk2";
    if (combined.includes("desk3") || combined.includes("desk 3") || combined.includes("macro") || combined.includes("intraday")) return "desk3";
    if (combined.includes("desk4") || combined.includes("desk 4") || combined.includes("contrarian") || combined.includes("red-team") || combined.includes("skeptic")) return "desk4";
    if (combined.includes("desk5") || combined.includes("desk 5") || combined.includes("pm") || combined.includes("synthesis")) return "desk5";
    return null;
}

function runPythonEngine(argsList, onStatusLine) {
    return new Promise((resolvePromise, rejectPromise) => {
        const scriptPath = resolveEngineScript();
        const pyCmd = process.platform === "win32" ? "python" : "python3";
        const child = spawn(pyCmd, [scriptPath, ...argsList], {
            windowsHide: true,
            stdio: ["ignore", "pipe", "pipe"],
        });

        let stdout = "";
        let stderr = "";

        child.stdout.on("data", (chunk) => {
            const text = chunk.toString("utf8");
            stdout += text;
            for (const line of text.split(/\r?\n/)) {
                const trimmed = line.trim();
                if (trimmed.startsWith("[market-quant]") && onStatusLine) {
                    onStatusLine(trimmed);
                }
            }
        });

        child.stderr.on("data", (chunk) => {
            stderr += chunk.toString("utf8");
        });

        child.on("error", (err) => rejectPromise(err));
        child.on("close", (code) => {
            if (code === 0) {
                resolvePromise({ stdout, stderr });
            } else {
                rejectPromise(
                    new Error(`market_quant_engine.py exited with code ${code}: ${stderr || stdout}`)
                );
            }
        });
    });
}

let sessionRef = null;

async function logTimeline(message, options = {}) {
    if (!sessionRef) return;
    try {
        await sessionRef.log(message, options);
    } catch {
        // Ignore transient log errors
    }
}

// Dynamic Workflow: 5-Desk Multi-Model Institutional Market Quant Pipeline
const marketQuantFleetWorkflow = defineWorkflow({
    meta: {
        name: "market-quant-fleet",
        description:
            "Runs the 4-phase Multi-Model Institutional Market Quant workflow: " +
            "(1) Python Quant Engine & Grounding, (2) Wave 1 Parallel Desks 1-3 across diverse models, " +
            "(3) Wave 2 Adversarial Red-Team Desk 4, and (4) Wave 3 Chief Quant PM Synthesis Desk 5.",
        phases: [
            { title: "Phase 1: Quant Engine & Grounding", detail: "Compute anomaly_summary.json, data_quality.json, and 300-DPI charts" },
            { title: "Phase 2: Wave 1 Specialist Desks", detail: "Parallel execution of Desk 1 (Microstructure), Desk 2 (Vol/FFT), Desk 3 (Macro/Clock)" },
            { title: "Phase 3: Wave 2 Adversarial Red-Team", detail: "Desk 4 Contrarian audit of Wave 1 claims against ground truth" },
            { title: "Phase 4: Wave 3 Chief PM Synthesis", detail: "Desk 5 executive report synthesis and deterministic verification" },
        ],
        argsSchema: {
            type: "object",
            properties: {
                market: { type: "string", enum: ["india", "us", "crypto", "global"] },
                workspace: { type: "string" },
                asof: { type: "string" },
                reuse_data: { type: "boolean" },
            },
        },
    },
    run: async (ctx) => {
        const market = String(ctx.args?.market || "india").toLowerCase();
        const workspace = resolve(String(ctx.args?.workspace || defaultWorkspacePath()));
        const asof = ctx.args?.asof ? String(ctx.args.asof) : null;
        const reuseData = ctx.args?.reuse_data !== false;
        activeWorkspace = workspace;

        // Phase 1: Run Python Quant Engine
        ctx.phase("Phase 1: Quant Engine & Grounding");
        ctx.log(`Running market_quant_engine.py for market=${market} in ${workspace}`);
        await logTimeline(
            `${badge("WORKFLOW", ANSI.bgBadgeCyan)} ${ANSI.bold}Phase 1/4:${ANSI.reset} Running Quantitative Engine (${market.toUpperCase()}) → ${ANSI.teal}${workspace}${ANSI.reset}`,
            { ephemeral: true }
        );

        const engineStep = await ctx.step("quant-engine-v1", async () => {
            const cliArgs = ["--market", market, "--workspace", workspace];
            if (reuseData) cliArgs.push("--reuse-data");
            if (asof) cliArgs.push("--asof", asof);
            await runPythonEngine(cliArgs, (line) => ctx.log(line));
            const summary = safeReadJson(join(workspace, "data", "anomaly_summary.json"));
            const quality = safeReadJson(join(workspace, "data", "data_quality.json"));
            return {
                workspace,
                market,
                date_tag: summary?.date_tag || null,
                sha256: quality?.daily_data_sha256_16 || null,
                primary_index: summary?.primary_index || null,
            };
        });

        const summary = safeReadJson(join(workspace, "data", "anomaly_summary.json"));
        const quality = safeReadJson(join(workspace, "data", "data_quality.json"));
        const grounding = safeReadJson(join(workspace, "agents", "quorum_grounding.json"));
        if (summary) {
            await logTimeline(formatQuantHud(summary, quality));
        }

        // Phase 2: Wave 1 Parallel Desks (1, 2, 3)
        ctx.phase("Phase 2: Wave 1 Specialist Desks");
        const wave1Desks = [
            {
                id: "desk1",
                file: "microstructure_orderflow_desk.md",
                outFile: "microstructure_orderflow_desk.result.md",
                title: "Desk 1: Microstructure & Order Flow",
            },
            {
                id: "desk2",
                file: "cycles_fractal_regime_desk.md",
                outFile: "cycles_fractal_regime_desk.result.md",
                title: "Desk 2: Volatility & FFT Cycles",
            },
            {
                id: "desk3",
                file: "intraday_volatility_clock_desk.md",
                outFile: "intraday_volatility_clock_desk.result.md",
                title: "Desk 3: Macro & Intraday Clock",
            },
        ];

        for (const d of wave1Desks) fleetState.set(d.id, "running");
        await logTimeline(formatFleetProgress(fleetState));

        const wave1Results = await ctx.parallel(
            wave1Desks.map((d) => async () => {
                const briefPath = join(workspace, "agents", "briefs", d.file);
                const outPath = join(workspace, "agents", "results", d.outFile);
                const briefText = existsSync(briefPath) ? readFileSync(briefPath, "utf8") : "";
                const prompt =
                    `${briefText}\n\n` +
                    `GROUNDING CONTRACT:\n${JSON.stringify(grounding || {}, null, 2)}\n\n` +
                    `Write your complete quantitative findings to ${outPath} and return a concise executive summary.`;
                const res = await ctx.agent(prompt, {
                    label: `${d.id}:${d.title}`,
                    agent: "general-purpose",
                });
                fleetState.set(d.id, "done");
                await logTimeline(formatFleetProgress(fleetState));
                return { desk: d.id, outPath, summary: res };
            })
        );

        // Phase 3: Wave 2 Adversarial Red-Team (Desk 4)
        ctx.phase("Phase 3: Wave 2 Adversarial Red-Team");
        fleetState.set("desk4", "running");
        await logTimeline(formatFleetProgress(fleetState));

        const desk4BriefPath = join(workspace, "agents", "briefs", "skeptical_risk_officer.md");
        const desk4OutPath = join(workspace, "agents", "results", "skeptical_risk_officer.result.md");
        const desk4Brief = existsSync(desk4BriefPath) ? readFileSync(desk4BriefPath, "utf8") : "";
        const desk4Prompt =
            `${desk4Brief}\n\n` +
            `WAVE 1 DESK OUTPUT SUMMARIES:\n${JSON.stringify(wave1Results, null, 2)}\n\n` +
            `Audit Wave 1 claims against ${join(workspace, "data", "anomaly_summary.json")}, write ${desk4OutPath}, and return your contrarian verdict.`;

        const desk4Res = await ctx.agent(desk4Prompt, {
            label: "desk4:Contrarian Red-Team",
            agent: "general-purpose",
        });
        fleetState.set("desk4", "done");
        await logTimeline(formatFleetProgress(fleetState));

        // Phase 4: Wave 3 Chief Quant PM Synthesis (Desk 5)
        ctx.phase("Phase 4: Wave 3 Chief PM Synthesis");
        fleetState.set("desk5", "running");
        await logTimeline(formatFleetProgress(fleetState));

        const desk5BriefPath = join(workspace, "agents", "briefs", "desk5_chief_pm_synthesis_brief.md");
        const finalReportPath = join(workspace, "reports", `FINAL_INSTITUTIONAL_QUANT_REPORT_${summary?.date_tag || "latest"}.md`);
        const desk5Brief = existsSync(desk5BriefPath) ? readFileSync(desk5BriefPath, "utf8") : "";
        const desk5Prompt =
            `${desk5Brief}\n\n` +
            `WAVE 1 RESULTS:\n${JSON.stringify(wave1Results, null, 2)}\n\n` +
            `WAVE 2 CONTRARIAN RED-TEAM:\n${desk4Res || ""}\n\n` +
            `Synthesize the final institutional report into ${finalReportPath} and return the executive action matrix.`;

        const desk5Res = await ctx.agent(desk5Prompt, {
            label: "desk5:Chief Quant PM Synthesis",
            agent: "general-purpose",
        });
        fleetState.set("desk5", "done");
        await logTimeline(formatFleetProgress(fleetState));

        return {
            engine: engineStep,
            finalReportPath,
            wave1Count: wave1Results.filter((x) => x !== null).length,
            redTeamComplete: Boolean(desk4Res),
            pmSynthesisComplete: Boolean(desk5Res),
        };
    },
});

const session = await joinSession({
    workflows: [marketQuantFleetWorkflow],
    hooks: {
        onSessionStart: async (input) => {
            await logTimeline(
                `${badge("⚡ MARKET-QUANT", ANSI.bgBadgeCyan)} Institutional Microstructure & Multi-Model Fleet Extension active ` +
                `${ANSI.gray}(tools: market_quant_scan, market_quant_hud, market_quant_verify_report │ workflow: market-quant-fleet)${ANSI.reset}`,
                { ephemeral: true }
            );
        },

        onUserPromptSubmitted: async (input) => {
            const prompt = String(input.prompt || "");
            if (/\b(market[- ]?quant|nifty|banknifty|microstructure|smart[- ]?money clock|chaikin|hurst|order[- ]?flow)\b/i.test(prompt)) {
                return {
                    additionalContext:
                        "The `market-quant` extension is loaded. Prefer calling `market_quant_scan` to run the deterministic Python quantitative engine and render the ANSI terminal HUD, `market_quant_hud` to display the colored terminal scorecard for an existing workspace, and `market_quant_verify_report` to audit synthesized Markdown reports against ground-truth JSON.",
                };
            }
        },

        onSubagentStart: async (input) => {
            const deskKey = matchDeskKey(input.agentName, input.agentDescription);
            if (!deskKey) return;

            fleetState.set(deskKey, "running");
            deskStartTimes.set(deskKey, performance.now());
            appendBlackboardEvent(activeWorkspace, {
                event: "subagent_start",
                desk: deskKey,
                agentName: input.agentName,
                agentDescription: input.agentDescription,
            });

            await logTimeline(
                `${badge("🚀 DESK START", ANSI.bgBadgeAmber)} ${ANSI.bold}${input.agentName || deskKey}${ANSI.reset} ` +
                `${ANSI.gray}(${input.agentDescription || "Specialist Quant Desk"})${ANSI.reset}\n` +
                formatFleetProgress(fleetState)
            );

            if (activeWorkspace) {
                const grounding = safeReadJson(join(activeWorkspace, "agents", "quorum_grounding.json"));
                if (grounding) {
                    return {
                        additionalContext:
                            `[MARKET-QUANT DETERMINISTIC GROUNDING CONTRACT — SHA256=${grounding.daily_data_sha256_16}]\n` +
                            `Never invent numeric values. Exclude zero-volume symbols (${JSON.stringify(grounding.cmf_invalid_symbols)}) from CMF rankings. ` +
                            `Enforce SIGNAL_SPEC thresholds: ${JSON.stringify(grounding.signal_spec)}.`,
                    };
                }
            }
        },

        onSubagentStop: async (input) => {
            const deskKey = matchDeskKey(input.agentName, input.agentDescription);
            if (!deskKey) return;

            fleetState.set(deskKey, "done");
            const started = deskStartTimes.get(deskKey);
            const elapsedSec = started ? ((performance.now() - started) / 1000).toFixed(1) : "?";
            appendBlackboardEvent(activeWorkspace, {
                event: "subagent_stop",
                desk: deskKey,
                agentName: input.agentName,
                elapsedSec: Number(elapsedSec) || null,
            });

            await logTimeline(
                `${badge("✔ DESK DONE", ANSI.bgBadgeGreen)} ${ANSI.bold}${input.agentName || deskKey}${ANSI.reset} ` +
                `completed in ${ANSI.teal}${elapsedSec}s${ANSI.reset}\n` +
                formatFleetProgress(fleetState)
            );
        },
    },

    tools: [
        {
            name: "market_quant_scan",
            description:
                "Runs the institutional market-quant Python engine (`market_quant_engine.py`) for a market (india, us, crypto, global), " +
                "computes multi-factor microstructure metrics (Spot vs Cash-ETF CMF, 70% contiguous Volume Profile with LVN air pockets, " +
                "60-day 1h Intraday Smart-Money Clock, variogram + R/S Hurst exponent, gated FFT cycles, and lag-adjusted macro correlations), " +
                "renders the ANSI-colored terminal scorecard in the CLI timeline, and returns all workspace artifact paths.",
            parameters: {
                type: "object",
                properties: {
                    market: {
                        type: "string",
                        enum: ["india", "us", "crypto", "global"],
                        description: "Target market universe preset (default: india).",
                    },
                    workspace: {
                        type: "string",
                        description: "Absolute workspace path (e.g., C:\\temp\\market-analysis\\22-10-26). Defaults to today's dated folder.",
                    },
                    asof: {
                        type: "string",
                        description: "Optional YYYY-MM-DD historical cutoff date for deterministic backtesting.",
                    },
                    reuse_data: {
                        type: "boolean",
                        description: "Reuse cached OHLCV CSVs in workspace/data if already downloaded (default: true).",
                    },
                    emit_fleet_plan_only: {
                        type: "boolean",
                        description: "Only emit data + agent briefs + fleet_dispatch.json without rendering PNG/HTML charts.",
                    },
                },
            },
            handler: async (args) => {
                const t0 = performance.now();
                const market = String(args?.market || "india").toLowerCase();
                const workspace = resolve(String(args?.workspace || defaultWorkspacePath()));
                const reuseData = args?.reuse_data !== false;
                const emitOnly = Boolean(args?.emit_fleet_plan_only);
                const asof = args?.asof ? String(args.asof) : null;

                activeWorkspace = workspace;
                fleetState.clear();

                await logTimeline(
                    `${badge("⚡ QUANT ENGINE", ANSI.bgBadgeCyan)} Launching ${ANSI.bold}${market.toUpperCase()}${ANSI.reset} scan ` +
                    `in ${ANSI.teal}${workspace}${ANSI.reset}${asof ? ` (asof=${asof})` : ""}...`,
                    { ephemeral: true }
                );

                const cliArgs = ["--market", market, "--workspace", workspace];
                if (reuseData) cliArgs.push("--reuse-data");
                if (emitOnly) cliArgs.push("--emit-fleet-plan-only");
                if (asof) cliArgs.push("--asof", asof);

                await runPythonEngine(cliArgs, (statusLine) => {
                    logTimeline(`${ANSI.cyan}⟳${ANSI.reset} ${ANSI.dim}${statusLine}${ANSI.reset}`, { ephemeral: true });
                });

                const summaryPath = join(workspace, "data", "anomaly_summary.json");
                const qualityPath = join(workspace, "data", "data_quality.json");
                const fleetPath = join(workspace, "agents", "fleet_dispatch.json");
                const groundingPath = join(workspace, "agents", "quorum_grounding.json");

                const summary = safeReadJson(summaryPath);
                const quality = safeReadJson(qualityPath);
                const elapsedSec = ((performance.now() - t0) / 1000).toFixed(2);

                if (summary) {
                    const hud = formatQuantHud(summary, quality);
                    await logTimeline(
                        `${hud}\n${badge("READY", ANSI.bgBadgeGreen)} Quant Engine finished in ${ANSI.bold}${elapsedSec}s${ANSI.reset} ` +
                        `│ SHA256: ${ANSI.teal}${quality?.daily_data_sha256_16 || "n/a"}${ANSI.reset}`
                    );
                }

                return JSON.stringify(
                    {
                        status: "success",
                        elapsed_seconds: Number(elapsedSec),
                        market,
                        workspace,
                        daily_data_sha256_16: quality?.daily_data_sha256_16 || null,
                        cmf_invalid_symbols: quality?.cmf_invalid_symbols || [],
                        primary_index: summary?.primary_index || null,
                        primary_index_snapshot: summary?.primary_index_snapshot || null,
                        spot_vs_etf_divergences: summary?.spot_vs_etf_divergences || [],
                        artifacts: {
                            anomaly_summary_json: summaryPath,
                            data_quality_json: qualityPath,
                            fleet_dispatch_json: fleetPath,
                            quorum_grounding_json: groundingPath,
                            intraday_clock_png: join(workspace, "reports", `intraday_smart_money_clock_${summary?.date_tag || "latest"}.png`),
                            social_infographic_png: join(workspace, "reports", `social_media_quant_infographic_${summary?.date_tag || "latest"}.png`),
                            interactive_dashboard_html: join(workspace, "reports", `market_quant_dashboard_${summary?.date_tag || "latest"}.html`),
                        },
                    },
                    null,
                    2
                );
            },
        },

        {
            name: "market_quant_hud",
            description:
                "Renders the colorful ANSI Institutional Quant Terminal Scorecard, Spot-vs-ETF Flow Matrix, Intraday Smart-Money Clock, " +
                "and Multi-Agent Fleet / Quorum Blackboard progress bar directly into the CLI timeline for an existing workspace.",
            parameters: {
                type: "object",
                properties: {
                    workspace: {
                        type: "string",
                        description: "Absolute path to the market-quant workspace (e.g., C:\\temp\\market-analysis\\22-10-26).",
                    },
                    open_dashboard: {
                        type: "boolean",
                        description: "If true, opens the interactive HTML dashboard in the default system browser.",
                    },
                },
                required: ["workspace"],
            },
            handler: async (args) => {
                const workspace = resolve(String(args.workspace));
                activeWorkspace = workspace;

                const summaryPath = join(workspace, "data", "anomaly_summary.json");
                const qualityPath = join(workspace, "data", "data_quality.json");
                const summary = safeReadJson(summaryPath);
                const quality = safeReadJson(qualityPath);

                if (!summary) {
                    return {
                        textResultForLlm: `No anomaly_summary.json found at ${summaryPath}. Run market_quant_scan first.`,
                        resultType: "failure",
                    };
                }

                // Check which desk reports already exist on disk
                const resultsDir = join(workspace, "agents", "results");
                if (existsSync(resultsDir)) {
                    const files = readdirSync(resultsDir).map((f) => f.toLowerCase());
                    for (const d of ["desk1", "desk2", "desk3", "desk4", "desk5"]) {
                        if (files.some((f) => f.includes(d))) {
                            fleetState.set(d, "done");
                        }
                    }
                }

                const hud = formatQuantHud(summary, quality);
                const fleetLine = formatFleetProgress(fleetState);
                await logTimeline(`${hud}\n${fleetLine}`);

                const htmlPath = join(workspace, "reports", `market_quant_dashboard_${summary.date_tag}.html`);
                if (args.open_dashboard && existsSync(htmlPath)) {
                    const openCmd =
                        process.platform === "win32"
                            ? `start "" "${htmlPath}"`
                            : process.platform === "darwin"
                              ? `open "${htmlPath}"`
                              : `xdg-open "${htmlPath}"`;
                    exec(openCmd, () => {});
                }

                return JSON.stringify(
                    {
                        status: "rendered",
                        workspace,
                        date_tag: summary.date_tag,
                        daily_data_sha256_16: quality?.daily_data_sha256_16 || null,
                        primary_index: summary.primary_index,
                        primary_close: summary.primary_index_snapshot?.close,
                        spot_vs_etf_flow_divergence: summary.spot_vs_etf_flow_divergence,
                        fleet_status: Object.fromEntries(fleetState.entries()),
                    },
                    null,
                    2
                );
            },
        },

        {
            name: "market_quant_verify_report",
            description:
                "Deterministically audits synthesized Markdown reports and specialist desk outputs in a market-quant workspace against " +
                "`anomaly_summary.json` and `data_quality.json` (checking zero-volume CMF exclusions, Spot vs Cash-ETF CMF accuracy, " +
                "POC/VAH/VAL levels, and SIGNAL_SPEC compliance).",
            parameters: {
                type: "object",
                properties: {
                    workspace: {
                        type: "string",
                        description: "Absolute path to the market-quant workspace.",
                    },
                    report_path: {
                        type: "string",
                        description: "Optional path to a specific Markdown file to audit. If omitted, audits all .md files in reports/ and agents/results/.",
                    },
                },
                required: ["workspace"],
            },
            handler: async (args) => {
                const workspace = resolve(String(args.workspace));
                const summary = safeReadJson(join(workspace, "data", "anomaly_summary.json"));
                const quality = safeReadJson(join(workspace, "data", "data_quality.json"));

                if (!summary || !quality) {
                    return {
                        textResultForLlm: `Missing anomaly_summary.json or data_quality.json in ${workspace}`,
                        resultType: "failure",
                    };
                }

                const targets = [];
                if (args.report_path && existsSync(args.report_path)) {
                    targets.push(resolve(args.report_path));
                } else {
                    for (const sub of ["reports", join("agents", "results")]) {
                        const d = join(workspace, sub);
                        if (existsSync(d)) {
                            for (const f of readdirSync(d)) {
                                if (f.endsWith(".md")) targets.push(join(d, f));
                            }
                        }
                    }
                }

                const invalidCmf = quality.cmf_invalid_symbols || [];
                const checks = [];
                let totalViolations = 0;

                for (const file of targets) {
                    const content = readFileSync(file, "utf8");
                    const fileViolations = [];

                    for (const sym of invalidCmf) {
                        const badPattern = new RegExp(`${sym}[^\\n]{0,40}CMF[^\\n]{0,15}[+-]\\d+\\.\\d+`, "i");
                        if (badPattern.test(content)) {
                            fileViolations.push(`Zero-volume symbol ${sym} assigned a numeric CMF value.`);
                        }
                    }

                    checks.push({
                        file,
                        size_bytes: content.length,
                        violations: fileViolations,
                        status: fileViolations.length === 0 ? "PASS" : "WARN",
                    });
                    totalViolations += fileViolations.length;
                }

                const badgeStyle = totalViolations === 0 ? ANSI.bgBadgeGreen : ANSI.bgBadgeAmber;
                await logTimeline(
                    `${badge("🔍 QUANT AUDIT", badgeStyle)} Audited ${ANSI.bold}${targets.length}${ANSI.reset} Markdown file(s) ` +
                    `against SHA256 ${ANSI.teal}${quality.daily_data_sha256_16}${ANSI.reset} │ Violations: ${ANSI.bold}${totalViolations}${ANSI.reset}`
                );

                return JSON.stringify(
                    {
                        status: totalViolations === 0 ? "PASS" : "WARN",
                        daily_data_sha256_16: quality.daily_data_sha256_16,
                        files_audited: targets.length,
                        total_violations: totalViolations,
                        checks,
                    },
                    null,
                    2
                );
            },
        },
    ],
});

sessionRef = session;

// Subscribe to tool events to render live Quorum Blackboard notifications in the CLI timeline
session.on("tool.execution_start", (event) => {
    const name = String(event.data?.toolName || "");
    const args = event.data?.arguments || {};
    if (name.includes("quorum-debate_start")) {
        logTimeline(
            `${badge("⚖️ QUORUM OPEN", ANSI.bgBadgePurple)} Topic: ${ANSI.bold}${args.topic || "Market Quant Debate"}${ANSI.reset}`,
            { ephemeral: true }
        );
    } else if (name.includes("quorum-board_post")) {
        const voteStr = args.vote ? ` │ Vote: ${args.vote === "yes" ? ANSI.green + "YES" : ANSI.red + "NO"}${ANSI.reset}` : "";
        logTimeline(
            `${badge(`⚖️ QUORUM R${args.round ?? 1}`, ANSI.bgBadgePurple)} Agent ${ANSI.bold}${args.agent || "desk"}${ANSI.reset} ` +
            `posted [${ANSI.amber}${args.stance || "EVIDENCE"}${ANSI.reset}]${voteStr}`
        );
    } else if (name.includes("quorum-tally_consensus")) {
        logTimeline(
            `${badge("⚖️ QUORUM TALLY", ANSI.bgBadgeCyan)} Tallying multi-agent ratification votes...`,
            { ephemeral: true }
        );
    }
});

