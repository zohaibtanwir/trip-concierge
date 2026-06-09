/**
 * usePlanStatusPoll — polling hook for the live planning theater UI.
 *
 * Slice 4.7-theater (trip-concierge-249) commit 3. Polls
 * /trips/{id}/plan/status via the fetchPlanStatusAction Server Action
 * at 2500ms (Q-impl-249-c) while state is non-terminal. Stops on
 * terminal {done, failed, cancelled}. Cleans up on unmount.
 *
 * `disabled: true` short-circuits the effect — no network activity at
 * all. Replay-mode PlanningTheater passes this so it can render
 * statically from the events prop without triggering polls.
 *
 * Visibility-aware polling (pause when tab hidden) deferred to v1.0b
 * per Q-impl-249-n=A — see trip-concierge-2me.
 *
 * Event source semantics (Q-249-i shared-data-shape):
 *   - During non-terminal: events_in_flight is the source (Redis-backed
 *     stream, LPUSH newest-first)
 *   - At terminal: events_in_flight is null; agent_summary is the source
 *     (Postgres-backed JobRun row, richest selected per hotfix-3x5)
 */

"use client";

import { useEffect, useState } from "react";

import { fetchPlanStatusAction } from "@/lib/actions";
import type { AgentSummaryRow, PlanStatus } from "@/lib/backend";

const _POLL_INTERVAL_MS = 2500;

const _TERMINAL_STATES: ReadonlyArray<PlanStatus["state"]> = ["done", "failed", "cancelled"];

interface UsePlanStatusPollOptions {
  disabled?: boolean;
}

interface UsePlanStatusPollResult {
  events: AgentSummaryRow[];
  state: PlanStatus["state"] | null;
}

function _selectEvents(status: PlanStatus): AgentSummaryRow[] {
  // Live runs: events_in_flight is the Redis stream.
  if (status.events_in_flight && status.events_in_flight.length > 0) {
    return status.events_in_flight;
  }
  // Terminal or no-events-yet: agent_summary (rich JobRun row).
  return status.agent_summary ?? [];
}

export function usePlanStatusPoll(
  tripId: string,
  userId: string,
  options?: UsePlanStatusPollOptions,
): UsePlanStatusPollResult {
  const disabled = options?.disabled ?? false;
  const [events, setEvents] = useState<AgentSummaryRow[]>([]);
  const [state, setState] = useState<PlanStatus["state"] | null>(null);

  useEffect(() => {
    if (disabled) return;
    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    async function poll() {
      try {
        const status = await fetchPlanStatusAction({ tripId, userId });
        if (cancelled) return;
        setState(status.state);
        setEvents(_selectEvents(status));
        // Terminal-state poll-stop: clear the interval so we don't burn
        // backend cycles for a completed trip.
        if (intervalId !== null && _TERMINAL_STATES.includes(status.state as PlanStatus["state"])) {
          clearInterval(intervalId);
          intervalId = null;
        }
      } catch {
        // Best-effort: keep polling on transient failure. A persistent
        // failure will surface eventually as the user notices the page
        // isn't updating; better than spuriously stopping.
      }
    }

    // Initial fire on mount; interval drives subsequent polls.
    poll();
    intervalId = setInterval(poll, _POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (intervalId !== null) {
        clearInterval(intervalId);
        intervalId = null;
      }
    };
  }, [tripId, userId, disabled]);

  return { events, state };
}
