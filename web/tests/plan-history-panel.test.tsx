/**
 * <PlanHistoryPanel /> test (slice 4.3, PRD §F8 partial) — fixture
 * repaired during slice 4d0 Sunday smoke (2026-06-07).
 *
 * IMPORTANT: the prior _SUMMARY fixture used the slice 4.3 pre-qek-a
 * shape {agent, step, duration_ms, tokens} — which was self-referential
 * to the component's read-shape and didn't match what JobRun.agent_summary
 * actually contains. All 4 tests passed against the fixture; the UI
 * rendered "undefinedms" rows in production.
 *
 * Fixture below is derived from the actual Coorg smoke trip JSONB
 * (449ba46a-…, captured 2026-06-06 16:08-16:18 UTC). When the backend
 * step_callback shape changes again, this fixture must be re-snapshotted
 * — not invented from the component's read-shape.
 *
 * Behavior pinned:
 * - Reads agent_summary prop (array of {event, timestamp, elapsed_ms, ...}).
 * - Filters to AgentFinish + callback_summary (skips task_completed noise).
 * - Renders one row per filtered event with the event label + time + duration.
 * - Collapsible: defaults to collapsed; clicking the header expands.
 * - Empty agent_summary renders an honest "No agent activity recorded" line
 *   (covers legacy pre-qek-a JobRuns).
 *
 * Tap-to-expand-step-reasoning per PRD §F8 acceptance is deferred until
 * backend enrichment ships per-step reasoning data — tracked as
 * trip-concierge-gco backend enrichment + trip-concierge-auu §17.5.
 * Backend agent_role enrichment so rows can show "Researcher" instead of
 * "AgentFinish" tracked as a separate P2.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { AgentSummaryRow } from "@/lib/backend";

afterEach(() => cleanup());

const _SUMMARY: AgentSummaryRow[] = [
  {
    event: "AgentFinish",
    timestamp: "2026-06-06T16:12:12.550713+00:00",
    elapsed_ms: 224413,
    output_excerpt: "Great — I now have the geographic context to anchor the cost validation.",
  },
  {
    event: "AgentFinish",
    timestamp: "2026-06-06T16:13:33.509855+00:00",
    elapsed_ms: 305371,
    output_excerpt: "Now I have all the information I need to compile the complete response.",
  },
  // task_completed event MUST be present in the fixture to verify it
  // gets filtered out. If the component stops filtering, this test
  // catches the regression.
  {
    event: "task_completed",
    timestamp: "2026-06-06T16:13:33.541264+00:00",
    elapsed_ms: 305402,
    task_index: 1,
    output_excerpt: "Now I have all the information I need to compile the complete response.",
  },
  {
    event: "AgentFinish",
    timestamp: "2026-06-06T16:15:27.550043+00:00",
    elapsed_ms: 419410,
    output_excerpt:
      "Great, I have the travel time data I need. Here's my full logistics assessment.",
  },
  {
    event: "callback_summary",
    timestamp: "2026-06-06T16:18:58.526116+00:00",
    elapsed_ms: 630000,
  },
];

describe("<PlanHistoryPanel />", () => {
  it("renders one row per AgentFinish + callback_summary, filters task_completed", async () => {
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={_SUMMARY} defaultExpanded />);
    // 3 AgentFinish + 1 callback_summary = 4 visible rows.
    // task_completed at idx=2 must NOT render — that's Option C filter behavior.
    const agentFinishLabels = screen.getAllByText(/AgentFinish/);
    expect(agentFinishLabels).toHaveLength(3);
    expect(screen.getByText(/callback_summary/)).toBeDefined();
    // Negative assertion: task_completed event filtered out.
    expect(screen.queryByText(/task_completed/)).toBeNull();
  });

  it("renders durations alongside event labels", async () => {
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={_SUMMARY} defaultExpanded />);
    // First AgentFinish elapsed_ms=224413 → formatted as "224.4s".
    expect(screen.getByText(/224\.4\s*s/i)).toBeDefined();
  });

  it("renders 'No agent activity recorded' when summary is empty", async () => {
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={[]} defaultExpanded />);
    expect(screen.getByText(/no agent activity recorded/i)).toBeDefined();
  });

  it("renders 'No agent activity recorded' when summary contains only filtered events", async () => {
    // Regression guard: if a JobRun's agent_summary happens to contain
    // ONLY task_completed events (unlikely but possible), the panel
    // should fall through to the empty state, not render an empty <ul>.
    const onlyTaskCompleted: AgentSummaryRow[] = [
      {
        event: "task_completed",
        timestamp: "2026-06-06T16:13:33.541264+00:00",
        elapsed_ms: 305402,
        task_index: 1,
      },
    ];
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={onlyTaskCompleted} defaultExpanded />);
    expect(screen.getByText(/no agent activity recorded/i)).toBeDefined();
  });

  it("shows the 'How this plan was made' header trigger", async () => {
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={_SUMMARY} />);
    expect(screen.getByText(/how this plan was made/i)).toBeDefined();
  });
});
