/**
 * AgentCard — single agent visualization in the 4-up theater grid.
 *
 * Slice 4.7-theater (trip-concierge-249) commit 2. Per Q-249-c sign-off:
 * card-based layout makes multi-agent specialization VISIBLE — agent
 * name + state + last action + duration in a compact tile.
 *
 * State machine (Q-249-d):
 *   - idle: pre-run; agent hasn't fired yet
 *   - queued: worker has the job; crew hasn't started crew kickoff
 *   - working: step event fired; agent is actively running
 *   - done: task_completed fired; agent terminal-state
 *   - waiting: Budget Auditor's pre-audit-loop state. Distinct copy
 *     "Waiting on plan" so the user knows the card isn't dormant —
 *     it's queued behind the main crew per Q-249-d=A
 *
 * Icon legend (Q-impl-249-j):
 *   - idle:    radio_button_unchecked
 *   - queued:  pending
 *   - working: psychology (matches PlanHistoryPanel AgentFinish)
 *   - done:    check_circle (matches PlanHistoryPanel task_completed)
 *   - waiting: hourglass_top
 *
 * Duration formatting (Q-impl-249-i=A): "45s" for <60s; "5.2m" for
 * ≥60s. Compact, human-readable, demo-friendly.
 */

import type { AgentCardState } from "@/lib/theater-state";

interface AgentCardProps {
  // Note: named `agentRole` rather than `role` because biome's
  // useValidAriaRole rule false-positives on the custom-component
  // `role` prop, interpreting it as an HTML ARIA role attribute.
  // `agentRole` is also more explicit at call sites.
  agentRole: string;
  state: AgentCardState;
  lastAction?: string;
  durationMs?: number;
}

const _ICON_BY_STATE: Record<AgentCardState, string> = {
  idle: "radio_button_unchecked",
  queued: "pending",
  working: "psychology",
  done: "check_circle",
  waiting: "hourglass_top",
};

const _LABEL_BY_STATE: Record<AgentCardState, string> = {
  idle: "Idle",
  queued: "Queued",
  working: "Working",
  done: "Done",
  waiting: "Waiting on plan",
};

function _formatDuration(ms: number): string {
  if (ms < 60000) return `${Math.round(ms / 1000)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

export function AgentCard({ agentRole, state, lastAction, durationMs }: AgentCardProps) {
  const icon = _ICON_BY_STATE[state];
  const label = _LABEL_BY_STATE[state];
  const showDuration = (state === "working" || state === "done") && durationMs !== undefined;
  const showLastAction = state === "working" && lastAction !== undefined;

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-outline-variant bg-surface-container-lowest p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-base" aria-hidden>
            {icon}
          </span>
          <h3 className="text-label-md text-on-surface">{agentRole}</h3>
        </div>
        <span className="rounded-full bg-surface-container-low px-2 py-0.5 text-label-sm text-on-surface-variant">
          {label}
        </span>
      </div>
      {showLastAction && <p className="text-body-sm text-on-surface-variant pl-6">{lastAction}</p>}
      {showDuration && (
        <p className="text-label-sm text-on-surface-variant pl-6">{_formatDuration(durationMs)}</p>
      )}
    </div>
  );
}
