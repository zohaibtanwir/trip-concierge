/**
 * PlanHistoryPanel — "How this plan was made" surface.
 *
 * Slice 4.3 — PRD §F8 partial. Reads agent_summary (array of
 * {agent, step, duration_ms, tokens?}) and renders one row per agent
 * step with the agent name + duration. Collapsible via Details/Summary
 * — defaults to collapsed unless `defaultExpanded` is set.
 *
 * Tap-to-expand-step-reasoning per PRD §F8 acceptance is deferred to a
 * future slice (trip-concierge-gco backend enrichment + auu §17.5).
 * Empty agent_summary renders an honest "No agent activity recorded"
 * line (legacy pre-qek-a JobRuns).
 */

"use client";

import type { AgentSummaryRow } from "@/lib/backend";

function _formatDuration(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms}ms`;
}

export function PlanHistoryPanel({
  agentSummary,
  defaultExpanded = false,
}: {
  agentSummary: AgentSummaryRow[];
  defaultExpanded?: boolean;
}) {
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
            {agentSummary.map((row) => (
              <li
                key={`${row.agent}-${row.step}`}
                className="flex items-baseline justify-between gap-4"
              >
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-primary text-base" aria-hidden>
                    psychology
                  </span>
                  <span className="text-label-md text-on-surface">{row.agent}</span>
                </div>
                <span className="text-label-sm text-on-surface-variant">
                  {_formatDuration(row.duration_ms)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}
