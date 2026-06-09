/**
 * agent-summary-format — shared formatting + agent-attribution for the
 * agent_summary surfaces (PlanHistoryPanel, LiveEventLog, theater-state).
 *
 * Hotfix (slice 4.7-theater post-commit-4): all three surfaces were
 * formatting event rows independently. PlanHistoryPanel had rich
 * agent_role + timestamp + duration; LiveEventLog had bare event-name
 * labels; theater-state.deriveAgentStates skipped legacy rows missing
 * agent_role. Replay modal on pre-Path-B trips (Coorg, Manali) read
 * cards stuck at default + "task_completed" / "AgentFinish" event
 * names in the log — neither demo-grade.
 *
 * Single source of truth here:
 *   - resolveAgentRole(event): agent_role when present, task_index →
 *     canonical role fallback for task_completed, undefined otherwise.
 *     Task ordering locked at agents/src/trip_agents/crew.py:179
 *     (Researcher → Local Expert → Logistics Planner — the Budget
 *     Auditor runs in a separate Python audit loop with no task_index)
 *   - formatDuration / formatTime: identical rendering across surfaces
 *
 * Proximity-based attribution for AgentFinish-without-role was
 * considered + explicitly rejected: the live-mode events_in_flight
 * stream is LPUSH'd newest-first, while replay-mode agent_summary is
 * chronological. The proximity rule depends on chronological ordering;
 * applying it correctly in both modes would require a sort-before-
 * attribute pass that adds surface area for bugs. Major-filter (the
 * demo default) only shows task_completed rows where task_index gives
 * full attribution; All-filter is the engineering-depth case where
 * bounded ambiguity ("Reasoning step" generic title) is acceptable.
 */

import type {
  AgentSummaryAgentFinishRow,
  AgentSummaryRow,
  AgentSummaryTaskCompletedRow,
} from "@/lib/backend";

// Locked at agents/src/trip_agents/crew.py:179.
// Indices are 0-based here; CrewAI task_index is 1-based (see the
// worker.py counter init).
const _TASK_INDEX_TO_ROLE = ["Travel Researcher", "Local Expert", "Logistics Planner"] as const;

/**
 * Resolve an event's agent role for display + state derivation.
 *
 * Priority:
 *   1. agent_role (Path B enrichment, when present)
 *   2. task_completed → task_index → canonical role (pre-Path-B legacy)
 *   3. undefined (AgentFinish without role; callback_summary)
 *
 * Callers handle the undefined case differently:
 *   - deriveAgentStates skips (can't attribute the card)
 *   - LiveEventLog / PlanHistoryPanel render "Reasoning step" as title
 */
export function resolveAgentRole(
  event: AgentSummaryAgentFinishRow | AgentSummaryTaskCompletedRow,
): string | undefined {
  if (event.agent_role) return event.agent_role;
  if (event.event === "task_completed") {
    const idx = event.task_index - 1;
    if (idx >= 0 && idx < _TASK_INDEX_TO_ROLE.length) {
      return _TASK_INDEX_TO_ROLE[idx];
    }
  }
  return undefined;
}

/**
 * Title to render for an event row when agent_role can't be resolved.
 * Generic but readable — beats leaking the internal event name.
 */
export const REASONING_STEP_TITLE = "Reasoning step";

/**
 * Resolve an event's row title.
 *   - task_completed / AgentFinish: resolveAgentRole or REASONING_STEP_TITLE
 *   - callback_summary: "Callback summary"
 */
export function resolveEventTitle(event: AgentSummaryRow): string {
  if (event.event === "callback_summary") return "Callback summary";
  const role = resolveAgentRole(event);
  if (role) return role;
  return REASONING_STEP_TITLE;
}

export function formatDuration(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms}ms`;
}

/**
 * Date-context-aware time formatter (slice 4d0 polish, 2026-06-07).
 *   same day      → "HH:MM:SS"
 *   yesterday     → "Yesterday · HH:MM:SS"
 *   within 7 days → "Sat · HH:MM:SS"  (3-letter weekday)
 *   older         → "Jun 6 · HH:MM:SS"
 * Stripping the date silently confuses readers viewing multi-day-old
 * trips; per the slice 4d0 Sunday smoke fourth-UI-data-context-bug
 * observation, any timestamp in a list of historical events needs
 * relative-date framing.
 */
export function formatTime(iso: string, now: Date = new Date()): string {
  let d: Date;
  try {
    d = new Date(iso);
    if (Number.isNaN(d.getTime())) throw new Error("NaN");
  } catch {
    return iso.slice(11, 19);
  }
  const time = d.toLocaleTimeString(undefined, { hour12: false });

  const sameDay = (a: Date, b: Date): boolean =>
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate();
  if (sameDay(d, now)) return time;

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (sameDay(d, yesterday)) return `Yesterday · ${time}`;

  const sevenDaysAgo = new Date(now);
  sevenDaysAgo.setDate(now.getDate() - 7);
  if (d >= sevenDaysAgo && d < now) {
    const weekday = new Intl.DateTimeFormat(undefined, { weekday: "short" }).format(d);
    return `${weekday} · ${time}`;
  }

  const dateLabel = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(
    d,
  );
  return `${dateLabel} · ${time}`;
}
