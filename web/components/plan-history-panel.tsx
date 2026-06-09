/**
 * PlanHistoryPanel — "How this plan was made" surface.
 *
 * Path B (hotfix-kyh reframe 2026-06-08): task_completed events are
 * now PRIMARY visibility — they're the only signal when CrewAI's
 * step_callback doesn't fire (the common case under 1.14.5 with
 * single-shot LLM outputs). The prior filter that swallowed
 * task_completed assumed step events were always present; kyh
 * showed that assumption is false for most trips.
 *
 * Discriminated union (slice 4d0 refactor preserved):
 * - AgentFinish — per-agent reasoning step. Renders with `psychology`
 *   icon, agent_role title (when present, fallback to event name),
 *   timestamp + elapsed_ms + output excerpt
 * - task_completed — per-agent task completion. Renders with
 *   `check_circle` icon, agent_role title (when present), timestamp +
 *   elapsed_ms + output excerpt. Visually distinct from AgentFinish
 *   to preserve the reasoning-vs-completion semantic
 * - callback_summary — qek-a observability tally, rendered with
 *   summary-row visual treatment (spec §9.15): bold weight + tinted
 *   background + summarize icon + user-facing copy ("N reasoning
 *   steps · M agent completions")
 *
 * agent_role discharges trip-concierge-nhm — both AgentFinish and
 * task_completed variants render the role string when present,
 * falling back to event-name framing for legacy data.
 *
 * sr-only event-type per Q-pathb-impl-a=B — the icon disambiguates
 * step vs task visually (aria-hidden), but screen readers need the
 * semantic context in text form.
 *
 * Spec reference: design-spec.md §9.15 (summary-row pattern).
 */

"use client";

import {
  formatDuration,
  formatTime,
  REASONING_STEP_TITLE,
  resolveAgentRole,
} from "@/lib/agent-summary-format";
import type {
  AgentSummaryAgentFinishRow,
  AgentSummaryCallbackSummaryRow,
  AgentSummaryRow,
  AgentSummaryTaskCompletedRow,
} from "@/lib/backend";

function _AgentFinishRow({ row }: { row: AgentSummaryAgentFinishRow }) {
  // Title prefers agent_role (Path B); falls back to generic
  // "Reasoning step" for pre-Path-B legacy data instead of leaking the
  // raw event name to the user. Proximity-based attribution was
  // considered + rejected (see agent-summary-format docstring).
  //
  // Hotfix-on7 (2026-06-08 evening): output_excerpt rendering removed.
  // The CrewAI scratchpad content (raw JSON dumps, agent reasoning
  // commentary) was demo-inappropriate. v1.0b structured summaries
  // (trip-concierge-q1v) will replace; until then the panel surfaces
  // role + timing only.
  const title = row.agent_role || REASONING_STEP_TITLE;
  return (
    <li key={`${row.event}-${row.timestamp}`} className="flex items-baseline justify-between gap-4">
      <div className="flex items-center gap-2">
        <span className="material-symbols-outlined text-primary text-base" aria-hidden>
          psychology
        </span>
        <span className="text-label-md text-on-surface">{title}</span>
        {/* sr-only event-type per Q-pathb-impl-a=B: icon is
            aria-hidden, screen readers need the semantic context. */}
        <span className="sr-only">reasoning step</span>
        <span className="text-label-sm text-on-surface-variant">{formatTime(row.timestamp)}</span>
      </div>
      <span className="text-label-sm text-on-surface-variant">
        {formatDuration(row.elapsed_ms)}
      </span>
    </li>
  );
}

function _TaskCompletedRow({ row }: { row: AgentSummaryTaskCompletedRow }) {
  // Path B primary visibility surface — surfaces when step_callback
  // doesn't fire (the common case under CrewAI 1.14.5). Visually
  // distinct from AgentFinish (check_circle vs psychology) to preserve
  // the completion-vs-reasoning semantic per Q-pathb-b=B.
  //
  // Title resolution: agent_role (Path B) → task_index → canonical
  // role (pre-Path-B legacy: Coorg, Manali). Discharges the replay-
  // modal hotfix for legacy trips where task_completed rows previously
  // rendered as literal "task_completed" titles.
  //
  // Hotfix-on7 (2026-06-08 evening): output_excerpt rendering removed
  // for the same reason as _AgentFinishRow above.
  const title = resolveAgentRole(row) ?? REASONING_STEP_TITLE;
  return (
    <li key={`${row.event}-${row.timestamp}`} className="flex items-baseline justify-between gap-4">
      <div className="flex items-center gap-2">
        <span className="material-symbols-outlined text-primary text-base" aria-hidden>
          check_circle
        </span>
        <span className="text-label-md text-on-surface">{title}</span>
        <span className="sr-only">agent completion</span>
        <span className="text-label-sm text-on-surface-variant">{formatTime(row.timestamp)}</span>
      </div>
      <span className="text-label-sm text-on-surface-variant">
        {formatDuration(row.elapsed_ms)}
      </span>
    </li>
  );
}

function _CallbackSummaryRow({ row }: { row: AgentSummaryCallbackSummaryRow }) {
  // Summary-row visual treatment (spec §9.15): bold weight + subtle
  // surface-container-low background + summarize icon + count tally.
  // Path B (Q-pathb-d=B): user-facing copy ("reasoning steps · agent
  // completions") instead of internal "step events · task events".
  // Preserves the load-bearing 0-callbacks signal while reading
  // naturally to demo audiences.
  return (
    <li
      key={`${row.event}`}
      className="flex items-baseline gap-2 mt-2 px-2 py-1.5 rounded-md bg-surface-container-low font-semibold"
    >
      <span className="material-symbols-outlined text-primary text-base" aria-hidden>
        summarize
      </span>
      <span className="text-label-md text-on-surface">Callback summary</span>
      <span className="text-label-sm text-on-surface-variant ml-auto">
        {row.step_callback_count} reasoning steps · {row.task_callback_count} agent completions
      </span>
    </li>
  );
}

export function PlanHistoryPanel({
  agentSummary,
  defaultExpanded = false,
}: {
  agentSummary: AgentSummaryRow[];
  defaultExpanded?: boolean;
}) {
  // Path B: no filter. All three event variants render. task_completed
  // is the primary visibility surface when step_callback is silent
  // (the common case under CrewAI 1.14.5 single-shot outputs); step
  // events surface alongside when both fire (the "everything works"
  // demo state).
  return (
    <details
      open={defaultExpanded}
      className="rounded-xl border border-outline-variant bg-surface-container-lowest p-4"
    >
      <summary className="cursor-pointer text-label-md text-on-surface hover:text-primary">
        How this plan was made
      </summary>
      <div className="mt-4">
        {agentSummary.length === 0 ? (
          <p className="text-body-md italic text-on-surface-variant">
            No agent activity recorded for this run.
          </p>
        ) : (
          <ul className="space-y-3">
            {agentSummary.map((row) => {
              // TypeScript narrowing on row.event picks the right
              // variant component. Compile-time exhaustiveness check
              // protects against future event-type additions. Keys
              // use event + timestamp (microsecond-unique in real
              // data); task_completed adds task_index for belt-and-
              // braces uniqueness against same-microsecond edge cases.
              if (row.event === "AgentFinish") {
                return <_AgentFinishRow key={`AgentFinish-${row.timestamp}`} row={row} />;
              }
              if (row.event === "task_completed") {
                return (
                  <_TaskCompletedRow
                    key={`task_completed-${row.task_index}-${row.timestamp}`}
                    row={row}
                  />
                );
              }
              return <_CallbackSummaryRow key="callback_summary" row={row} />;
            })}
          </ul>
        )}
      </div>
    </details>
  );
}
