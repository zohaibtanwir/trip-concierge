/**
 * <PlanningTheater /> tests — slice 4.7-theater commit 3.
 *
 * Container component that puts together the 4-up AgentCard grid +
 * EventDensityToggle + LiveEventLog primitives from commit 2.
 *
 * Two modes:
 *
 *   - live: uses usePlanStatusPoll(tripId, userId) for real-time
 *     polling at 2500ms; renders during {queued, running, cancelling}
 *     states on the trip detail page
 *   - replay: consumes `events` prop directly (no polling); used by the
 *     "View agent trace" modal in commit 4 for replayable historical
 *     view of agent_summary
 *
 * Q-249-i shared-data-shape principle: BOTH modes render the SAME
 * component, just with different data sources. live polls; replay
 * consumes prop.
 *
 * Contract:
 *
 *   interface PlanningTheaterProps {
 *     mode: "live" | "replay";
 *     tripId: string;
 *     userId: string;
 *     events?: AgentSummaryRow[];  // required in replay; ignored in live
 *   }
 *
 * 4 cards always render:
 *   - Travel Researcher
 *   - Local Expert
 *   - Logistics Planner
 *   - Budget Auditor (default state "waiting" per Q-249-d=A)
 *
 * Card-to-role lookup is prefix-based: any role string containing
 * "Researcher" matches the Researcher card, "Expert" matches the
 * Expert card, etc. Handles destination-aware variants like "Local
 * Coorg Expert" / "Local Pondicherry Expert".
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AgentSummaryRow } from "@/lib/backend";

// Mock the Server Action; commit 3 adds it to lib/actions.ts but the
// vi.mock factory provides the implementation regardless. Default
// mock returns running state; tests override per scenario.
vi.mock("@/lib/actions", () => ({
  fetchPlanStatusAction: vi.fn().mockResolvedValue({
    state: "running",
    events_in_flight: [],
    agent_summary: null,
  }),
}));

afterEach(() => cleanup());

describe("<PlanningTheater /> replay mode", () => {
  it("renders 4 agent cards (Researcher / Expert / Logistics / Auditor) by default", async () => {
    // Initial state before any events. All 4 cards visible so the user
    // sees the multi-agent specialization story from the first frame.
    const { PlanningTheater } = await import("@/components/planning-theater");
    render(<PlanningTheater mode="replay" tripId="trip-1" userId="user-1" events={[]} />);
    expect(screen.getByText(/Travel Researcher/)).toBeDefined();
    expect(screen.getByText(/Local Expert/)).toBeDefined();
    expect(screen.getByText(/Logistics Planner/)).toBeDefined();
    expect(screen.getByText(/Budget Auditor/)).toBeDefined();
  });

  it("Budget Auditor defaults to 'waiting' state (not idle) per Q-249-d=A", async () => {
    // Auditor's pre-audit-loop state is distinct from idle — it's
    // queued behind the main crew. The "Waiting on plan" copy
    // communicates this rather than implying inactivity.
    const { PlanningTheater } = await import("@/components/planning-theater");
    render(<PlanningTheater mode="replay" tripId="trip-1" userId="user-1" events={[]} />);
    expect(screen.getByText(/waiting on plan/i)).toBeDefined();
  });

  it("derives card states from events (task_completed → done)", async () => {
    // Connects derive_agent_states from commit 2 — task_completed for
    // an agent transitions that card to done state. The visual
    // narrative settles into "all done" by the end of plan_trip.
    const events: AgentSummaryRow[] = [
      {
        event: "task_completed",
        timestamp: "2026-06-09T10:05:00+00:00",
        elapsed_ms: 312000,
        task_index: 1,
        agent_role: "Travel Researcher",
      },
    ];
    const { PlanningTheater } = await import("@/components/planning-theater");
    render(<PlanningTheater mode="replay" tripId="trip-1" userId="user-1" events={events} />);
    // At least one "Done" pill appears (Researcher's card).
    const doneMatches = screen.getAllByText(/^done$/i);
    expect(doneMatches.length).toBeGreaterThanOrEqual(1);
  });

  it("maps destination-aware role variants to the canonical card (Local Coorg Expert → Expert card)", async () => {
    // Real data has role strings like "Local Coorg Expert" or
    // "Local Pondicherry Expert"; both should drive the SAME card.
    // Prefix-match on "Expert" handles this without per-destination
    // configuration in the theater component.
    const events: AgentSummaryRow[] = [
      {
        event: "task_completed",
        timestamp: "2026-06-09T10:05:00+00:00",
        elapsed_ms: 240000,
        task_index: 1,
        agent_role: "Local Coorg Expert",
      },
    ];
    const { PlanningTheater } = await import("@/components/planning-theater");
    render(<PlanningTheater mode="replay" tripId="trip-1" userId="user-1" events={events} />);
    // Expert card visible AND in done state (because the role matched).
    expect(screen.getByText(/Local Expert/)).toBeDefined();
    const doneMatches = screen.getAllByText(/^done$/i);
    expect(doneMatches.length).toBeGreaterThanOrEqual(1);
  });

  it("renders EventDensityToggle + LiveEventLog below the cards", async () => {
    // Cards always show full agent state. Below, the user sees the
    // density toggle + recent event log. Per R6: density filters only
    // the log, not the cards.
    const events: AgentSummaryRow[] = [
      {
        event: "task_completed",
        timestamp: "2026-06-09T10:05:00+00:00",
        elapsed_ms: 312000,
        task_index: 1,
        agent_role: "Travel Researcher",
      },
    ];
    const { PlanningTheater } = await import("@/components/planning-theater");
    render(<PlanningTheater mode="replay" tripId="trip-1" userId="user-1" events={events} />);
    // Density toggle buttons.
    expect(screen.getByRole("button", { name: /^major$/i })).toBeDefined();
    expect(screen.getByRole("button", { name: /^all$/i })).toBeDefined();
  });

  it("replay mode does NOT call fetchPlanStatusAction (hook disabled)", async () => {
    // Critical for the "View agent trace" replay modal in commit 4 —
    // opening it must not trigger polling for a trip that's already
    // terminal. The hook is called with { disabled: true } and is a no-op.
    const { fetchPlanStatusAction } = await import("@/lib/actions");
    const { PlanningTheater } = await import("@/components/planning-theater");
    render(<PlanningTheater mode="replay" tripId="trip-1" userId="user-1" events={[]} />);
    // Let microtasks settle to give any latent fetch a chance to fire.
    await new Promise((r) => setTimeout(r, 50));
    expect(fetchPlanStatusAction).not.toHaveBeenCalled();
  });
});
