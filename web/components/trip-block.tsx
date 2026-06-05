/**
 * TripBlock — pure render of a single itinerary block.
 *
 * Slice 4.2 — venue + time + cost + notes + sources. No swipe gestures,
 * no expand-collapse, no thumbnails — those land in slice 4.3 (refine UX).
 *
 * Pure render: no branching beyond null guards on optional fields. No
 * tests for this file (exercised transitively by trip-day tests).
 */

import type { Block } from "@/lib/backend";

function _formatCost(est_cost: string | null, currency: string): string | null {
  if (est_cost === null || est_cost === "") return null;
  return `${currency} ${est_cost}`;
}

function _formatDuration(minutes: number): string | null {
  if (!minutes) return null;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
}

export function TripBlock({ block }: { block: Block }) {
  const cost = _formatCost(block.est_cost, block.currency);
  const duration = _formatDuration(block.duration_minutes);

  return (
    <div className="border-l-2 border-slate-300 pl-4 py-2">
      <div className="flex items-baseline gap-2">
        <span className="font-medium">{block.venue_name}</span>
        <span className="text-xs uppercase text-slate-500">{block.type}</span>
      </div>
      <div className="text-sm text-slate-600 mt-1 flex gap-3 flex-wrap">
        {block.start_time && <span>{block.start_time}</span>}
        {duration && <span>{duration}</span>}
        {cost && <span>{cost}</span>}
      </div>
      {block.notes && <p className="text-sm text-slate-700 mt-2">{block.notes}</p>}
      {block.sources.length > 0 && (
        <ul className="text-xs text-slate-500 mt-2 list-disc list-inside">
          {block.sources.map((s) => (
            <li key={s.id}>
              <a href={s.url} className="underline" rel="noopener noreferrer" target="_blank">
                {s.url}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
