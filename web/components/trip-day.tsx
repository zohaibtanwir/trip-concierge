/**
 * TripDay — renders one calendar day's header + summary + blocks.
 *
 * Slice 4.3 — spec §9.5 vertical-timeline pattern: numbered circles
 * (bg-primary-container) connected by a w-0.5 vertical line. Each block
 * sits to the right of its circle.
 *
 * Tests in tests/trip-row-and-day.test.tsx exercise the empty-day
 * fallback, the ordered-rendering invariant, and the §9.5 pattern via
 * source-file content read.
 */

import { TripBlock } from "@/components/trip-block";
import type { TripDay as TripDayShape } from "@/lib/backend";

export function TripDay({ day }: { day: TripDayShape }) {
  return (
    <section className="mb-12">
      <header className="mb-6">
        <h2 className="text-headline-md text-on-surface">
          Day {day.day_number}
          {day.date && (
            <span className="ml-3 text-label-sm text-on-surface-variant">{day.date}</span>
          )}
        </h2>
        {day.summary && <p className="mt-2 text-body-md text-on-surface-variant">{day.summary}</p>}
      </header>
      {day.blocks.length === 0 ? (
        <p className="text-body-md italic text-on-surface-variant">No blocks for this day yet.</p>
      ) : (
        <div className="space-y-0">
          {day.blocks.map((b, idx) => (
            <div key={b.id} className="flex gap-6 group">
              {/* §9.5 numbered circle + vertical connector */}
              <div className="flex flex-col items-center">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary-container text-on-primary-container font-bold">
                  {idx + 1}
                </div>
                {idx < day.blocks.length - 1 && (
                  <div className="w-0.5 flex-1 bg-outline-variant my-2" />
                )}
              </div>
              <div className="flex-1 pb-6">
                <TripBlock block={b} />
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
