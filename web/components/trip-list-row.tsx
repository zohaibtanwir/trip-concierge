/**
 * TripListRow — one row in the trip list, click-through to detail.
 *
 * Slice 4.3 — migrated to spec §3.6 palette tokens + spec §7
 * editorial-shadow / active-teal-glow on hover (replaces slice 4.2's
 * generic hover:bg-slate-50). State badge + destination + dates + budget.
 * Anchor wraps the whole row.
 *
 * Tests in tests/trip-row-and-day.test.tsx exercise the 4-way badge
 * mapping and the link href invariant.
 */

import Link from "next/link";

import { StateBadge, type TripState } from "@/components/state-badge";
import type { TripListItem } from "@/lib/backend";

function _formatDateRange(start: string | null, end: string | null): string | null {
  if (!start && !end) return null;
  if (start && end) return `${start} → ${end}`;
  return start ?? end;
}

export function TripListRow({ item }: { item: TripListItem }) {
  const dates = _formatDateRange(item.start_date, item.end_date);
  return (
    <Link
      href={`/trips/${item.id}`}
      className="block rounded-xl border border-outline-variant bg-surface-container-lowest p-6 transition-all editorial-shadow hover:active-teal-glow focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-lg font-semibold text-on-surface">{item.destination}</span>
        <StateBadge state={item.state as TripState} />
      </div>
      <div className="mt-2 flex flex-wrap gap-3 text-sm text-on-surface-variant">
        {dates && <span>{dates}</span>}
        {item.budget_total && (
          <span>
            {item.currency} {item.budget_total}
          </span>
        )}
      </div>
    </Link>
  );
}
