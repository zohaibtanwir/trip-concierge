/**
 * Shared agent_summary test fixtures.
 *
 * Slice 4d0 Sunday smoke (2026-06-07) — extracted from the in-place
 * fixtures in plan-history-panel.test.tsx, trip-detail.test.tsx, and
 * backend.test.ts. Three test files had three independent copies of the
 * same fixture shape. When backend evolved (slice qek-a:
 * {agent, step, duration_ms, tokens} → {event, timestamp, elapsed_ms,
 * output_excerpt} + callback_summary variant), all three stayed
 * green against their self-references. UI rendered "undefinedms" in
 * production.
 *
 * **Source of truth:** real Coorg smoke JobRun.agent_summary JSONB,
 * trip 449ba46a-7264-4428-8542-d7cf83461daa, captured 2026-06-06
 * 16:08-16:18 UTC. When the backend step_callback shape changes again,
 * re-snapshot from real data, not from the component's read-shape.
 *
 * Each named export covers a discriminator value of AgentSummaryRow's
 * discriminated union. Fixtures should mirror the cardinality of event
 * types in the data, not the cardinality of test cases the developer
 * cared about — see experiments/01-langfuse.md "heterogeneous-event-
 * types-require-fixtures-that-cover-all-variants" observation.
 */

import type { AgentSummaryRow } from "@/lib/backend";

/** A single AgentFinish event — per-agent reasoning step record.
 *
 * Path B (hotfix-kyh reframe 2026-06-08): includes agent_role so the
 * row renders "Travel Researcher" instead of literal "AgentFinish".
 */
export const AGENT_FINISH_FIXTURE: AgentSummaryRow = {
  event: "AgentFinish",
  timestamp: "2026-06-06T16:12:12.550713+00:00",
  elapsed_ms: 224413,
  output_excerpt: "Great — I now have the geographic context to anchor the cost validation.",
  agent_role: "Travel Researcher",
};

/** A single task_completed event — CrewAI agent-completion marker.
 *
 * Path B: no longer filtered out by the renderer; surfaces with
 * check_circle icon + agent_role title. Primary visibility surface
 * when step_callback doesn't fire (the common case under CrewAI 1.14.5
 * with single-shot agent outputs).
 */
export const TASK_COMPLETED_FIXTURE: AgentSummaryRow = {
  event: "task_completed",
  timestamp: "2026-06-06T16:13:33.541264+00:00",
  elapsed_ms: 305402,
  task_index: 1,
  output_excerpt: "Now I have all the information I need to compile the complete response.",
  agent_role: "Local Coorg Expert",
};

/**
 * The single callback_summary tally event — the qek-a observability
 * marker. Structurally heterogeneous from AgentFinish: no timestamp,
 * no elapsed_ms, two count fields instead.
 */
export const CALLBACK_SUMMARY_FIXTURE: AgentSummaryRow = {
  event: "callback_summary",
  step_callback_count: 7,
  task_callback_count: 3,
};

/**
 * Full agent_summary array mirroring a real Coorg smoke run shape:
 * 3 AgentFinish + 1 task_completed (to verify filtering) + 1
 * callback_summary (to verify the count-tally rendering). Smaller than
 * the production 11-event array but represents all three discriminator
 * values — fixture cardinality follows schema variants, not test-case
 * importance.
 */
export const FULL_SUMMARY_FIXTURE: AgentSummaryRow[] = [
  AGENT_FINISH_FIXTURE,
  {
    event: "AgentFinish",
    timestamp: "2026-06-06T16:13:33.509855+00:00",
    elapsed_ms: 305371,
    output_excerpt: "Now I have all the information I need to compile the complete response.",
  },
  TASK_COMPLETED_FIXTURE,
  {
    event: "AgentFinish",
    timestamp: "2026-06-06T16:15:27.550043+00:00",
    elapsed_ms: 419410,
    output_excerpt:
      "Great, I have the travel time data I need. Here's my full logistics assessment.",
  },
  CALLBACK_SUMMARY_FIXTURE,
];
