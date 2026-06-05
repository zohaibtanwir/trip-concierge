/**
 * Branching-component tests — trip-list-row + trip-day (slice 4.2 / 2th).
 *
 * Per the slice 4.2 refinement #4: trip-block and state-badge are pure-
 * render with no branching logic, so they don't get their own test files
 * (their behavior is exercised transitively by these tests and by the
 * page-composition tests). trip-list-row and trip-day DO branch:
 *
 *   trip-list-row: state-badge selection (4-way), click-through link
 *   trip-day:      empty-blocks fallback, ordered block rendering
 *
 * Failing-first: imports of @/components/* throw until commit 2 lands
 * the implementations.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TripListItem } from "@/lib/backend";

afterEach(() => {
  cleanup();
  vi.resetModules();
});

// --- trip-list-row ---

describe("<TripListRow />", () => {
  const _BASE_ROW: TripListItem = {
    id: "trip-1",
    destination: "Coorg, India",
    start_date: null,
    end_date: null,
    currency: "INR",
    budget_total: "40000.00",
    state: "succeeded",
    created_at: "2026-06-04T13:48:32Z",
  };

  it.each([
    ["succeeded" as const, /Ready/],
    ["failed" as const, /Failed/],
    ["planning" as const, /Planning/],
    ["no_job" as const, /Not started/],
  ])("renders the %s badge label", async (state, labelRegex) => {
    const { TripListRow } = await import("@/components/trip-list-row");
    render(<TripListRow item={{ ..._BASE_ROW, state }} />);
    expect(screen.getByText(labelRegex)).toBeDefined();
  });

  it("renders an anchor tag whose href is /trips/[id]", async () => {
    const { TripListRow } = await import("@/components/trip-list-row");
    render(<TripListRow item={_BASE_ROW} />);
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("/trips/trip-1");
  });

  it("uses spec §3.6 palette tokens (primary / error), not slice 4.2's slate-amber-emerald-rose", async () => {
    // Slice 4.3 — migration per design-spec.md §14. The state badge classes
    // must reference the spec §3.6 palette tokens. This test reads the
    // state-badge source file and asserts the new tokens replaced the old.
    const { readFileSync } = await import("node:fs");
    const { resolve } = await import("node:path");
    const src = readFileSync(resolve(__dirname, "../components/state-badge.tsx"), "utf-8");
    // New tokens must appear (at least one per state).
    expect(src).toMatch(/bg-primary|bg-error-container|bg-surface-container|bg-primary-fixed/);
    // Old tokens from slice 4.2 must NOT appear.
    expect(src).not.toMatch(/bg-emerald-100|bg-rose-100|bg-amber-100|bg-slate-100/);
  });
});

// --- trip-day ---

describe("<TripDay />", () => {
  const _DAY_BASE = {
    id: "day-1",
    day_number: 1,
    date: "2026-07-01",
    summary: "Arrival day",
    blocks: [
      {
        id: "block-1",
        order: 1,
        type: "venue",
        venue_name: "Coffee plantation",
        lat: null,
        lng: null,
        start_time: "09:00",
        duration_minutes: 120,
        est_cost: "500.00",
        currency: "INR",
        locked: false,
        notes: "",
        sources: [],
      },
      {
        id: "block-2",
        order: 2,
        type: "meal",
        venue_name: "Lunch at homestay",
        lat: null,
        lng: null,
        start_time: "13:00",
        duration_minutes: 60,
        est_cost: "300.00",
        currency: "INR",
        locked: false,
        notes: "",
        sources: [],
      },
    ],
  };

  it("renders blocks in their declared order", async () => {
    const { TripDay } = await import("@/components/trip-day");
    render(<TripDay day={_DAY_BASE} />);

    const coffee = screen.getByText(/Coffee plantation/);
    const lunch = screen.getByText(/Lunch at homestay/);

    // Both must render.
    expect(coffee).toBeDefined();
    expect(lunch).toBeDefined();

    // DOM order: coffee before lunch.
    const coffeePos = coffee.compareDocumentPosition(lunch);
    expect(coffeePos & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("renders an empty-blocks fallback when day.blocks is empty", async () => {
    const { TripDay } = await import("@/components/trip-day");
    render(<TripDay day={{ ..._DAY_BASE, blocks: [] }} />);
    // Loose copy assertion — exact text can be "no blocks yet" / "no
    // activities planned" / etc. Pins the fallback exists.
    expect(screen.getByText(/no (blocks|activities|plans)/i)).toBeDefined();
  });

  it("renders the day header with the day_number", async () => {
    const { TripDay } = await import("@/components/trip-day");
    render(<TripDay day={_DAY_BASE} />);
    expect(screen.getByText(/Day 1/)).toBeDefined();
  });

  it("renders blocks with §9.5 numbered-circle vertical timeline pattern", async () => {
    // Slice 4.3 — spec §9.5 specifies numbered circles + vertical connector
    // line as the block-rendering pattern within a day. This test reads the
    // trip-day.tsx source and asserts the pattern is present (numbered
    // circles via flex layout + connector via vertical w-0.5 divider).
    const { readFileSync } = await import("node:fs");
    const { resolve } = await import("node:path");
    const src = readFileSync(resolve(__dirname, "../components/trip-day.tsx"), "utf-8");
    // §9.5 marker: bg-primary-container on the numbered circle.
    expect(src).toMatch(/bg-primary-container/);
    // §9.5 connector marker: vertical thin line (w-0.5 + bg-outline-variant).
    expect(src).toMatch(/w-0\.5/);
  });
});
