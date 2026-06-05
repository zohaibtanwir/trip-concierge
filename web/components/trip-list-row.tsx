/**
 * TripListRow — one row in the trip list, click-through to detail.
 *
 * Slice 4.2. Renders state-badge + destination + dates + budget. The
 * entire row is an anchor tag whose href points to /trips/[id]; the
 * detail page is the next stop in the navigational flow.
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
      className="block border border-slate-200 rounded-lg p-4 hover:bg-slate-50 transition-colors"
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium text-slate-900">{item.destination}</span>
        <StateBadge state={item.state as TripState} />
      </div>
      <div className="text-sm text-slate-600 mt-1 flex gap-3 flex-wrap">
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
