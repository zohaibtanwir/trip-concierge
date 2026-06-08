/**
 * Server Action contract test — web/lib/actions.ts (slice 4.3).
 *
 * Verifies planAgainAction's wire shape: mint a fresh MCP token, POST to
 * /trips/{id}/plan with x-tc-token header, return the parsed response.
 * Error propagation: non-2xx throws BackendError carrying the status.
 *
 * The "use server" directive at the top of actions.ts is a Next.js
 * runtime hint — vitest runs the module as plain TS and the directive
 * is effectively a no-op. We test the behavior, not the directive.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const _ORIG_FETCH = global.fetch;

beforeEach(() => {
  vi.stubEnv("BACKEND_URL", "http://test-backend");
  vi.stubEnv("INTERNAL_AUTH_SECRET", "test-internal-secret");
});

afterEach(() => {
  vi.unstubAllEnvs();
  global.fetch = _ORIG_FETCH;
  vi.resetModules();
});

function _jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("planAgainAction", () => {
  it("mints a token, POSTs /trips/{id}/plan with x-tc-token, returns parsed PlanStatus", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce(
      _jsonResponse({ mcp_token: "jwt-replan", expires_at: "2026-09-03T00:00:00Z" }),
    );
    fetchMock.mockResolvedValueOnce(
      _jsonResponse({
        state: "queued",
        approved: null,
        job_id: "job-new-xyz",
        kind: "plan",
        agent_summary: null,
      }),
    );
    global.fetch = fetchMock as unknown as typeof fetch;

    const { planAgainAction } = await import("@/lib/actions");
    const result = await planAgainAction("trip-failed-1", "user-abc");

    expect(result.state).toBe("queued");
    expect(result.job_id).toBe("job-new-xyz");

    // Verify the POST sequence.
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [planUrl, planInit] = fetchMock.mock.calls[1];
    expect(planUrl).toBe("http://test-backend/trips/trip-failed-1/plan");
    expect(planInit?.method).toBe("POST");
    expect((planInit?.headers as Record<string, string>)["x-tc-token"]).toBe("jwt-replan");
  });

  it("throws BackendError on non-2xx response", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce(_jsonResponse({ mcp_token: "jwt", expires_at: "x" }));
    fetchMock.mockResolvedValueOnce(new Response("trip not found", { status: 404 }));
    global.fetch = fetchMock as unknown as typeof fetch;

    const { planAgainAction } = await import("@/lib/actions");
    await expect(planAgainAction("trip-missing", "user-abc")).rejects.toThrow(/404/);
  });
});

describe("addConstraintAction", () => {
  it("mints token + POSTs /trips/{id}/constraints with kind + text body, returns parsed response", async () => {
    // Slice 4.5 first object-args Server Action (sets precedent for u8v
    // refactor of planAgainAction). Calls existing backend route from
    // slice 3.4a which appends to Trip.constraints['rules'] + auto-
    // enqueues a refine job. Response shape: {job_id, status_url}.
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce(
      _jsonResponse({ mcp_token: "jwt-constraint", expires_at: "2026-09-03T00:00:00Z" }),
    );
    fetchMock.mockResolvedValueOnce(
      _jsonResponse({
        job_id: "refine-new-xyz",
        status_url: "/trips/trip-1/plan/status",
      }),
    );
    global.fetch = fetchMock as unknown as typeof fetch;

    const { addConstraintAction } = await import("@/lib/actions");
    const result = await addConstraintAction({
      tripId: "trip-1",
      userId: "user-abc",
      kind: "dietary",
      text: "vegetarian",
    });

    expect(result.job_id).toBe("refine-new-xyz");
    expect(result.status_url).toBe("/trips/trip-1/plan/status");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [postUrl, postInit] = fetchMock.mock.calls[1];
    expect(postUrl).toBe("http://test-backend/trips/trip-1/constraints");
    expect(postInit?.method).toBe("POST");
    expect((postInit?.headers as Record<string, string>)["x-tc-token"]).toBe("jwt-constraint");
    expect(JSON.parse(postInit?.body as string)).toEqual({
      constraint_text: "vegetarian",
      constraint_kind: "dietary",
    });
  });

  it("throws BackendError on 403 (ownership mismatch propagates from backend)", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce(_jsonResponse({ mcp_token: "jwt", expires_at: "x" }));
    fetchMock.mockResolvedValueOnce(new Response("forbidden", { status: 403 }));
    global.fetch = fetchMock as unknown as typeof fetch;

    const { addConstraintAction } = await import("@/lib/actions");
    await expect(
      addConstraintAction({
        tripId: "other-user-trip",
        userId: "user-abc",
        kind: "dietary",
        text: "vegetarian",
      }),
    ).rejects.toThrow(/403/);
  });
});

describe("updateTripSettingsAction", () => {
  it("mints token + PATCHes /trips/{id} with pace + budget_total body, returns parsed response", async () => {
    // Slice 4.5b commit 2 — settings-shaped column writes via the new
    // PATCH /trips/{id} route landed in commit 1. Object-args pattern
    // (matches addConstraintAction). Wire shape: PATCH with JSON body
    // {pace?, budget_total?}, response shape {job_id, status_url}.
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce(
      _jsonResponse({ mcp_token: "jwt-settings", expires_at: "2026-09-03T00:00:00Z" }),
    );
    fetchMock.mockResolvedValueOnce(
      _jsonResponse({
        job_id: "patch-refine-xyz",
        status_url: "/trips/trip-1/plan/status",
      }),
    );
    global.fetch = fetchMock as unknown as typeof fetch;

    const { updateTripSettingsAction } = await import("@/lib/actions");
    const result = await updateTripSettingsAction({
      tripId: "trip-1",
      userId: "user-abc",
      pace: "packed",
      budgetTotal: 50000,
    });

    expect(result.job_id).toBe("patch-refine-xyz");
    expect(result.status_url).toBe("/trips/trip-1/plan/status");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [patchUrl, patchInit] = fetchMock.mock.calls[1];
    expect(patchUrl).toBe("http://test-backend/trips/trip-1");
    expect(patchInit?.method).toBe("PATCH");
    expect((patchInit?.headers as Record<string, string>)["x-tc-token"]).toBe("jwt-settings");
    expect(JSON.parse(patchInit?.body as string)).toEqual({
      pace: "packed",
      budget_total: 50000,
    });
  });

  it("omits undefined fields from PATCH body — pace-only call sends only pace", async () => {
    // The backend's at-least-one-of validator accepts {pace} alone OR
    // {budget_total} alone. The client must serialize ONLY the provided
    // fields — undefined values should not appear as keys with null.
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce(_jsonResponse({ mcp_token: "jwt", expires_at: "x" }));
    fetchMock.mockResolvedValueOnce(_jsonResponse({ job_id: "j", status_url: "/x" }));
    global.fetch = fetchMock as unknown as typeof fetch;

    const { updateTripSettingsAction } = await import("@/lib/actions");
    await updateTripSettingsAction({
      tripId: "trip-1",
      userId: "user-abc",
      pace: "lazy",
    });

    const [, patchInit] = fetchMock.mock.calls[1];
    const body = JSON.parse(patchInit?.body as string);
    expect(body).toEqual({ pace: "lazy" });
    expect(body).not.toHaveProperty("budget_total");
  });

  it("throws BackendError on 403 (ownership mismatch propagates from backend)", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce(_jsonResponse({ mcp_token: "jwt", expires_at: "x" }));
    fetchMock.mockResolvedValueOnce(new Response("forbidden", { status: 403 }));
    global.fetch = fetchMock as unknown as typeof fetch;

    const { updateTripSettingsAction } = await import("@/lib/actions");
    await expect(
      updateTripSettingsAction({
        tripId: "other-user-trip",
        userId: "user-abc",
        pace: "packed",
      }),
    ).rejects.toThrow(/403/);
  });
});

describe("createTripAction", () => {
  // Slice 4.5c commit 3.5 — web-side trip creation via the same
  // backend endpoint the MCP tool uses (POST /trips + POST
  // /trips/{id}/plan). Object-args per u8v precedent. Three-call
  // wire shape: mint → POST /trips → POST /trips/{id}/plan.

  it("mints token + POSTs /trips with payload + POSTs /trips/{id}/plan; returns {trip_id}", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce(
      _jsonResponse({ mcp_token: "jwt-create", expires_at: "2026-09-03T00:00:00Z" }),
    );
    // POST /trips → returns the trip row (TripRead shape)
    fetchMock.mockResolvedValueOnce(
      _jsonResponse(
        {
          id: "new-trip-uuid-1234",
          user_id: "user-abc",
          status: "draft",
          destination: "Goa, India",
          start_date: "2026-07-15",
          end_date: "2026-07-17",
          group_size: 2,
          budget_total: "40000.00",
          currency: "INR",
          constraints: {},
          pace: "balanced",
          created_at: "2026-06-07T00:00:00Z",
          updated_at: "2026-06-07T00:00:00Z",
        },
        201,
      ),
    );
    // POST /trips/{id}/plan → 202 with job info
    fetchMock.mockResolvedValueOnce(
      _jsonResponse(
        {
          state: "queued",
          approved: null,
          job_id: "plan-job-xyz",
          kind: "plan",
          agent_summary: null,
        },
        202,
      ),
    );
    global.fetch = fetchMock as unknown as typeof fetch;

    const { createTripAction } = await import("@/lib/actions");
    const result = await createTripAction({
      userId: "user-abc",
      destination: "Goa, India",
      startDate: "2026-07-15",
      endDate: "2026-07-17",
      groupSize: 2,
      budgetTotal: 40000,
      currency: "INR",
      pace: "balanced",
    });

    expect(result.trip_id).toBe("new-trip-uuid-1234");

    // Three calls: mint, POST /trips, POST /trips/{id}/plan
    expect(fetchMock).toHaveBeenCalledTimes(3);

    // Call 2: POST /trips with full payload
    const [createUrl, createInit] = fetchMock.mock.calls[1];
    expect(createUrl).toBe("http://test-backend/trips");
    expect(createInit?.method).toBe("POST");
    expect((createInit?.headers as Record<string, string>)["x-tc-token"]).toBe("jwt-create");
    expect(JSON.parse(createInit?.body as string)).toEqual({
      destination: "Goa, India",
      start_date: "2026-07-15",
      end_date: "2026-07-17",
      group_size: 2,
      budget_total: 40000,
      currency: "INR",
      pace: "balanced",
    });

    // Call 3: POST /trips/{new-trip-uuid-1234}/plan with same token
    const [planUrl, planInit] = fetchMock.mock.calls[2];
    expect(planUrl).toBe("http://test-backend/trips/new-trip-uuid-1234/plan");
    expect(planInit?.method).toBe("POST");
    expect((planInit?.headers as Record<string, string>)["x-tc-token"]).toBe("jwt-create");
  });

  it("omits undefined optional fields from the POST /trips body", async () => {
    // destination is the only required field. start_date / end_date /
    // budget_total are optional — when not provided, they should NOT
    // appear in the body (backend's Pydantic accepts missing optionals
    // but null vs missing has semantic difference for date fields).
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce(_jsonResponse({ mcp_token: "jwt", expires_at: "x" }));
    fetchMock.mockResolvedValueOnce(
      _jsonResponse({ id: "t-2", user_id: "user-abc", status: "draft" }, 201),
    );
    fetchMock.mockResolvedValueOnce(_jsonResponse({ job_id: "j" }, 202));
    global.fetch = fetchMock as unknown as typeof fetch;

    const { createTripAction } = await import("@/lib/actions");
    await createTripAction({
      userId: "user-abc",
      destination: "Hampi",
      groupSize: 1,
      currency: "INR",
      pace: "lazy",
    });

    const [, createInit] = fetchMock.mock.calls[1];
    const body = JSON.parse(createInit?.body as string);
    expect(body).toEqual({
      destination: "Hampi",
      group_size: 1,
      currency: "INR",
      pace: "lazy",
    });
    expect(body).not.toHaveProperty("start_date");
    expect(body).not.toHaveProperty("end_date");
    expect(body).not.toHaveProperty("budget_total");
  });

  it("throws BackendError if POST /trips fails (no /plan call made)", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce(_jsonResponse({ mcp_token: "jwt", expires_at: "x" }));
    fetchMock.mockResolvedValueOnce(new Response("bad destination", { status: 422 }));
    global.fetch = fetchMock as unknown as typeof fetch;

    const { createTripAction } = await import("@/lib/actions");
    await expect(
      createTripAction({
        userId: "user-abc",
        destination: "",
        groupSize: 1,
        currency: "USD",
        pace: "balanced",
      }),
    ).rejects.toThrow(/422/);

    // Only 2 calls: mint + POST /trips (failed). NO /plan call.
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("regenerateDayAction", () => {
  // Slice 4.6 commit 2 — day regenerate Server Action. Single backend
  // call to POST /trips/{tripId}/days/{dayNumber}/regenerate with an
  // optional hint. Returns the {job_id, status_url} pair the existing
  // route emits; caller (RegenerateDayDialog) navigates to the trip
  // detail page where planning-state UX takes over per Q2.

  it("mints token + POSTs /days/{n}/regenerate with hint body; returns {job_id, status_url}", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce(
      _jsonResponse({ mcp_token: "jwt-regen", expires_at: "2026-09-03T00:00:00Z" }),
    );
    fetchMock.mockResolvedValueOnce(
      _jsonResponse(
        {
          job_id: "regen-job-xyz",
          status_url: "/trips/trip-1/plan/status",
        },
        202,
      ),
    );
    global.fetch = fetchMock as unknown as typeof fetch;

    const { regenerateDayAction } = await import("@/lib/actions");
    const result = await regenerateDayAction({
      userId: "user-abc",
      tripId: "trip-1",
      dayNumber: 2,
      hint: "more food, less hiking",
    });

    expect(result.job_id).toBe("regen-job-xyz");
    expect(result.status_url).toBe("/trips/trip-1/plan/status");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe("http://test-backend/trips/trip-1/days/2/regenerate");
    expect(init?.method).toBe("POST");
    expect((init?.headers as Record<string, string>)["x-tc-token"]).toBe("jwt-regen");
    expect(JSON.parse(init?.body as string)).toEqual({ hint: "more food, less hiking" });
  });

  it("omits hint from body when not provided (empty submit)", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce(_jsonResponse({ mcp_token: "jwt", expires_at: "x" }));
    fetchMock.mockResolvedValueOnce(_jsonResponse({ job_id: "j", status_url: "/x" }, 202));
    global.fetch = fetchMock as unknown as typeof fetch;

    const { regenerateDayAction } = await import("@/lib/actions");
    await regenerateDayAction({
      userId: "user-abc",
      tripId: "trip-1",
      dayNumber: 1,
    });

    const [, init] = fetchMock.mock.calls[1];
    const body = JSON.parse(init?.body as string);
    // hint absent — backend accepts empty body OR body without the field.
    expect(body).not.toHaveProperty("hint");
  });

  it("throws BackendError on 409 (active job in flight)", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce(_jsonResponse({ mcp_token: "jwt", expires_at: "x" }));
    fetchMock.mockResolvedValueOnce(new Response("a refinement job is in flight", { status: 409 }));
    global.fetch = fetchMock as unknown as typeof fetch;

    const { regenerateDayAction } = await import("@/lib/actions");
    await expect(
      regenerateDayAction({
        userId: "user-abc",
        tripId: "trip-1",
        dayNumber: 2,
      }),
    ).rejects.toThrow(/409/);
  });
});
