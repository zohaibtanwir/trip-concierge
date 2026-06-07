/**
 * PlanHistoryPanel — "How this plan was made" surface.
 *
 * Slice 4.3 (PRD §F8 partial) — refactored during slice 4d0 Sunday
 * smoke (2026-06-07) when callback_summary's structural heterogeneity
 * from AgentFinish was caught. AgentSummaryRow is now a discriminated
 * union; the component branches per `event` value to render each
 * variant with its actual field set.
 *
 * Filter logic (Option C from triage dialogue):
 * - AgentFinish — per-agent completion, renders with timestamp + elapsed
 * - callback_summary — final qek-a observability tally, renders with
 *   summary-row visual treatment (bold + tinted background + summarize
 *   icon + count semantic, no timing columns)
 * - task_completed — redundant CrewAI hook fired alongside each
 *   AgentFinish, no additional signal — filtered out
 *
 * Spec reference: design-spec.md §9.15 documents the summary-row pattern
 * for activity panel footers.
 *
 * Tap-to-expand-step-reasoning per PRD §F8 acceptance still deferred to
 * a future slice (trip-concierge-gco backend enrichment + auu §17.5).
 * Empty agent_summary renders "No agent activity recorded" (legacy
 * pre-qek-a JobRuns and any failure-path rows that didn't capture
 * agent_summary).
 */

"use client";

import type {
  AgentSummaryAgentFinishRow,
  AgentSummaryCallbackSummaryRow,
  AgentSummaryRow,
} from "@/lib/backend";

function _formatDuration(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms}ms`;
}

function _formatTime(iso: string, now: Date = new Date()): string {
  // Date-context-aware formatter (slice 4d0 polish, 2026-06-07).
  //   same day      → "HH:MM:SS"
  //   yesterday     → "Yesterday · HH:MM:SS"
  //   within 7 days → "Sat · HH:MM:SS"  (3-letter weekday)
  //   older         → "Jun 6 · HH:MM:SS"
  // Stripping the date silently confuses readers viewing multi-day-old
  // trips; per the slice 4d0 Sunday smoke fourth-UI-data-context-bug
  // observation, any timestamp in a list of historical events needs
  // relative-date framing.
  let d: Date;
  try {
    d = new Date(iso);
    if (Number.isNaN(d.getTime())) throw new Error("NaN");
  } catch {
    return iso.slice(11, 19);
  }
  const time = d.toLocaleTimeString(undefined, { hour12: false });

  // Compare against now's calendar day (browser TZ).
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

function _AgentFinishRow({ row }: { row: AgentSummaryAgentFinishRow }) {
  return (
    <li key={`${row.event}-${row.timestamp}`} className="flex items-baseline justify-between gap-4">
      <div className="flex items-center gap-2">
        <span className="material-symbols-outlined text-primary text-base" aria-hidden>
          psychology
        </span>
        <span className="text-label-md text-on-surface">{row.event}</span>
        <span className="text-label-sm text-on-surface-variant">{_formatTime(row.timestamp)}</span>
      </div>
      <span className="text-label-sm text-on-surface-variant">
        {_formatDuration(row.elapsed_ms)}
      </span>
    </li>
  );
}

function _CallbackSummaryRow({ row }: { row: AgentSummaryCallbackSummaryRow }) {
  // Summary-row visual treatment (spec §9.15): bold weight + subtle
  // surface-container-low background + summarize icon + count tally
  // instead of timing columns. Marks this row as the activity-panel
  // footer / qek-a observability tally, structurally distinct from
  // per-event AgentFinish rows.
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
        {row.step_callback_count} step events · {row.task_callback_count} task events
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
  // Filter task_completed (redundant CrewAI hook). AgentFinish +
  // callback_summary both surface meaningful, distinct signal.
  const visible = agentSummary.filter(
    (row) => row.event === "AgentFinish" || row.event === "callback_summary",
  );
  return (
    <details
      open={defaultExpanded}
      className="rounded-xl border border-outline-variant bg-surface-container-lowest p-4"
    >
      <summary className="cursor-pointer text-label-md text-on-surface hover:text-primary">
        How this plan was made
      </summary>
      <div className="mt-4">
        {visible.length === 0 ? (
          <p className="text-body-md italic text-on-surface-variant">
            No agent activity recorded for this run.
          </p>
        ) : (
          <ul className="space-y-3">
            {visible.map((row) => {
              // TypeScript narrowing on row.event picks the right
              // variant component. Compile-time exhaustiveness check
              // protects against future event-type additions.
              if (row.event === "AgentFinish") {
                return <_AgentFinishRow key={`${row.event}-${row.timestamp}`} row={row} />;
              }
              return <_CallbackSummaryRow key={`${row.event}`} row={row} />;
            })}
          </ul>
        )}
      </div>
    </details>
  );
}
