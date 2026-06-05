/**
 * BlockDetail — expanded-state content body for a block.
 *
 * Slice 4.3 — rendered inside <BlockExpand />'s Sheet (mobile) or Dialog
 * (desktop). v1.0a renders: notes, start_time + duration, est_cost,
 * sources (URLs). Empty-state placeholders for fields the backend will
 * enrich in future slices (per trip-concierge-gco): opening_hours,
 * full_address, photos, why_picked.
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

export function BlockDetail({ block }: { block: Block }) {
  const cost = _formatCost(block.est_cost, block.currency);
  const duration = _formatDuration(block.duration_minutes);

  return (
    <div className="space-y-4 p-2">
      <h3 className="text-headline-md text-on-surface">{block.venue_name}</h3>

      <dl className="grid grid-cols-2 gap-3 text-sm">
        {block.start_time && (
          <div>
            <dt className="text-on-surface-variant text-label-sm uppercase tracking-wider">
              Start
            </dt>
            <dd className="text-on-surface">{block.start_time}</dd>
          </div>
        )}
        {duration && (
          <div>
            <dt className="text-on-surface-variant text-label-sm uppercase tracking-wider">
              Duration
            </dt>
            <dd className="text-on-surface">{duration}</dd>
          </div>
        )}
        {cost && (
          <div>
            <dt className="text-on-surface-variant text-label-sm uppercase tracking-wider">
              Est. cost
            </dt>
            <dd className="text-on-surface">{cost}</dd>
          </div>
        )}
      </dl>

      {block.notes && (
        <div>
          <h4 className="text-label-sm uppercase tracking-wider text-on-surface-variant">Notes</h4>
          <p className="mt-1 text-body-md text-on-surface">{block.notes}</p>
        </div>
      )}

      {block.sources.length > 0 ? (
        <div>
          <h4 className="text-label-sm uppercase tracking-wider text-on-surface-variant">
            Sources
          </h4>
          <ul className="mt-1 space-y-1">
            {block.sources.map((s) => (
              <li key={s.id}>
                <a
                  href={s.url}
                  className="text-sm text-primary underline focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
                  rel="noopener noreferrer"
                  target="_blank"
                >
                  {s.url}
                </a>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Empty-state placeholders for fields backend enrichment will
          populate later. Tracked as trip-concierge-gco. */}
      <p className="text-label-sm italic text-on-surface-variant">
        Opening hours, full address, photos, and the "why this was picked" rationale will appear
        here once the planner enriches each block.
      </p>
    </div>
  );
}
