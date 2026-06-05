/**
 * StateBadge — pure render of the 4-way derived trip state.
 *
 * Slice 4.2 — see backend/app/services/trip_service.list_trips_for_user
 * for the state derivation rules.
 *
 * Pure render: no logic beyond the table mapping. No tests for this file
 * (the table is exercised transitively by trip-list-row tests via
 * `it.each`).
 */

export type TripState = "succeeded" | "failed" | "planning" | "no_job";

const _STATE_CLASSES: Record<TripState, string> = {
  succeeded: "bg-emerald-100 text-emerald-900",
  failed: "bg-rose-100 text-rose-900",
  planning: "bg-amber-100 text-amber-900",
  no_job: "bg-slate-100 text-slate-700",
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
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{label}</span>
  );
}
