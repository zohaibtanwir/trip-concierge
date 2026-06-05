/**
 * Page composition test — app/trips/[id]/page.tsx (slice 4.2 / 2th).
 *
 * The detail RSC's contract:
 *   1. Auth-gated by middleware (assumed; not re-tested here).
 *   2. Calls `auth()` for the session, then `fetchTripDetail({userId,
 *      tripId})` which internally composes /full + /plan/status.
 *   3. Branches on planStatus.state:
 *        planning  → "Your trip is being planned" + progress message
 *        done+ok   → renders day-by-day blocks
 *        failed    → error message + back-to-list link
 *   4. Exports `const dynamic = 'force-dynamic'` so Next.js 15 doesn't
 *      cache RSC output across renders (planning UX requires fresh
 *      /plan/status). Pinned by this test until trip-concierge-jv7
 *      lands a build-time guard.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Hoisted by vitest. Per-test behavior is configured via the mocked
// module's .mockResolvedValue() in each test body.
vi.mock("@/auth", () => ({
  auth: vi.fn(async () => ({ user: { id: "user-abc", email: "u@test.com" } })),
}));
vi.mock("@/lib/backend", () => ({
  fetchTripDetail: vi.fn(),
  fetchTripList: vi.fn(),
  mintMcpToken: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.resetModules();
  vi.restoreAllMocks();
});

const _TRIP_BASE = {
  id: "trip-1",
  user_id: "user-abc",
  status: "draft",
  destination: "Coorg, India",
  start_date: null,
  end_date: null,
  group_size: 2,
  budget_total: "40000.00",
  currency: "INR",
  constraints: {},
  pace: "balanced",
  created_at: "2026-06-04T13:48:32Z",
  updated_at: "2026-06-04T13:48:32Z",
};

describe("/trips/[id] detail page", () => {
  it("branches to PLANNING surface when planStatus.state ∈ {queued, running}", async () => {
    const backend = await import("@/lib/backend");
    (backend.fetchTripDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      trip: { ..._TRIP_BASE, days: [] },
      planStatus: {
        state: "running",
        approved: null,
        job_id: "job-running",
        kind: "plan",
        progress_message: {
          agent: "Researcher",
          pass: 1,
          message: "Searching for venues",
        },
      },
    });

    const Page = (await import("@/app/trips/[id]/page")).default;
    render(await Page({ params: Promise.resolve({ id: "trip-1" }) }));

    // The planning surface must surface "planning" language AND the
    // progress message body so the user sees what the crew is working on.
    expect(screen.getByText(/being planned|in progress|planning/i)).toBeDefined();
    expect(screen.getByText(/Researcher/)).toBeDefined();
  });

  it("branches to SUCCEEDED surface and renders day-by-day blocks", async () => {
    const backend = await import("@/lib/backend");
    (backend.fetchTripDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      trip: {
        ..._TRIP_BASE,
        days: [
          {
            id: "day-1",
            day_number: 1,
            date: "2026-07-01",
            summary: "Arrival + coffee plantation tour",
            blocks: [
              {
                id: "block-1",
                order: 1,
                type: "venue",
                venue_name: "Tata Coffee Plantation",
                lat: null,
                lng: null,
                start_time: "09:00",
                duration_minutes: 120,
                est_cost: "500.00",
                currency: "INR",
                locked: false,
                notes: "Guided tour available",
                sources: [],
              },
            ],
          },
        ],
      },
      planStatus: { state: "done", approved: true, job_id: "job-1", kind: "plan" },
    });

    const Page = (await import("@/app/trips/[id]/page")).default;
    render(await Page({ params: Promise.resolve({ id: "trip-1" }) }));

    expect(screen.getByText(/Tata Coffee Plantation/)).toBeDefined();
    // Summary may appear in both the left-column TripDay header AND the
    // right-column day-chip timeline. Loose match.
    expect(screen.getAllByText(/Arrival \+ coffee plantation tour/).length).toBeGreaterThan(0);
    // "Day 1" appears in the day header + the right-column chip — getAllByText.
    expect(screen.getAllByText(/Day 1/).length).toBeGreaterThan(0);
  });

  it("branches to FAILED surface with error message + back-to-list link", async () => {
    const backend = await import("@/lib/backend");
    (backend.fetchTripDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      trip: { ..._TRIP_BASE, days: [] },
      planStatus: {
        state: "failed",
        approved: null,
        job_id: "job-failed",
        kind: "plan",
        error: "the planner could not satisfy your budget",
      },
    });

    const Page = (await import("@/app/trips/[id]/page")).default;
    render(await Page({ params: Promise.resolve({ id: "trip-1" }) }));

    // Headline (failed surface) + body (error message) often share
    // failure-related words ("could not", "didn't"). getAllByText
    // tolerates both matching.
    const failedTexts = screen.getAllByText(/didn't generate|did not complete|failed|could not/i);
    expect(failedTexts.length).toBeGreaterThan(0);
    expect(screen.getByText(/the planner could not satisfy your budget/)).toBeDefined();

    // Both the header crumb and the body CTA are back-to-list links.
    const backLinks = screen.getAllByRole("link", {
      name: /back to list|all trips|trips/i,
    });
    expect(backLinks.length).toBeGreaterThan(0);
    for (const link of backLinks) {
      expect(link.getAttribute("href")).toBe("/trips");
    }
  });

  it("renders <PlanAgainDialog /> on the FAILED branch", async () => {
    // Slice 4.3 wires Q9: Plan again is failed-only. The component is
    // imported and rendered when isFailed is true; succeeded/planning/
    // no_job branches must NOT include it.
    const backend = await import("@/lib/backend");
    (backend.fetchTripDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      trip: { ..._TRIP_BASE, days: [] },
      planStatus: {
        state: "failed",
        approved: null,
        job_id: "job-failed",
        kind: "plan",
        error: "FatalJobError",
        agent_summary: [],
      },
    });

    const Page = (await import("@/app/trips/[id]/page")).default;
    render(await Page({ params: Promise.resolve({ id: "trip-1" }) }));

    expect(screen.getByRole("button", { name: /plan again/i })).toBeDefined();
  });

  it("renders agent_summary via <PlanHistoryPanel /> on succeeded branch", async () => {
    // Slice 4.3 — PRD §F8 partial. The sticky right panel includes the
    // 'How this plan was made' surface, sourced from planStatus.agent_summary.
    const backend = await import("@/lib/backend");
    (backend.fetchTripDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      trip: { ..._TRIP_BASE, days: [] },
      planStatus: {
        state: "done",
        approved: true,
        job_id: "job-ok",
        kind: "plan",
        agent_summary: [{ agent: "Researcher", step: 1, duration_ms: 32500, tokens: 1840 }],
      },
    });

    const Page = (await import("@/app/trips/[id]/page")).default;
    render(await Page({ params: Promise.resolve({ id: "trip-1" }) }));

    // PlanHistoryPanel header surface.
    expect(screen.getByText(/how this plan was made/i)).toBeDefined();
    // Agent row visible (the panel renders agents inline; if a future change
    // collapses by default the test would need adjustment but the assertion
    // confirms the surface exists at the page level).
    expect(screen.getByText(/Researcher/)).toBeDefined();
  });

  it("renders the no_job fallback section when planStatus.state === 'no_job'", async () => {
    // Slice 4.2 tightening — pins the genuinely-unplanned UX state.
    // With the active-job overlay in fetchTripDetail, no_job is rare
    // (worker died at enqueue + Redis key absent). The fallback must
    // still render honestly so the page isn't blank.
    const backend = await import("@/lib/backend");
    (backend.fetchTripDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      trip: { ..._TRIP_BASE, days: [] },
      planStatus: { state: "no_job", approved: null, job_id: null, kind: null },
    });

    const Page = (await import("@/app/trips/[id]/page")).default;
    render(await Page({ params: Promise.resolve({ id: "trip-1" }) }));

    expect(screen.getByText(/hasn't been planned yet/i)).toBeDefined();
  });

  it("pins the dynamic = 'force-dynamic' route segment opt-out", async () => {
    // Until trip-concierge-jv7 lands a build-time guard, this assertion
    // is the only thing preventing a silent regression on Next.js 15
    // RSC caching defaults. If anyone removes the export, planning-state
    // UX breaks (cached "Not started" badge during in-flight planning).
    const mod = await import("@/app/trips/[id]/page");
    expect(mod.dynamic).toBe("force-dynamic");
  });
});
