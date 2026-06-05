/**
 * Unit tests for web/lib/backend.ts — the PWA's HTTP boundary to the
 * FastAPI backend (slice 4.2 / trip-concierge-2th).
 *
 * Three helpers, all tested with global.fetch mocked:
 *   - mintMcpToken({ userId })     EXISTING (slice 4.1)
 *   - fetchTripList({ userId })    NEW
 *   - fetchTripDetail({ userId, tripId })  NEW
 *
 * Each helper's contract: mint a fresh x-tc-token per request (per the
 * slice 4.2 design dialogue's Q3 decision — per-request mint avoids
 * session-cache complexity), forward the JWT in `x-tc-token`, parse
 * the response.
 *
 * Error propagation: 5xx throws a descriptive Error; 403 throws an
 * Error whose message names the status so callers can branch on it.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const _ORIG_FETCH = global.fetch;

beforeEach(() => {
  // Reset module env. Each test stubs fetch explicitly.
  vi.stubEnv("BACKEND_URL", "http://test-backend");
  vi.stubEnv("INTERNAL_AUTH_SECRET", "test-internal-secret");
});

afterEach(() => {
  vi.unstubAllEnvs();
  global.fetch = _ORIG_FETCH;
  vi.resetModules();
});

function _mockFetchSequence(
  responses: Array<Response | (() => Promise<Response>)>,
): ReturnType<typeof vi.fn> {
  const fn = vi.fn();
  for (const r of responses) {
    if (typeof r === "function") {
      fn.mockImplementationOnce(r);
    } else {
      fn.mockResolvedValueOnce(r);
    }
  }
  global.fetch = fn as unknown as typeof fetch;
  return fn;
}

function _jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// --- mintMcpToken (existing helper — passes today, kept as canary) ---

describe("mintMcpToken", () => {
  it("POSTs to /internal/auth/mint-mcp-token with the shared secret header", async () => {
    const fetchMock = _mockFetchSequence([
      _jsonResponse({ mcp_token: "mint-jwt", expires_at: "2026-09-03T00:00:00Z" }),
    ]);

    const { mintMcpToken } = await import("@/lib/backend");
    const result = await mintMcpToken({ userId: "user-abc" });

    expect(result.mcp_token).toBe("mint-jwt");
    expect(result.expires_at).toBe("2026-09-03T00:00:00Z");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://test-backend/internal/auth/mint-mcp-token");
    expect(init?.method).toBe("POST");
    expect((init?.headers as Record<string, string>)["X-Internal-Secret"]).toBe(
      "test-internal-secret",
    );
    expect(JSON.parse(init?.body as string)).toEqual({ user_id: "user-abc" });
  });

  it("throws on non-2xx mint response", async () => {
    _mockFetchSequence([new Response("internal error", { status: 500 })]);
    const { mintMcpToken } = await import("@/lib/backend");
    await expect(mintMcpToken({ userId: "user-abc" })).rejects.toThrow(/500/);
  });
});

// --- fetchTripList (NEW — slice 4.2) ---

describe("fetchTripList", () => {
  it("mints a token, GETs /trips with x-tc-token, returns parsed items", async () => {
    const fetchMock = _mockFetchSequence([
      // 1. Mint call
      _jsonResponse({ mcp_token: "jwt-for-list", expires_at: "2026-09-03T00:00:00Z" }),
      // 2. List call
      _jsonResponse({
        items: [
          {
            id: "trip-1",
            destination: "Goa",
            start_date: null,
            end_date: null,
            currency: "INR",
            budget_total: "40000.00",
            state: "succeeded",
            created_at: "2026-06-04T13:48:32Z",
          },
        ],
      }),
    ]);

    const { fetchTripList } = await import("@/lib/backend");
    const items = await fetchTripList({ userId: "user-abc" });

    expect(items).toHaveLength(1);
    expect(items[0].id).toBe("trip-1");
    expect(items[0].state).toBe("succeeded");

    // Verify the two-call sequence.
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [listUrl, listInit] = fetchMock.mock.calls[1];
    expect(listUrl).toBe("http://test-backend/trips");
    expect((listInit?.headers as Record<string, string>)["x-tc-token"]).toBe("jwt-for-list");
  });

  it("throws a descriptive error on backend 5xx", async () => {
    _mockFetchSequence([
      _jsonResponse({ mcp_token: "jwt", expires_at: "x" }),
      new Response("db down", { status: 500 }),
    ]);
    const { fetchTripList } = await import("@/lib/backend");
    await expect(fetchTripList({ userId: "user-abc" })).rejects.toThrow(/500/);
  });

  it("throws on 401 (token rejected by backend)", async () => {
    _mockFetchSequence([
      _jsonResponse({ mcp_token: "jwt", expires_at: "x" }),
      new Response("invalid token", { status: 401 }),
    ]);
    const { fetchTripList } = await import("@/lib/backend");
    await expect(fetchTripList({ userId: "user-abc" })).rejects.toThrow(/401/);
  });
});

// --- fetchTripDetail (NEW — slice 4.2) ---

describe("fetchTripDetail", () => {
  it("mints a token, fetches /full + /plan/status concurrently, returns merged shape", async () => {
    const fetchMock = _mockFetchSequence([
      // 1. Mint call
      _jsonResponse({ mcp_token: "jwt-for-detail", expires_at: "2026-09-03T00:00:00Z" }),
      // 2. /full
      _jsonResponse({
        id: "trip-1",
        user_id: "user-abc",
        status: "draft",
        destination: "Goa",
        start_date: null,
        end_date: null,
        group_size: 2,
        budget_total: "40000.00",
        currency: "INR",
        constraints: {},
        pace: "balanced",
        created_at: "2026-06-04T13:48:32Z",
        updated_at: "2026-06-04T13:48:32Z",
        days: [],
      }),
      // 3. /plan/status
      _jsonResponse({
        state: "done",
        approved: true,
        job_id: "job-xyz",
        kind: "plan",
      }),
    ]);

    const { fetchTripDetail } = await import("@/lib/backend");
    const detail = await fetchTripDetail({ userId: "user-abc", tripId: "trip-1" });

    expect(detail.trip.id).toBe("trip-1");
    expect(detail.trip.destination).toBe("Goa");
    expect(detail.planStatus.state).toBe("done");
    expect(detail.planStatus.approved).toBe(true);

    // Verify three calls total: mint, full, status. Order of full and
    // status can vary because they fire concurrently via Promise.all.
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const callUrls = fetchMock.mock.calls.map((c) => c[0]);
    expect(callUrls[0]).toBe("http://test-backend/internal/auth/mint-mcp-token");
    expect(callUrls.slice(1).sort()).toEqual([
      "http://test-backend/trips/trip-1/full",
      "http://test-backend/trips/trip-1/plan/status",
    ]);

    // Both backend calls must carry the freshly-minted token.
    for (const call of fetchMock.mock.calls.slice(1)) {
      const headers = call[1]?.headers as Record<string, string>;
      expect(headers["x-tc-token"]).toBe("jwt-for-detail");
    }
  });

  it("throws on 403 (ownership mismatch)", async () => {
    _mockFetchSequence([
      _jsonResponse({ mcp_token: "jwt", expires_at: "x" }),
      new Response("forbidden", { status: 403 }),
      new Response("forbidden", { status: 403 }),
    ]);
    const { fetchTripDetail } = await import("@/lib/backend");
    await expect(fetchTripDetail({ userId: "user-abc", tripId: "trip-1" })).rejects.toThrow(/403/);
  });

  it("synthesizes planning state when /plan/status 404 and active-job present", async () => {
    // Slice 4.2 tightening — pins the active-job overlay on the 404
    // path. Sequence: mint → /full 200 + /plan/status 404 (Promise.all
    // pair) → /internal/trips/{id}/active-job returns {active: true}
    // → synthesized PlanStatus(state='running').
    const fetchMock = _mockFetchSequence([
      _jsonResponse({ mcp_token: "jwt", expires_at: "x" }),
      _jsonResponse({
        id: "trip-1",
        user_id: "user-abc",
        status: "draft",
        destination: "Coorg",
        start_date: null,
        end_date: null,
        group_size: 2,
        budget_total: null,
        currency: "INR",
        constraints: {},
        pace: "balanced",
        created_at: "2026-06-05T05:00:00Z",
        updated_at: "2026-06-05T05:00:00Z",
        days: [],
      }),
      new Response("no jobrun yet", { status: 404 }),
      _jsonResponse({ active: true }),
    ]);

    const { fetchTripDetail } = await import("@/lib/backend");
    const detail = await fetchTripDetail({ userId: "user-abc", tripId: "trip-1" });

    expect(detail.planStatus.state).toBe("running");
    expect(detail.trip.id).toBe("trip-1");

    // Four total calls: mint, /full, /plan/status, /internal/active-job.
    expect(fetchMock).toHaveBeenCalledTimes(4);
    const activeJobCall = fetchMock.mock.calls[3];
    expect(activeJobCall[0]).toBe("http://test-backend/internal/trips/trip-1/active-job");
    expect((activeJobCall[1]?.headers as Record<string, string>)["X-Internal-Secret"]).toBe(
      "test-internal-secret",
    );
  });

  it("synthesizes no_job state when /plan/status 404 and active-job absent", async () => {
    _mockFetchSequence([
      _jsonResponse({ mcp_token: "jwt", expires_at: "x" }),
      _jsonResponse({
        id: "trip-1",
        user_id: "user-abc",
        status: "draft",
        destination: "Coorg",
        start_date: null,
        end_date: null,
        group_size: 2,
        budget_total: null,
        currency: "INR",
        constraints: {},
        pace: "balanced",
        created_at: "2026-06-05T05:00:00Z",
        updated_at: "2026-06-05T05:00:00Z",
        days: [],
      }),
      new Response("no jobrun yet", { status: 404 }),
      _jsonResponse({ active: false }),
    ]);

    const { fetchTripDetail } = await import("@/lib/backend");
    const detail = await fetchTripDetail({ userId: "user-abc", tripId: "trip-1" });

    expect(detail.planStatus.state).toBe("no_job");
  });
});
