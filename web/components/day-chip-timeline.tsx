/**
 * DayChipTimeline — horizontal day-scroll timeline with sticky variant.
 *
 * Slice 4.3 — spec §9.4 + spec v1.1 prep §17.1 sticky-when-scrolling.
 * Renders one chip per day; the currentDayId chip carries the "Current"
 * badge per §9.4 active-day pattern. Container is sticky to keep the
 * day navigation in view as the user scrolls within a day's blocks.
 */

import type { TripDay } from "@/lib/backend";

export function DayChipTimeline({
  days,
  currentDayId,
}: {
  days: TripDay[];
  currentDayId?: string;
}) {
  return (
    <div className="sticky top-20 z-30 glass-header py-3 -mx-2 px-2">
      <div className="itinerary-scroll flex gap-4 overflow-x-auto pb-2 snap-x">
        {days.map((day) => {
          const isCurrent = day.id === currentDayId;
          return (
            <div
              key={day.id}
              className={`min-w-[160px] rounded-xl border p-4 snap-start transition-all ${
                isCurrent
                  ? "border-2 border-primary bg-surface-container-lowest editorial-shadow relative"
                  : "border-outline-variant bg-surface-container-lowest"
              }`}
            >
              {isCurrent && (
                <div className="absolute -top-3 right-3 bg-primary text-on-primary text-label-sm px-2 py-0.5 rounded-full uppercase font-bold">
                  Current
                </div>
              )}
              <p className="text-label-sm text-on-surface-variant mb-1">
                Day {day.day_number}
                {day.date && <span className="ml-2">{day.date}</span>}
              </p>
              {day.summary && (
                <p className="text-label-md text-on-surface line-clamp-1">{day.summary}</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
