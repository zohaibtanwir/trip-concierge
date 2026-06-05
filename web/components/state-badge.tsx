/**
 * StateBadge — pure render of the 4-way derived trip state.
 *
 * Slice 4.3 — migrated to spec §3.6 palette tokens (replaces slice 4.2's
 * slate/amber/emerald/rose Tailwind defaults). Each state maps to a
 * primary/error/surface token pair per the design table.
 *
 * Pure render: no logic beyond the table mapping. No tests on this file
 * directly — the §3.6 token migration is asserted by
 * tests/trip-row-and-day.test.tsx via file-content read.
 */

export type TripState = "succeeded" | "failed" | "planning" | "no_job";

const _STATE_CLASSES: Record<TripState, string> = {
  // spec §3.6 — palette tokens
  planning: "bg-primary-fixed-dim/20 text-on-primary-fixed-variant",
  succeeded: "bg-primary-container/10 text-primary",
  failed: "bg-error-container text-on-error-container",
  no_job: "bg-surface-container-high text-on-surface-variant",
};

const _STATE_LABELS: Record<TripState, string> = {
  succeeded: "Ready",
  failed: "Failed",
  planning: "Planning…",
  no_job: "Not started",
};

export function StateBadge({ state }: { state: TripState }) {
  const cls = _STATE_CLASSES[state];
  const label = _STATE_LABELS[state];
  return <span className={`rounded-full px-3 py-1 text-xs font-medium ${cls}`}>{label}</span>;
}
