/**
 * <LiveEventLog /> tests — slice 4.7-theater commit 2.
 *
 * Compact timeline of the last 3 events below the 4-up agent grid.
 * Density toggle ("major" vs "all") filters BEFORE the truncation,
 * so the user sees the 3 most-recent events matching their density
 * preference.
 *
 * Renders empty-state when no events to show (initial theater state
 * before any callbacks fire — "Waiting for first event"-style copy).
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { AgentSummaryRow } from "@/lib/backend";

afterEach(() => cleanup());

describe("<LiveEventLog />", () => {
  it("renders empty-state copy when events array is empty", async () => {
    // Initial state before any callbacks have fired. Don't render an
    // empty <ul> — surface that the crew is still spinning up.
    const { LiveEventLog } = await import("@/components/live-event-log");
    render(<LiveEventLog events={[]} />);
    expect(screen.getByText(/waiting|no events|spinning/i)).toBeDefined();
  });

  it("renders a single event with agent_role + event-type indicator", async () => {
    const events: AgentSummaryRow[] = [
      {
        event: "task_completed",
        timestamp: "2026-06-09T10:05:00+00:00",
        elapsed_ms: 312000,
        task_index: 1,
        agent_role: "Travel Researcher",
      },
    ];
    const { LiveEventLog } = await import("@/components/live-event-log");
    render(<LiveEventLog events={events} />);
    expect(screen.getByText(/Travel Researcher/)).toBeDefined();
  });

  it("truncates to the most recent 3 events when given more than 3", async () => {
    // The log is a "what just happened" feed — older events live in
    // the post-completion PlanHistoryPanel (commit 4 settle handoff).
    // Cap keeps the surface scannable; user toggles density for more.
    const events: AgentSummaryRow[] = [
      {
        event: "task_completed",
        timestamp: "2026-06-09T10:01:00+00:00",
        elapsed_ms: 60000,
        task_index: 1,
        agent_role: "Travel Researcher",
      },
      {
        event: "task_completed",
        timestamp: "2026-06-09T10:02:00+00:00",
        elapsed_ms: 120000,
        task_index: 2,
        agent_role: "Local Coorg Expert",
      },
      {
        event: "task_completed",
        timestamp: "2026-06-09T10:03:00+00:00",
        elapsed_ms: 180000,
        task_index: 3,
        agent_role: "Logistics Planner",
      },
      {
        event: "task_completed",
        timestamp: "2026-06-09T10:04:00+00:00",
        elapsed_ms: 240000,
        task_index: 4,
        agent_role: "Budget Auditor",
      },
      {
        event: "callback_summary",
        step_callback_count: 0,
        task_callback_count: 4,
      },
    ];
    const { LiveEventLog } = await import("@/components/live-event-log");
    render(<LiveEventLog events={events} />);
    // 3 list items rendered, not 5.
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
  });
});
