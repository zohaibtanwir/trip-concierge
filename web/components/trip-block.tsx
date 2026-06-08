/**
 * TripBlock — pure render of a single itinerary block in the day list.
 *
 * Slice 4.3 — spec §8 Material Symbols by block.type:
 *   venue   → location_on
 *   meal    → restaurant
 *   transit → directions_car
 *   rest    → bed
 *
 * Slice 4.6 commit 3 — bottom-right block-action cluster. Currently
 * houses the "Swap this" trigger; commit 4 adds the lock toggle
 * adjacent. tripId/userId/dayNumber are optional so legacy callers
 * (none currently, but the door stays open) can skip rendering the
 * action cluster.
 *
 * The block-expand surface (Sheet/Dialog) wraps this in
 * <BlockExpand /> at the page level. This component itself is the
 * default (collapsed) rendering — venue name + meta line + optional
 * notes preview + action cluster.
 */

import { BlockAlternativeDialog } from "@/components/block-alternative-dialog";
import { BlockLockToggle } from "@/components/block-lock-toggle";
import type { Block } from "@/lib/backend";

const _ICON_BY_TYPE: Record<string, string> = {
  venue: "location_on",
  meal: "restaurant",
  transit: "directions_car",
  rest: "bed",
};

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

interface TripBlockProps {
  block: Block;
  tripId?: string;
  userId?: string;
  dayNumber?: number;
}

export function TripBlock({ block, tripId, userId, dayNumber }: TripBlockProps) {
  const cost = _formatCost(block.est_cost, block.currency);
  const duration = _formatDuration(block.duration_minutes);
  const icon = _ICON_BY_TYPE[block.type] ?? "place";
  const canSwap = Boolean(tripId && userId && dayNumber !== undefined);

  return (
    <div>
      <div className="flex items-center gap-2">
        <span className="material-symbols-outlined text-primary text-lg" aria-hidden>
          {icon}
        </span>
        <h5 className="text-label-md text-on-surface">{block.venue_name}</h5>
      </div>
      <div className="mt-1 flex flex-wrap gap-3 text-sm text-on-surface-variant">
        {block.start_time && <span>{block.start_time}</span>}
        {duration && <span>{duration}</span>}
        {cost && <span>{cost}</span>}
      </div>
      {block.notes && <p className="mt-2 text-body-md text-on-surface-variant">{block.notes}</p>}
      {canSwap && tripId && userId && dayNumber !== undefined && (
        <div className="mt-3 flex justify-end gap-2">
          <BlockLockToggle
            tripId={tripId}
            userId={userId}
            blockId={block.id}
            initialLocked={block.locked}
          />
          <BlockAlternativeDialog
            tripId={tripId}
            userId={userId}
            blockId={block.id}
            blockVenueName={block.venue_name}
            dayNumber={dayNumber}
          />
        </div>
      )}
    </div>
  );
}
