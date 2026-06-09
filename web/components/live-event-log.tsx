/**
 * LiveEventLog — compact 3-event timeline below the theater agent grid.
 *
 * Slice 4.7-theater (trip-concierge-249) commit 2; rewritten in the
 * post-commit-4 replay-modal hotfix (2026-06-09). Per Q-impl-249-k=A
 * the row layout is inline / one-liner — but the information density
 * mirrors PlanHistoryPanel (icon + agent role + timestamp + duration)
 * so the user gets agent identity, not a bare event-name label.
 *
 * Density-toggle filtering is applied by the parent (PlanningTheater)
 * before passing events to this log. Truncates to 3 most-recent.
 *
 * Title resolution chain (resolveEventTitle in agent-summary-format):
 *   1. agent_role (Path B enrichment)
 *   2. task_index → canonical role (pre-Path-B legacy task_completed)
 *   3. "Reasoning step" generic title (AgentFinish without role)
 *   4. "Callback summary" (callback_summary footer)
 *
 * Icons mirror PlanHistoryPanel:
 *   - check_circle for task_completed (completion)
 *   - psychology for AgentFinish (reasoning)
 *   - summarize for callback_summary (tally)
 *
 * Parent passes events in either newest-first (Redis LPUSH from
 * /plan/status events_in_flight) or chronological (agent_summary at
 * terminal). This component does NOT re-sort — it takes the first 3
 * as-given.
 */

import { formatDuration, formatTime, resolveEventTitle } from "@/lib/agent-summary-format";
import type { AgentSummaryRow } from "@/lib/backend";

interface LiveEventLogProps {
  events: AgentSummaryRow[];
}

const _MAX_VISIBLE = 3;

function _eventIcon(event: AgentSummaryRow): string {
  if (event.event === "task_completed") return "check_circle";
  if (event.event === "callback_summary") return "summarize";
  return "psychology";
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
      {visible.map((event) => {
        if (event.event === "callback_summary") {
          // Mirror PlanHistoryPanel's §9.15 summary-row treatment in a
          // compact one-liner form: bold weight + tinted background +
          // user-facing count copy.
          return (
            <li
              key={_eventKey(event)}
              className="flex items-baseline gap-2 rounded-md bg-surface-container-low px-3 py-1.5 font-semibold"
            >
              <span className="material-symbols-outlined text-primary text-base" aria-hidden>
                summarize
              </span>
              <span className="text-label-md text-on-surface">Callback summary</span>
              <span className="text-label-sm text-on-surface-variant ml-auto">
                {event.step_callback_count} reasoning steps · {event.task_callback_count} agent
                completions
              </span>
            </li>
          );
        }

        const title = resolveEventTitle(event);
        return (
          <li
            key={_eventKey(event)}
            className="flex items-baseline justify-between gap-3 rounded-md bg-surface-container-low px-3 py-1.5"
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className="material-symbols-outlined text-primary text-base" aria-hidden>
                {_eventIcon(event)}
              </span>
              <span className="text-label-md text-on-surface truncate">{title}</span>
              <span className="text-label-sm text-on-surface-variant">
                {formatTime(event.timestamp)}
              </span>
            </div>
            <span className="text-label-sm text-on-surface-variant shrink-0">
              {formatDuration(event.elapsed_ms)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
