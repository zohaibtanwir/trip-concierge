/**
 * usePlanStatusPoll tests — slice 4.7-theater (trip-concierge-249) commit 3.
 *
 * Polling hook driving the theater UI. While state is non-terminal,
 * polls GET /trips/{id}/plan/status every 2500ms via the
 * fetchPlanStatusAction Server Action. Stops polling when state
 * transitions to terminal {done, failed, cancelled}. Cleans up on
 * unmount. Disabled mode (replay theater) short-circuits — no
 * network activity at all.
 *
 * Contract:
 *
 *   function usePlanStatusPoll(
 *     tripId: string,
 *     userId: string,
 *     options?: { disabled?: boolean },
 *   ): { events: AgentSummaryRow[]; state: PlanState | null }
 *
 * 2500ms interval per Q-impl-249-c sign-off. The hook resolves events
 * from PlanStatus.events_in_flight (live runs) OR PlanStatus.agent_summary
 * (terminal) with the live-takes-precedence semantic per the slice's
 * shared-data-shape principle.
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/actions", () => ({
  fetchPlanStatusAction: vi.fn(),
}));

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
  vi.resetAllMocks();
});

describe("usePlanStatusPoll", () => {
  it("polls /plan/status at 2500ms while state is non-terminal", async () => {
    // Q-impl-249-c: 2500ms cadence. The test pins the exact interval —
    // changes to either direction need explicit re-sign-off (faster
    // hammers infra; slower kills demo perception of liveness).
    const { fetchPlanStatusAction } = await import("@/lib/actions");
    (fetchPlanStatusAction as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: "running",
      events_in_flight: [],
      agent_summary: null,
    });

    const { usePlanStatusPoll } = await import("@/lib/use-plan-status-poll");
    renderHook(() => usePlanStatusPoll("trip-1", "user-1"));

    // Initial fire on mount.
    await waitFor(() => {
      expect(fetchPlanStatusAction).toHaveBeenCalledTimes(1);
    });

    // Advance 2500ms; second fire.
    await act(async () => {
      vi.advanceTimersByTime(2500);
    });
    await waitFor(() => {
      expect(fetchPlanStatusAction).toHaveBeenCalledTimes(2);
    });

    // Advance another 2500ms; third fire.
    await act(async () => {
      vi.advanceTimersByTime(2500);
    });
    await waitFor(() => {
      expect(fetchPlanStatusAction).toHaveBeenCalledTimes(3);
    });
  });

  it("stops polling when state transitions to terminal (done)", async () => {
    // Terminal-state poll-stop is the load-bearing efficiency guarantee.
    // Without this, the page would forever-poll a completed trip, burning
    // backend cycles for no benefit.
    const { fetchPlanStatusAction } = await import("@/lib/actions");
    (fetchPlanStatusAction as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ state: "running", events_in_flight: [], agent_summary: null })
      .mockResolvedValueOnce({ state: "done", events_in_flight: null, agent_summary: [] });

    const { usePlanStatusPoll } = await import("@/lib/use-plan-status-poll");
    renderHook(() => usePlanStatusPoll("trip-1", "user-1"));

    await waitFor(() => {
      expect(fetchPlanStatusAction).toHaveBeenCalledTimes(1);
    });

    // Second poll arrives with state=done; hook should stop the interval.
    await act(async () => {
      vi.advanceTimersByTime(2500);
    });
    await waitFor(() => {
      expect(fetchPlanStatusAction).toHaveBeenCalledTimes(2);
    });

    // Advance MORE time; should NOT fire a third time.
    await act(async () => {
      vi.advanceTimersByTime(10000);
    });
    expect(fetchPlanStatusAction).toHaveBeenCalledTimes(2);
  });

  it("cleans up the interval on unmount (no leaks)", async () => {
    // React unmount must clear setInterval; otherwise navigating away
    // from /trips/[id] would leave background polling burning forever.
    const { fetchPlanStatusAction } = await import("@/lib/actions");
    (fetchPlanStatusAction as ReturnType<typeof vi.fn>).mockResolvedValue({
      state: "running",
      events_in_flight: [],
      agent_summary: null,
    });

    const { usePlanStatusPoll } = await import("@/lib/use-plan-status-poll");
    const { unmount } = renderHook(() => usePlanStatusPoll("trip-1", "user-1"));

    await waitFor(() => {
      expect(fetchPlanStatusAction).toHaveBeenCalledTimes(1);
    });

    unmount();

    // After unmount, no further fires regardless of how much time passes.
    await act(async () => {
      vi.advanceTimersByTime(15000);
    });
    expect(fetchPlanStatusAction).toHaveBeenCalledTimes(1);
  });

  it("disabled option short-circuits — no polling, no initial fetch", async () => {
    // Replay-mode theater calls the hook with { disabled: true } so it
    // can render statically from the events prop without triggering
    // network activity. The hook must be a no-op in this mode (React
    // Hooks rules: hook always called, but its effect skipped).
    const { fetchPlanStatusAction } = await import("@/lib/actions");
    const { usePlanStatusPoll } = await import("@/lib/use-plan-status-poll");
    renderHook(() => usePlanStatusPoll("trip-1", "user-1", { disabled: true }));

    // Initial fire suppressed.
    await act(async () => {
      vi.advanceTimersByTime(0);
    });
    expect(fetchPlanStatusAction).not.toHaveBeenCalled();

    // Subsequent intervals also suppressed.
    await act(async () => {
      vi.advanceTimersByTime(10000);
    });
    expect(fetchPlanStatusAction).not.toHaveBeenCalled();
  });
});
