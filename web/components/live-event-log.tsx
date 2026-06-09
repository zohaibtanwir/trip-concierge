/**
 * LiveEventLog — compact 3-event timeline below the theater agent grid.
 *
 * Slice 4.7-theater (trip-concierge-249) commit 2. Per Q-impl-249-k=A:
 * inline compact row layout (one-liners), independent from
 * PlanHistoryPanel's denser per-row stack. Theater density-toggle
 * (EventDensityToggle) filters the event stream before truncation —
 * applied by the parent component before passing to this log.
 *
 * Truncates to 3 most-recent events. Parent passes events in either
 * newest-first (Redis LPUSH from /plan/status events_in_flight) or
 * chronological (agent_summary at terminal). This component does NOT
 * re-sort — it takes the first 3 as-given.
 *
 * Empty-state copy when no events present: tells the user the crew
 * is still spinning up rather than rendering a bare empty list.
 */

import type { AgentSummaryRow } from "@/lib/backend";

interface LiveEventLogProps {
  events: AgentSummaryRow[];
}

const _MAX_VISIBLE = 3;

function _eventTitle(event: AgentSummaryRow): string {
  if (event.event === "callback_summary") return "Callback summary";
  return event.agent_role || event.event;
}

function _eventTag(event: AgentSummaryRow): string {
  if (event.event === "task_completed") return "completed";
  if (event.event === "callback_summary") return "tally";
  return "reasoning";
}

export function LiveEventLog({ events }: LiveEventLogProps) {
  if (events.length === 0) {
    return (
      <p className="text-body-sm italic text-on-surface-variant">
        Waiting for first event — the crew is still spinning up.
      </p>
    );
  }
  const visible = events.slice(0, _MAX_VISIBLE);
  return (
    <ul className="space-y-1.5">
      {visible.map((event) => (
        <li
          key={_eventKey(event)}
          className="flex items-baseline gap-3 rounded-md bg-surface-container-low px-3 py-1.5"
        >
          <span className="text-label-md text-on-surface">{_eventTitle(event)}</span>
          <span className="text-label-sm text-on-surface-variant">{_eventTag(event)}</span>
        </li>
      ))}
    </ul>
  );
}

function _eventKey(event: AgentSummaryRow): string {
  // event + timestamp is microsecond-unique in real data; task_index
  // is the belt-and-braces tiebreaker against same-microsecond pairs
  // on task events. callback_summary appears at most once per
  // event_summary so its bare event name suffices.
  if (event.event === "callback_summary") return "callback_summary";
  if (event.event === "task_completed")
    return `task_completed-${event.task_index}-${event.timestamp}`;
  return `${event.event}-${event.timestamp}`;
}
