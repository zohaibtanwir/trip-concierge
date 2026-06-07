/**
 * PlanHistoryPanel — "How this plan was made" surface.
 *
 * Slice 4.3 (PRD §F8 partial) — repaired during slice 4d0 Sunday smoke
 * (2026-06-07) when the original fixture-self-referential schema
 * mismatch was caught: backend ships qek-a shape
 * {event, timestamp, elapsed_ms, output_excerpt}, not the pre-qek-a
 * shape {agent, step, duration_ms, tokens} the component used to read.
 *
 * Filter logic (Option C from the smoke triage dialogue):
 * - Surface AgentFinish events (the actual agent work)
 * - Surface callback_summary (final qek-a observability marker)
 * - Skip task_completed (redundant CrewAI hook fired alongside each
 *   AgentFinish, no additional signal)
 *
 * Display: "{event} · {time} · {elapsed}" — honest about the data
 * available without backend agent_role enrichment (tracked as P2).
 *
 * Tap-to-expand-step-reasoning per PRD §F8 acceptance still deferred to
 * a future slice (trip-concierge-gco backend enrichment + auu §17.5).
 * Empty agent_summary renders "No agent activity recorded" (legacy
 * pre-qek-a JobRuns and any failure-path rows that didn't capture
 * agent_summary).
 */

"use client";

import type { AgentSummaryRow } from "@/lib/backend";

function _formatDuration(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms}ms`;
}

function _formatTime(iso: string): string {
  // Render HH:MM:SS in the user's local timezone for human readability.
  // The raw ISO timestamp is preserved in the key so duplicate event
  // labels (multiple AgentFinish in one trace) don't collide.
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString(undefined, { hour12: false });
  } catch {
    return iso.slice(11, 19);
  }
}

export function PlanHistoryPanel({
  agentSummary,
  defaultExpanded = false,
}: {
  agentSummary: AgentSummaryRow[];
  defaultExpanded?: boolean;
}) {
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
            {visible.map((row) => (
              <li
                key={`${row.event}-${row.timestamp}`}
                className="flex items-baseline justify-between gap-4"
              >
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-primary text-base" aria-hidden>
                    psychology
                  </span>
                  <span className="text-label-md text-on-surface">{row.event}</span>
                  <span className="text-label-sm text-on-surface-variant">
                    {_formatTime(row.timestamp)}
                  </span>
                </div>
                <span className="text-label-sm text-on-surface-variant">
                  {_formatDuration(row.elapsed_ms)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}
