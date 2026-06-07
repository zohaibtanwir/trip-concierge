/**
 * Page composition test — app/trips/page.tsx (slice 4.2 / trip-concierge-2th).
 *
 * The list RSC's contract:
 *   1. Auth-gated by middleware (assumed; not re-tested here).
 *   2. Calls `auth()` to get the session, then `fetchTripList({userId})`.
 *   3. Renders one TripListRow per item plus a state badge.
 *   4. Empty state when no trips.
 *
 * The component imports are dynamic so this test file can run against a
 * codebase where the page doesn't exist yet (failing-first commit). When
 * impl lands, the import resolves and the assertions run.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Hoisted by vitest. Per-test behavior is configured via the mocked
// module's .mockResolvedValue() in each test body.
vi.mock("@/auth", () => ({
  auth: vi.fn(async () => ({ user: { id: "user-abc", email: "u@test.com" } })),
}));
vi.mock("@/lib/backend", () => ({
  fetchTripList: vi.fn(async () => []),
  fetchTripDetail: vi.fn(),
  mintMcpToken: vi.fn(),
}));
// Slice 4.5c: Header is an async RSC; vitest can't await nested
// components rendered inside the page. Header's surface is covered
// by tests/header.test.tsx.
vi.mock("@/components/header", () => ({
  Header: () => null,
}));

afterEach(() => {
  cleanup();
  vi.resetModules();
  vi.restoreAllMocks();
});

const _MIXED_STATE_FIXTURE = [
  {
    id: "trip-succ",
    destination: "Coorg, India",
    start_date: "2026-07-01",
    end_date: "2026-07-03",
    currency: "INR",
    budget_total: "40000.00",
    state: "succeeded",
    created_at: "2026-06-04T13:48:32Z",
  },
  {
    id: "trip-fail",
    destination: "Pondicherry, India",
    start_date: null,
    end_date: null,
    currency: "INR",
    budget_total: "40000.00",
    state: "failed",
    created_at: "2026-05-29T13:14:40Z",
  },
  {
    id: "trip-plan",
    destination: "Goa, India",
    start_date: null,
    end_date: null,
    currency: "INR",
    budget_total: "40000.00",
    state: "planning",
    created_at: "2026-06-05T05:00:00Z",
  },
  {
    id: "trip-nojob",
    destination: "Hampi, India",
    start_date: null,
    end_date: null,
    currency: "INR",
    budget_total: null,
    state: "no_job",
    created_at: "2026-05-28T07:26:43Z",
  },
];

describe("/trips list page", () => {
  it("renders a row per trip with destination + state badge label", async () => {
    const backend = await import("@/lib/backend");
    (backend.fetchTripList as ReturnType<typeof vi.fn>).mockResolvedValue(_MIXED_STATE_FIXTURE);

    const Page = (await import("@/app/trips/page")).default;
    render(await Page({ searchParams: Promise.resolve({}) }));

    // Each destination appears.
    expect(screen.getByText(/Coorg, India/)).toBeDefined();
    expect(screen.getByText(/Pondicherry, India/)).toBeDefined();
    expect(screen.getByText(/Goa, India/)).toBeDefined();
    expect(screen.getByText(/Hampi, India/)).toBeDefined();

    // All four state badge labels appear (per refinement #2: Ready,
    // Failed, Planning…, Not started).
    expect(screen.getByText(/Ready/)).toBeDefined();
    expect(screen.getByText(/Failed/)).toBeDefined();
    expect(screen.getByText(/Planning/)).toBeDefined();
    expect(screen.getByText(/Not started/)).toBeDefined();
  });

  it("renders an empty state when fetchTripList returns []", async () => {
    const backend = await import("@/lib/backend");
    (backend.fetchTripList as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    const Page = (await import("@/app/trips/page")).default;
    render(await Page({ searchParams: Promise.resolve({}) }));

    // Some clear "you have no trips yet" surface. We're loose on the
    // exact copy (the empty state may use "No trips yet", "Plan your
    // first trip", etc.) — the test asserts SOMETHING substantive
    // renders rather than a blank page. getAllByText tolerates the
    // common shape of headline-plus-subtitle.
    const matches = screen.getAllByText(/no trips|first trip/i);
    expect(matches.length).toBeGreaterThan(0);
  });

  it("makes each trip row a link to /trips/[id]", async () => {
    const backend = await import("@/lib/backend");
    (backend.fetchTripList as ReturnType<typeof vi.fn>).mockResolvedValue(
      _MIXED_STATE_FIXTURE.slice(0, 1),
    );

    const Page = (await import("@/app/trips/page")).default;
    render(await Page({ searchParams: Promise.resolve({}) }));

    const link = screen.getByRole("link", { name: /Coorg/i });
    expect(link.getAttribute("href")).toBe("/trips/trip-succ");
  });
});
