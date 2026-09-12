import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { analyze, compare, defaults, htmlReport, simulate, stateAt, traceSchema, type Scenario } from "../lib/trace.ts";

const corpus = JSON.parse(readFileSync(new URL("../../tests/fixtures/conformance.json", import.meta.url), "utf8"));
for (const { trace, report } of corpus) {
  test(`Python/TypeScript conformance: ${trace.scenario} seed ${trace.seed}`, () => {
    const { trace_sha256: _hash, schema_version: _schema, engine_version: _engine, ...expected } = report;
    assert.deepEqual(analyze(traceSchema.parse(trace)), expected);
    assert.deepEqual(analyze(simulate(trace.scenario as Scenario, trace.seed)), expected);
  });
}
test("Seeking backwards reconstructs state without mutating events", () => {
  const t = simulate(), before = JSON.stringify(t);
  assert.equal(stateAt(t, 20400).playback, "playing");
  assert.equal(stateAt(t, 20399).playback, "paused");
  assert.equal(stateAt(t, 32000).signals.get("Vehicle.Speed")?.age_ms, 4250);
  assert.equal(JSON.stringify(t), before);
  assert.throws(() => stateAt(t, NaN));
  assert.throws(() => stateAt(t, 60001));
});
test("Imports reject duplicate IDs, backwards clocks and missing span duration", () => {
  const t = simulate();
  assert.equal(traceSchema.safeParse({ ...t, events: [t.events[0], t.events[0]] }).success, false);
  assert.equal(traceSchema.safeParse({ ...t, events: [...t.events].reverse() }).success, false);
  assert.equal(traceSchema.safeParse({ ...t, events: [{ ...t.events[0], kind: "span", duration_ms: null }] }).success, false);
  assert.equal(traceSchema.safeParse({ ...t, duration_ms: Infinity }).success, false);
  assert.equal(traceSchema.safeParse({ ...t, unexpected: true }).success, false);
});
test("Comparison uses matching budgets and report export escapes imported text", () => {
  const t = simulate(), r = analyze(t);
  assert.throws(() => compare(r, analyze(t, { ...defaults, frame_ms: 100 })));
  const html = htmlReport({ ...t, title: '<script>alert("x")</script>' }, r);
  assert.ok(!html.includes("<script>"));
  assert.ok(html.includes("&lt;script&gt;"));
});
test("Audio evidence is scoped to the player and unresolved focus is explicit", () => {
  const t = traceSchema.parse({ title: "Recording", source: "android", duration_ms: 3000, events: [
    { seq: 0, t_ms: 0, source: "app", kind: "audio", name: "media", value: "gain", correlation_id: "a" },
    { seq: 1, t_ms: 100, source: "app", kind: "playback", name: "media", value: "playing", correlation_id: "b" },
  ] });
  assert.equal(analyze(t).findings[0].code, "AUDIO_UNRESOLVED");
  assert.equal(analyze(t).metrics.audio_resume_max_ms, null);
});
