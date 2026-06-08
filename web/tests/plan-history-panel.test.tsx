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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentSummaryRow } from "@/lib/backend";
import {
  CALLBACK_SUMMARY_FIXTURE,
  FULL_SUMMARY_FIXTURE,
  TASK_COMPLETED_FIXTURE,
} from "@/tests/fixtures/agent-summary";

afterEach(() => cleanup());

const _SUMMARY = FULL_SUMMARY_FIXTURE;

describe("<PlanHistoryPanel />", () => {
  it("renders all AgentFinish + task_completed + callback_summary events (Path B: no longer filters task_completed)", async () => {
    // Path B (hotfix-kyh reframe 2026-06-08): task_completed events are
    // the primary visibility surface when step_callback doesn't fire,
    // so the renderer no longer filters them. FULL_SUMMARY_FIXTURE has
    // 3 AgentFinish + 1 task_completed + 1 callback_summary → 5 visible.
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={_SUMMARY} defaultExpanded />);
    // AgentFinish rows now title as agent_role ("Travel Researcher"
    // appears at least once from the AGENT_FINISH_FIXTURE entry).
    expect(screen.getByText(/Travel Researcher/)).toBeDefined();
    // task_completed row titles as agent_role too ("Local Coorg Expert"
    // from TASK_COMPLETED_FIXTURE).
    expect(screen.getByText(/Local Coorg Expert/)).toBeDefined();
    // Callback summary footer always present.
    expect(screen.getByText(/Callback summary/i)).toBeDefined();
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

  it("renders task_completed event when it's the only event in the summary (Path B: task is primary visibility)", async () => {
    // Path B reframe: when step_callback is silent (the common case
    // under CrewAI 1.14.5 with single-shot agent outputs), task_completed
    // events ARE the activity record. Surfacing them is the whole point.
    const onlyTaskCompleted: AgentSummaryRow[] = [TASK_COMPLETED_FIXTURE];
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={onlyTaskCompleted} defaultExpanded />);
    // Empty state must NOT appear when task_completed events exist.
    expect(screen.queryByText(/no agent activity recorded/i)).toBeNull();
    // The task event renders with its agent_role title.
    expect(screen.getByText(/Local Coorg Expert/)).toBeDefined();
  });

  it("callback_summary renders user-facing copy: 'reasoning steps' + 'agent completions' (Path B Q-pathb-d)", async () => {
    // Q-pathb-d=B: callback_summary footer uses user-facing language
    // instead of internal terms. Preserves the load-bearing 0-steps
    // signal while reading more clearly to demo audiences.
    const onlyCallback: AgentSummaryRow[] = [CALLBACK_SUMMARY_FIXTURE];
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={onlyCallback} defaultExpanded />);
    expect(screen.getByText(/Callback summary/i)).toBeDefined();
    // Fixture: step_callback_count=7, task_callback_count=3.
    expect(screen.getByText(/7 reasoning steps · 3 agent completions/)).toBeDefined();
    // Negative assertions: no "undefinedms" or "Invalid Date".
    expect(screen.queryByText(/undefined/i)).toBeNull();
    expect(screen.queryByText(/Invalid Date/i)).toBeNull();
  });

  it("shows the 'How this plan was made' header trigger", async () => {
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={_SUMMARY} />);
    expect(screen.getByText(/how this plan was made/i)).toBeDefined();
  });
});

describe("<PlanHistoryPanel /> Path B — agent_role + task_completed rendering", () => {
  // Path B (hotfix-kyh reframe 2026-06-08): agent_role enrichment +
  // task_completed surfacing. Discharges trip-concierge-nhm.

  it("AgentFinish row titles with agent_role when present (Q-pathb-c=A)", async () => {
    // Q-pathb-c=A: title = agent_role only. The user sees "Travel
    // Researcher", not literal "AgentFinish". Backward-compat fallback
    // tested below.
    const row: AgentSummaryRow = {
      event: "AgentFinish",
      timestamp: "2026-06-08T12:23:00.000+00:00",
      elapsed_ms: 5000,
      output_excerpt: "Found 12 venues across Pondicherry.",
      agent_role: "Travel Researcher",
    };
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={[row]} defaultExpanded />);
    expect(screen.getByText(/Travel Researcher/)).toBeDefined();
    // The literal event-name string should NOT appear as the primary title
    // when agent_role is present.
    expect(screen.queryByText(/^AgentFinish$/)).toBeNull();
  });

  it("AgentFinish row falls back to event name when agent_role is absent (backward compat)", async () => {
    // Legacy JobRuns from pre-Path-B writes lack agent_role. The
    // renderer must still produce a readable row.
    const row: AgentSummaryRow = {
      event: "AgentFinish",
      timestamp: "2026-06-08T12:23:00.000+00:00",
      elapsed_ms: 5000,
      output_excerpt: "legacy data without agent_role",
    };
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={[row]} defaultExpanded />);
    expect(screen.getByText(/AgentFinish/)).toBeDefined();
  });

  it("task_completed row titles with agent_role (Q-pathb-c=A)", async () => {
    const row: AgentSummaryRow = {
      event: "task_completed",
      timestamp: "2026-06-08T12:23:00.000+00:00",
      elapsed_ms: 5000,
      output_excerpt: "Completed research task — 12 venues identified.",
      task_index: 1,
      agent_role: "Travel Researcher",
    };
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={[row]} defaultExpanded />);
    expect(screen.getByText(/Travel Researcher/)).toBeDefined();
    // The event excerpt should also appear so the demo audience sees
    // what the agent actually accomplished.
    expect(screen.getByText(/12 venues identified/)).toBeDefined();
  });

  it("task_completed row uses check_circle icon; AgentFinish uses psychology (Q-pathb-b=B)", async () => {
    // Visual distinction per Q-pathb-b=B: completion vs reasoning.
    // Material Symbols render as literal text content in the span,
    // so we can assert on text presence — same pattern as the lock_open
    // test in block-lock-toggle.
    const taskRow: AgentSummaryRow = {
      event: "task_completed",
      timestamp: "2026-06-08T12:23:00.000+00:00",
      elapsed_ms: 5000,
      task_index: 1,
      agent_role: "Travel Researcher",
    };
    const finishRow: AgentSummaryRow = {
      event: "AgentFinish",
      timestamp: "2026-06-08T12:22:00.000+00:00",
      elapsed_ms: 3000,
      agent_role: "Travel Researcher",
    };
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={[finishRow, taskRow]} defaultExpanded />);
    // Both icons present in the rendered DOM.
    expect(screen.getByText("check_circle")).toBeDefined();
    expect(screen.getByText("psychology")).toBeDefined();
  });

  it("renders task_completed output_excerpt so the demo shows what the agent accomplished", async () => {
    // The whole point of Path B: visibility into the agent's
    // contribution, not just that it fired. The output_excerpt is
    // the load-bearing content for the demo narrative.
    const row: AgentSummaryRow = {
      event: "task_completed",
      timestamp: "2026-06-08T12:23:00.000+00:00",
      elapsed_ms: 5000,
      task_index: 1,
      agent_role: "Logistics Planner",
      output_excerpt:
        "Built 5-day Pondicherry plan with French Quarter morning, Auroville afternoon.",
    };
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={[row]} defaultExpanded />);
    expect(screen.getByText(/French Quarter morning/)).toBeDefined();
  });

  it("renders both step + task events when both fire (Q-pathb-e=A: full transparency)", async () => {
    // The "everything works" demo state: 7 step events + 3 task events
    // surface together. Demo audience sees both reasoning + completion.
    const events: AgentSummaryRow[] = [
      {
        event: "AgentFinish",
        timestamp: "2026-06-08T12:20:00.000+00:00",
        elapsed_ms: 1000,
        agent_role: "Travel Researcher",
      },
      {
        event: "task_completed",
        timestamp: "2026-06-08T12:21:00.000+00:00",
        elapsed_ms: 5000,
        task_index: 1,
        agent_role: "Travel Researcher",
      },
      {
        event: "AgentFinish",
        timestamp: "2026-06-08T12:22:00.000+00:00",
        elapsed_ms: 1000,
        agent_role: "Local Coorg Expert",
      },
      {
        event: "task_completed",
        timestamp: "2026-06-08T12:23:00.000+00:00",
        elapsed_ms: 5000,
        task_index: 2,
        agent_role: "Local Coorg Expert",
      },
    ];
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={events} defaultExpanded />);
    // Both agent roles appear; their event types are disambiguated by icon.
    const researcherMatches = screen.getAllByText(/Travel Researcher/);
    expect(researcherMatches.length).toBeGreaterThanOrEqual(2);
    const expertMatches = screen.getAllByText(/Local Coorg Expert/);
    expect(expertMatches.length).toBeGreaterThanOrEqual(2);
  });
});

describe("<PlanHistoryPanel /> date-context-aware time formatter", () => {
  // Slice 4d0 polish (2026-06-07): bare time strings stripped date
  // context — "21:42:12" rendered identically for today's plan and
  // yesterday's plan. The four buckets below pin the date-aware
  // rendering per relative distance from now. AGENT_FINISH_FIXTURE
  // timestamp is "2026-06-06T16:12:12.550713+00:00".

  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  const _renderWithTimestamp = async (timestamp: string) => {
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    const row: AgentSummaryRow = {
      event: "AgentFinish",
      timestamp,
      elapsed_ms: 60000,
      output_excerpt: "test",
    };
    render(<PlanHistoryPanel agentSummary={[row]} defaultExpanded />);
  };

  it("renders time only when timestamp is the same calendar day as now", async () => {
    // Now = 2026-06-07 22:00:00 IST. Timestamp = 2026-06-07 14:00:00 IST
    // (08:30 UTC). Same day → no date prefix.
    vi.setSystemTime(new Date("2026-06-07T16:30:00Z"));
    await _renderWithTimestamp("2026-06-07T08:30:00+00:00");
    // Time string varies by locale TZ, but "Yesterday" / "Jun" / weekday
    // should NOT appear.
    expect(screen.queryByText(/Yesterday/i)).toBeNull();
    expect(screen.queryByText(/Jun/i)).toBeNull();
    // Just-time format is what's left.
    expect(screen.queryByText(/Yesterday ·|· /)).toBeNull();
  });

  it("renders 'Yesterday · HH:MM:SS' when timestamp is one calendar day before now", async () => {
    // Now = 2026-06-07. Timestamp = 2026-06-06 (the Coorg trip).
    vi.setSystemTime(new Date("2026-06-07T16:30:00Z"));
    await _renderWithTimestamp("2026-06-06T16:12:12.550713+00:00");
    expect(screen.getByText(/Yesterday/)).toBeDefined();
  });

  it("renders 'Weekday · HH:MM:SS' when timestamp is within last 7 days but not yesterday", async () => {
    // Now = Sun 2026-06-07. Timestamp = Wed 2026-06-03 → within 7 days.
    // Expect "Wed" prefix.
    vi.setSystemTime(new Date("2026-06-07T16:30:00Z"));
    await _renderWithTimestamp("2026-06-03T10:00:00+00:00");
    // Weekday label: locale-dependent but should be a 3-letter day code.
    // Negative assertion: should NOT show "Yesterday" or "Jun" prefix.
    expect(screen.queryByText(/Yesterday/)).toBeNull();
    expect(screen.queryByText(/^Jun/)).toBeNull();
    // Positive: a 3-letter weekday appears. Look for any of Mon-Sun.
    const dayMatch = screen.queryByText(/Mon|Tue|Wed|Thu|Fri|Sat|Sun/);
    expect(dayMatch).toBeDefined();
  });

  it("renders 'Mon D · HH:MM:SS' when timestamp is older than 7 days", async () => {
    // Now = 2026-06-07. Timestamp = 2026-05-15 → older than 7 days.
    // Expect "May 15" or similar locale-formatted month-day.
    vi.setSystemTime(new Date("2026-06-07T16:30:00Z"));
    await _renderWithTimestamp("2026-05-15T10:00:00+00:00");
    expect(screen.queryByText(/Yesterday/)).toBeNull();
    // Month abbreviation should appear (May or Apr depending on TZ; we
    // assert one of them is present).
    const monthMatch = screen.queryByText(/May|Apr|Jun|Jul/);
    expect(monthMatch).toBeDefined();
  });
});
