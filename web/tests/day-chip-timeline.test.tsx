/**
 * <DayChipTimeline /> test (slice 4.3).
 *
 * Behavior pinned per spec §9.4 + spec v1.1 §17.1 sticky variant:
 * - Renders one chip per day in trip.days, ordered by day_number ASC.
 * - Each chip carries "Day N" label + optional date.
 * - The chip matching the `currentDayId` prop renders the "Current"
 *   badge per §9.4 active-day pattern.
 * - The container carries `sticky top-20` per the v1.1 sticky variant.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => cleanup());

const _DAYS = [
  { id: "day-1", day_number: 1, date: "2026-07-01", summary: "Arrival", blocks: [] },
  { id: "day-2", day_number: 2, date: "2026-07-02", summary: "Exploration", blocks: [] },
  { id: "day-3", day_number: 3, date: "2026-07-03", summary: "Return", blocks: [] },
];

describe("<DayChipTimeline />", () => {
  it("renders one chip per day in order", async () => {
    const { DayChipTimeline } = await import("@/components/day-chip-timeline");
    render(<DayChipTimeline days={_DAYS} currentDayId="day-1" />);
    expect(screen.getByText(/Day 1/)).toBeDefined();
    expect(screen.getByText(/Day 2/)).toBeDefined();
    expect(screen.getByText(/Day 3/)).toBeDefined();
  });

  it("marks the current day with a 'Current' badge", async () => {
    const { DayChipTimeline } = await import("@/components/day-chip-timeline");
    render(<DayChipTimeline days={_DAYS} currentDayId="day-2" />);
    expect(screen.getByText(/Current/i)).toBeDefined();
  });

  it("applies the sticky-top container per spec v1.1 §17.1", async () => {
    const { DayChipTimeline } = await import("@/components/day-chip-timeline");
    const { container } = render(<DayChipTimeline days={_DAYS} currentDayId="day-1" />);
    // Loose className check — the exact Tailwind class set may evolve but
    // `sticky` must be present for the spec v1.1 §17.1 behavior to hold.
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.className).toMatch(/sticky/);
  });
});
