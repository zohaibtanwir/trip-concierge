/**
 * <ViewAgentTraceLink /> tests — slice 4.7-theater commit 4.
 *
 * Replay-mode entry point per Q-impl-249-f=B: link in the terminal-state
 * trip detail header opens a modal containing the full PlanningTheater
 * in replay mode (Q-impl-249-s=A). Same component, two data sources —
 * the modal renders from the agentSummary prop without polling.
 *
 * Modal uses the §9.18 imperative-useEffect dialog pattern (hotfix-nwk
 * hardened): native <dialog>, showModal/close via useEffect, backdrop
 * click + Escape close, sr-only event-type for a11y.
 *
 * Q-impl-249-q=A: link placement is below the destination h1 in the
 * page header — discovery in the natural read order, doesn't bloat
 * PlanHistoryPanel.
 *
 * Q-impl-249-t=C: density toggle inside the modal reads from the same
 * sessionStorage key ("theater-density") as live-mode — consistency
 * across modes; last choice survives.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AgentSummaryRow } from "@/lib/backend";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

// PlanningTheater (inside the modal) imports fetchPlanStatusAction —
// mock it even though replay mode shouldn't call it.
vi.mock("@/lib/actions", () => ({
  fetchPlanStatusAction: vi.fn(),
}));

afterEach(() => cleanup());

const _AGENT_SUMMARY_FIXTURE: AgentSummaryRow[] = [
  {
    event: "task_completed",
    timestamp: "2026-06-09T10:05:00+00:00",
    elapsed_ms: 312000,
    task_index: 1,
    agent_role: "Travel Researcher",
  },
  {
    event: "task_completed",
    timestamp: "2026-06-09T10:09:00+00:00",
    elapsed_ms: 545000,
    task_index: 2,
    agent_role: "Local Udaipur Expert",
  },
  {
    event: "callback_summary",
    step_callback_count: 0,
    task_callback_count: 3,
  },
];

describe("<ViewAgentTraceLink />", () => {
  it("renders trigger labeled 'View agent trace' (or similar)", async () => {
    // Discovery surface — small link/button in the terminal-state page
    // header. Copy: loose regex covers "View agent trace" / "Trace" /
    // "View crew activity" — load-bearing semantic is "open the
    // historical theater view" not the exact wording.
    const { ViewAgentTraceLink } = await import("@/components/view-agent-trace-link");
    render(
      <ViewAgentTraceLink tripId="trip-1" userId="user-1" agentSummary={_AGENT_SUMMARY_FIXTURE} />,
    );
    expect(screen.getByRole("button", { name: /trace|crew activity|agent trace/i })).toBeDefined();
  });

  it("dialog content NOT in DOM by default — load-bearing absence", async () => {
    // The §9.18 imperative-useEffect modal pattern: dialog node lives
    // in DOM but children are gated by state. Before click, the
    // theater's role title shouldn't be present.
    const { ViewAgentTraceLink } = await import("@/components/view-agent-trace-link");
    render(
      <ViewAgentTraceLink tripId="trip-1" userId="user-1" agentSummary={_AGENT_SUMMARY_FIXTURE} />,
    );
    // Heading inside the modal (theater container) — absent before open.
    expect(screen.queryByText(/your crew is at work|crew is at work/i)).toBeNull();
  });

  it("click trigger opens modal containing the PlanningTheater in replay mode", async () => {
    // Q-impl-249-s=A: modal contents = full PlanningTheater in replay.
    // The 4 cards render from agentSummary; we verify by querying for
    // the canonical card labels.
    const { ViewAgentTraceLink } = await import("@/components/view-agent-trace-link");
    render(
      <ViewAgentTraceLink tripId="trip-1" userId="user-1" agentSummary={_AGENT_SUMMARY_FIXTURE} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /trace|crew activity|agent trace/i }));

    // All 4 cards visible (full theater render). Researcher appears
    // in both the card heading AND the recent-activity log (since the
    // fixture includes a task_completed for that role), so use
    // getAllByText. The other three only appear in the card heading.
    expect(screen.getAllByText(/Travel Researcher/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Logistics Planner/)).toBeDefined();
    expect(screen.getByText(/Budget Auditor/)).toBeDefined();
    // "Local Expert" is the card display name; "Local Udaipur Expert"
    // (the role in the fixture) maps to it via prefix-match. The card
    // heading is the exact "Local Expert" string.
    expect(screen.getByText(/^Local Expert$/)).toBeDefined();
    // Researcher derived from task_completed → done state pill.
    const doneMatches = screen.getAllByText(/^done$/i);
    expect(doneMatches.length).toBeGreaterThanOrEqual(1);
  });

  it("replay-mode modal does NOT call fetchPlanStatusAction (no polling)", async () => {
    // Critical proof that mode='replay' propagates correctly through
    // the modal → theater chain. The hook is called with disabled:true
    // and short-circuits its effect.
    const { fetchPlanStatusAction } = await import("@/lib/actions");
    const { ViewAgentTraceLink } = await import("@/components/view-agent-trace-link");
    render(
      <ViewAgentTraceLink tripId="trip-1" userId="user-1" agentSummary={_AGENT_SUMMARY_FIXTURE} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /trace|crew activity|agent trace/i }));
    await new Promise((r) => setTimeout(r, 50));
    expect(fetchPlanStatusAction).not.toHaveBeenCalled();
  });

  it("Close button (X) dismisses the modal", async () => {
    // §9.18 pattern: X click → setOpen(false) → useEffect.close() →
    // modal closes. Same pattern as RegenerateDayDialog +
    // BlockAlternativeDialog post-hotfix-nwk.
    const { ViewAgentTraceLink } = await import("@/components/view-agent-trace-link");
    render(
      <ViewAgentTraceLink tripId="trip-1" userId="user-1" agentSummary={_AGENT_SUMMARY_FIXTURE} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /trace|crew activity|agent trace/i }));
    expect(screen.getAllByText(/Travel Researcher/).length).toBeGreaterThanOrEqual(1);

    fireEvent.click(screen.getByRole("button", { name: /Close/i }));
    expect(screen.queryByText(/Travel Researcher/)).toBeNull();
  });

  it("calls showModal() and the call RETURNS cleanly (modal mode required per §9.18)", async () => {
    // §9.18 regression pin from hotfix-nwk. The polyfill in vitest.setup.ts
    // throws InvalidStateError when showModal is called on a dialog with
    // the `open` attribute already set — mirroring real-browser behavior.
    // Asserting mock.results[0].type === "return" catches the bug.
    const showModalSpy = vi.spyOn(HTMLDialogElement.prototype, "showModal");

    const { ViewAgentTraceLink } = await import("@/components/view-agent-trace-link");
    render(
      <ViewAgentTraceLink tripId="trip-1" userId="user-1" agentSummary={_AGENT_SUMMARY_FIXTURE} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /trace|crew activity|agent trace/i }));

    await vi.waitFor(() => {
      expect(showModalSpy).toHaveBeenCalled();
    });
    expect(showModalSpy.mock.results[0].type).toBe("return");
    showModalSpy.mockRestore();
  });
});
