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
