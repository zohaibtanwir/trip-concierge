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
