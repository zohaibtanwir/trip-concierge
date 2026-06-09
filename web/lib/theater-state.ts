/**
 * theater-state — pure functions consumed by the planning theater UI.
 *
 * Slice 4.7-theater (trip-concierge-249) commit 2. The theater grid
 * shows 4 AgentCards; this module maps the AgentSummaryRow event
 * stream (from /plan/status `events_in_flight` during live runs OR
 * `agent_summary` during replay) into per-agent-role card state.
 *
 * Density filter applies the "major vs all" toggle per Q-impl-249-e=A:
 *   - "major" → task_completed + callback_summary only (clean demo)
 *   - "all" → identity pass-through (engineering depth)
 *
 * Per R6 confirmation: cards always show full state regardless of
 * density toggle. Density filters only the LiveEventLog below.
 */

import type { AgentSummaryRow } from "@/lib/backend";

export type AgentCardState = "idle" | "queued" | "working" | "done" | "waiting";

export interface AgentCardData {
  state: AgentCardState;
  lastAction?: string;
  durationMs?: number;
}

/**
 * Map an event stream to per-agent-role state.
 *
 * Keyed by the raw CrewAI role string ("Travel Researcher", "Local Coorg
 * Expert", etc.). Destination-aware variants (e.g., "Local Pondicherry
 * Expert") pass through unchanged — the parent component does the
 * card-to-role lookup (cards match by prefix or canonical name; not
 * this module's concern).
 *
 * State machine is monotonic toward `done`: once a task_completed
 * event fires for an agent, subsequent events don't downgrade it.
 * AgentFinish (and other step events) without a prior task_completed
 * mean the agent is currently working.
 *
 * Events without `agent_role` are silently ignored — legacy data,
 * callback_summary footer, and malformed entries don't contribute
 * to card state derivation.
 */
export function deriveAgentStates(events: AgentSummaryRow[]): Record<string, AgentCardData> {
  const result: Record<string, AgentCardData> = {};
  for (const event of events) {
    if (event.event === "callback_summary") continue;
    const role = event.agent_role;
    if (!role) continue;

    if (event.event === "task_completed") {
      // task_completed = monotonic terminal-per-agent state. Always
      // overwrites earlier "working" state for the same agent.
      result[role] = {
        state: "done",
        durationMs: event.elapsed_ms,
      };
      continue;
    }

    // Step events (AgentFinish, AgentAction, _FakeStep in tests, etc.):
    // mark as working UNLESS the agent has already completed.
    if (result[role]?.state === "done") continue;
    result[role] = {
      state: "working",
      durationMs: event.elapsed_ms,
    };
  }
  return result;
}

/**
 * Filter an event stream by the user's density preference.
 *
 * "major" keeps the canonical agent-completion markers (task_completed)
 * plus the closing tally (callback_summary). This is the clean demo
 * narrative — 3 + 1 = 4 events on a typical plan_trip.
 *
 * "all" returns the full event stream unmodified (identity). Used by
 * the "show me everything" engineering toggle.
 */
export function filterEventsByDensity(
  events: AgentSummaryRow[],
  mode: "major" | "all",
): AgentSummaryRow[] {
  if (mode === "all") return events;
  return events.filter(
    (event) => event.event === "task_completed" || event.event === "callback_summary",
  );
}
