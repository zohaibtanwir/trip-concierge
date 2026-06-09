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

  it("renders agent role + timestamp + duration on task_completed row (mirrors PlanHistoryPanel)", async () => {
    // Replay-modal hotfix: rows must surface agent identity + timing
    // (not just an event-name label). Compact one-liner still — but
    // with the full information density PlanHistoryPanel uses, so the
    // user gets context, not a bare event label.
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
    // 312000ms → "312.0s" via _formatDuration (matches PlanHistoryPanel).
    expect(screen.getByText(/312\.0\s*s/)).toBeDefined();
  });

  it("renders check_circle icon for task_completed (mirrors PlanHistoryPanel)", async () => {
    // Visual disambiguation: check_circle = completion, psychology =
    // reasoning, summarize = tally. Same icons as PlanHistoryPanel
    // for cross-surface consistency.
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
    expect(screen.getByText("check_circle")).toBeDefined();
  });

  it("renders psychology icon for AgentFinish (mirrors PlanHistoryPanel)", async () => {
    const events: AgentSummaryRow[] = [
      {
        event: "AgentFinish",
        timestamp: "2026-06-09T10:04:00+00:00",
        elapsed_ms: 5000,
        agent_role: "Local Coorg Expert",
      },
    ];
    const { LiveEventLog } = await import("@/components/live-event-log");
    render(<LiveEventLog events={events} />);
    expect(screen.getByText("psychology")).toBeDefined();
  });

  it("renders summarize icon + user-facing copy for callback_summary", async () => {
    // Mirrors PlanHistoryPanel's §9.15 summary-row treatment.
    const events: AgentSummaryRow[] = [
      {
        event: "callback_summary",
        step_callback_count: 7,
        task_callback_count: 3,
      },
    ];
    const { LiveEventLog } = await import("@/components/live-event-log");
    render(<LiveEventLog events={events} />);
    expect(screen.getByText("summarize")).toBeDefined();
    expect(screen.getByText(/7 reasoning steps · 3 agent completions/)).toBeDefined();
  });

  it("task_completed without agent_role falls back to task_index → canonical role (Coorg/Manali)", async () => {
    // Pre-Path-B legacy data: agent_role missing, task_index present.
    // task_index=1 → "Travel Researcher" so the row reads naturally
    // instead of literal "task_completed".
    const events: AgentSummaryRow[] = [
      {
        event: "task_completed",
        timestamp: "2026-06-06T16:08:00+00:00",
        elapsed_ms: 312000,
        task_index: 1,
        // No agent_role — pre-Path-B shape.
      },
    ];
    const { LiveEventLog } = await import("@/components/live-event-log");
    render(<LiveEventLog events={events} />);
    expect(screen.getByText(/Travel Researcher/)).toBeDefined();
    // Negative: the bare event name MUST NOT appear as the row title.
    expect(screen.queryByText(/^task_completed$/)).toBeNull();
  });

  it("AgentFinish without agent_role renders 'Reasoning step' (no proximity inference)", async () => {
    // Pre-Path-B AgentFinish has no agent_role + no task_index. We
    // explicitly skip proximity-based inference (too brittle across
    // live-mode newest-first ordering); render a generic but readable
    // title instead of literal "AgentFinish".
    const events: AgentSummaryRow[] = [
      {
        event: "AgentFinish",
        timestamp: "2026-06-06T16:07:30+00:00",
        elapsed_ms: 5000,
      },
    ];
    const { LiveEventLog } = await import("@/components/live-event-log");
    render(<LiveEventLog events={events} />);
    expect(screen.getByText(/Reasoning step/i)).toBeDefined();
    // Negative: the literal event name MUST NOT appear as the row title.
    expect(screen.queryByText(/^AgentFinish$/)).toBeNull();
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
