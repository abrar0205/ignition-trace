import { z } from "zod";

const time = z.number().finite().min(0).max(86_400_000);
const eventSchema = z.object({
  seq: z.number().int().min(0).max(1_000_000), t_ms: time,
  source: z.string().min(1).max(80),
  kind: z.enum(["signal", "frame", "span", "audio", "playback", "lifecycle"]),
  name: z.string().min(1).max(120),
  value: z.union([z.number().finite(), z.string().max(200), z.boolean(), z.null()]).default(null),
  duration_ms: time.nullable().default(null),
  correlation_id: z.string().max(80).nullable().default(null),
}).strict();
export const traceSchema = z.object({
  schema_version: z.literal("1.0").default("1.0"),
  title: z.string().min(1).max(120), source: z.enum(["synthetic", "android", "imported"]),
  duration_ms: time.refine(v => v > 0), clock: z.literal("session-monotonic-ms").default("session-monotonic-ms"),
  scenario: z.string().max(80).default("recording"), seed: z.number().int().min(0).max(4294967295).default(42),
  events: z.array(eventSchema).min(1).max(100_000),
}).strict().superRefine((t, ctx) => {
  const seen = new Set<number>(); let last = -1;
  for (const e of t.events) {
    if (seen.has(e.seq) || e.t_ms < last || e.t_ms + (e.duration_ms || 0) > t.duration_ms ||
        (["span", "frame"].includes(e.kind) && e.duration_ms == null)) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "Invalid event order, duration, or identity" }); return;
    }
    seen.add(e.seq); last = e.t_ms;
  }
});
export type Trace = z.infer<typeof traceSchema>;
export type TraceEvent = Trace["events"][number];
export type Budgets = { frame_ms: number; network_ms: number; startup_ms: number; audio_resume_ms: number; signal_gap_ms: number };
export const defaults: Budgets = { frame_ms: 50, network_ms: 500, startup_ms: 1500, audio_resume_ms: 500, signal_gap_ms: 1000 };
export const SPEED = "Vehicle.Speed";
export const BATTERY = "Vehicle.Powertrain.TractionBattery.StateOfCharge.Current";
export const scenarios = [
  { id: "mixed", name: "The imperfect commute", detail: "Four faults. One drive. Follow the evidence.", count: "04" },
  { id: "clean", name: "A clean baseline", detail: "A reference run with no injected faults.", count: "00" },
  { id: "audio-resume", name: "The silent return", detail: "Media resumes late after an interruption.", count: "01" },
  { id: "signal-stall", name: "A frozen speed signal", detail: "Vehicle updates disappear for five seconds.", count: "01" },
  { id: "network", name: "Through the tunnel", detail: "Catalog requests stall and time out.", count: "01" },
  { id: "frame-jank", name: "A screen that stutters", detail: "Rendering takes longer than its budget.", count: "01" },
] as const;
export type Scenario = typeof scenarios[number]["id"];

export function simulate(scenario: Scenario = "mixed", seed = 42): Trace {
  if (!scenarios.some(s => s.id === scenario) || !Number.isInteger(seed) || seed < 0 || seed > 4294967295) throw new Error("Invalid scenario or seed");
  let state = seed;
  const random = () => { state = (Math.imul(1664525, state) + 1013904223) >>> 0; return state / 4294967296; };
  const events: TraceEvent[] = [];
  const has = (fault: string) => scenario === fault || scenario === "mixed";
  const add = (t_ms: number, kind: TraceEvent["kind"], name: string, value: TraceEvent["value"] = null, duration_ms: number | null = null, source = "headunit", correlation_id: string | null = null) => events.push({ seq: events.length, t_ms, source, kind, name, value, duration_ms, correlation_id });
  for (let t = 0; t <= 60000; t += 250) {
    const speed = Math.round(Math.max(0, Math.min(110, (t / 1000 - 3) * 4, (60 - t / 1000) * 6) + Math.sin(t / 4000) * 4) * 100) / 100;
    if (!(has("signal-stall") && t >= 28000 && t < 33000)) add(t, "signal", SPEED, speed, null, "vehicle-sim");
    if (t % 1000 === 0) {
      add(t, "signal", BATTERY, Math.round((82 - t / 60000 * 2) * 100) / 100, null, "vehicle-sim");
      add(t, "signal", "Vehicle.Powertrain.Transmission.CurrentGear", speed === 0 ? 0 : 1, null, "vehicle-sim");
    }
    if (t % 1000 === 0 && t < 59000) {
      let d = 12 + Math.floor(random() * 5);
      if (has("frame-jank") && t >= 40000 && t <= 44000) d += 80 + Math.floor(random() * 60);
      add(t, "frame", "frame.render", null, d);
    }
    if (t % 5000 === 0 && t > 0 && t < 55000) {
      const d = 70 + Math.floor(random() * 120), timeout = has("network") && t >= 20000 && t <= 25000;
      add(t, "span", "http.catalog", timeout ? "timeout" : "200", timeout ? 2500 : d, "headunit", `request-${t}`);
    }
  }
  add(0, "lifecycle", "app", "created"); add(0, "span", "app.startup", null, 680);
  add(1000, "audio", "media", "gain", null, "headunit", "media-main");
  add(1100, "playback", "media", "playing", null, "headunit", "media-main");
  add(12000, "audio", "media", "loss_transient", null, "headunit", "media-main");
  add(12030, "playback", "media", "paused", null, "headunit", "media-main");
  add(18000, "audio", "media", "gain", null, "headunit", "media-main");
  add(has("audio-resume") ? 20400 : 18120, "playback", "media", "playing", null, "headunit", "media-main");
  events.sort((a, b) => a.t_ms - b.t_ms || a.seq - b.seq); events.forEach((e, i) => e.seq = i);
  return traceSchema.parse({ title: `Alpine commute / ${scenario}`, source: "synthetic", scenario, seed, duration_ms: 60000, events });
}

export type Finding = { id: string; code: string; title: string; source: string; start_ms: number; end_ms: number; observed_ms: number; budget_ms: number; evidence: number[] };
export type Report = { budgets: Budgets; event_count: number; finding_count: number; findings: Finding[]; omitted_findings: number; metrics: { frame_p95_ms: number | null; network_p95_ms: number | null; startup_max_ms: number | null; audio_resume_max_ms: number | null } };
const round = (n: number) => Math.round(n * 1000) / 1000;
export function percentile(values: number[], p: number) {
  if (!values.length) return null;
  const v = [...values].sort((a, b) => a - b), at = (v.length - 1) * p, i = Math.floor(at);
  return round(v[i] + (v[Math.min(i + 1, v.length - 1)] - v[i]) * (at - i));
}
export function analyze(trace: Trace, budgets: Budgets = defaults): Report {
  for (const [k, v] of Object.entries(budgets)) if (!Number.isFinite(v) || v <= 0 || v > (k === "frame_ms" ? 1000 : 60000)) throw new Error("Invalid budget");
  const findings: Finding[] = [], frames: number[] = [], network: number[] = [], startup: number[] = [], resumes: number[] = [];
  const signals = new Map<string, TraceEvent[]>(), pending = new Map<string, TraceEvent>();
  function issue(code: string, title: string, e: TraceEvent, value: number, budget: number, end = e.t_ms, evidence = [e.seq]) {
    findings.push({ id: `${code}-${e.seq}`, code, title, source: e.source, start_ms: e.t_ms, end_ms: end, observed_ms: round(value), budget_ms: budget, evidence });
  }
  for (const e of trace.events) {
    const d = e.duration_ms || 0;
    if (e.kind === "frame") { frames.push(d); if (d > budgets.frame_ms) issue("FRAME_BUDGET", "Slow frame", e, d, budgets.frame_ms, e.t_ms + d); }
    if (e.kind === "span" && e.name.startsWith("http.")) { network.push(d); if (e.value === "timeout" || d > budgets.network_ms) issue("NETWORK_BUDGET", "Network request exceeded budget", e, d, budgets.network_ms, e.t_ms + d); }
    if (e.kind === "span" && e.name === "app.startup") { startup.push(d); if (d > budgets.startup_ms) issue("STARTUP_BUDGET", "Slow application startup", e, d, budgets.startup_ms, e.t_ms + d); }
    if (e.kind === "signal" && e.name === SPEED) { const k = JSON.stringify([e.source, e.name]); if (!signals.has(k)) signals.set(k, []); signals.get(k)!.push(e); }
    const key = JSON.stringify([e.source, e.name, e.correlation_id]);
    if (e.kind === "audio") { if (e.value === "gain") { if (!pending.has(key)) pending.set(key, e); } else pending.delete(key); }
    if (e.kind === "playback" && e.value === "playing" && pending.has(key)) {
      const gained = pending.get(key)!; pending.delete(key); const d = e.t_ms - gained.t_ms; resumes.push(d);
      if (d > budgets.audio_resume_ms) issue("AUDIO_RESUME", "Late playback after focus gain", gained, d, budgets.audio_resume_ms, e.t_ms, [gained.seq, e.seq]);
    }
  }
  for (const gained of pending.values()) { const wait = trace.duration_ms - gained.t_ms; if (wait > budgets.audio_resume_ms) issue("AUDIO_UNRESOLVED", "No observed playback after focus gain", gained, wait, budgets.audio_resume_ms, trace.duration_ms); }
  for (const events of signals.values()) events.forEach((e, i) => {
    const end = i + 1 < events.length ? events[i + 1].t_ms : trace.duration_ms, gap = end - e.t_ms;
    if (gap > budgets.signal_gap_ms) issue("SIGNAL_GAP", "Speed signal went stale", e, gap, budgets.signal_gap_ms, end, [e.seq, ...(i + 1 < events.length ? [events[i + 1].seq] : [])]);
  });
  findings.sort((a, b) => a.start_ms - b.start_ms || (a.code < b.code ? -1 : a.code > b.code ? 1 : 0));
  const maximum = (values: number[]) => values.length ? values.reduce((a, b) => Math.max(a, b)) : null;
  return { budgets, event_count: trace.events.length, finding_count: findings.length, findings: findings.slice(0, 200), omitted_findings: Math.max(0, findings.length - 200), metrics: { frame_p95_ms: percentile(frames, .95), network_p95_ms: percentile(network, .95), startup_max_ms: maximum(startup), audio_resume_max_ms: maximum(resumes) } };
}

export function stateAt(trace: Trace, cursor: number) {
  if (!Number.isFinite(cursor) || cursor < 0 || cursor > trace.duration_ms) throw new Error("Cursor outside recording");
  const signals = new Map<string, { value: TraceEvent["value"]; age_ms: number; source: string }>();
  let playback: TraceEvent["value"] = "unknown";
  for (const e of trace.events) { if (e.t_ms > cursor) break; if (e.kind === "signal") signals.set(e.name, { value: e.value, age_ms: cursor - e.t_ms, source: e.source }); if (e.kind === "playback") playback = e.value; }
  return { signals, playback };
}
export function compare(baseline: Report, candidate: Report) {
  if (Object.keys(defaults).some(k => baseline.budgets[k as keyof Budgets] !== candidate.budgets[k as keyof Budgets])) throw new Error("Budgets must match");
  return Object.fromEntries(Object.entries(baseline.metrics).map(([k, v]) => { const now = candidate.metrics[k as keyof Report["metrics"]]; return [k, v == null || now == null ? null : round(now - v)]; }));
}
export function download(name: string, data: unknown, type = "application/json") {
  const url = URL.createObjectURL(new Blob([typeof data === "string" ? data : JSON.stringify(data, null, 2)], { type }));
  const a = document.createElement("a"); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function htmlReport(trace: Trace, report: Report) {
  const esc = (s: unknown) => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
  return `<!doctype html><html lang="en"><meta charset="utf-8"><title>IgnitionTrace report</title><style>body{font:16px system-ui;max-width:1000px;margin:48px auto;padding:24px;color:#1f2b40}table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #ddd;padding:12px;text-align:left}</style><h1>IgnitionTrace</h1><h2>${esc(trace.title)}</h2><p>Source: ${esc(trace.source)} · ${report.event_count} events · ${report.finding_count} findings</p><p>Threshold observations, not proof of root cause. Replay reconstructs captured event state.</p><table><tr><th>Finding</th><th>Time (ms)</th><th>Observed / budget (ms)</th><th>Event IDs</th></tr>${report.findings.map(f => `<tr><td>${esc(f.title)}</td><td>${f.start_ms}</td><td>${f.observed_ms} / ${f.budget_ms}</td><td>${f.evidence.join(", ")}</td></tr>`).join("")}</table><p>${report.omitted_findings} additional findings omitted.</p><h3>Budgets</h3><pre>${esc(JSON.stringify(report.budgets, null, 2))}</pre></html>`;
}
