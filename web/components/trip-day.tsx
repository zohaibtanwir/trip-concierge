/**
 * TripDay — renders one calendar day's header + summary + blocks.
 *
 * Slice 4.2. Branches on blocks.length === 0 to show an empty-day
 * fallback (per the slice 4.2 "failed trips have 0 days" data shape;
 * also covers a partial generation where one day was skipped).
 *
 * Tests in tests/trip-row-and-day.test.tsx exercise the empty-day
 * fallback and the ordered-rendering invariant.
 */

import { TripBlock } from "@/components/trip-block";
import type { TripDay as TripDayShape } from "@/lib/backend";

export function TripDay({ day }: { day: TripDayShape }) {
  return (
    <section className="mb-8">
      <header className="mb-3">
        <h2 className="text-lg font-semibold">
          Day {day.day_number}
          {day.date && <span className="ml-2 text-sm text-slate-500">{day.date}</span>}
        </h2>
        {day.summary && <p className="text-sm text-slate-600 mt-1">{day.summary}</p>}
      </header>
      {day.blocks.length === 0 ? (
        <p className="text-sm text-slate-500 italic">No blocks for this day yet.</p>
      ) : (
        <div className="space-y-2">
          {day.blocks.map((b) => (
            <TripBlock key={b.id} block={b} />
          ))}
        </div>
      )}
    </section>
  );
}
