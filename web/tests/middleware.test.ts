/**
 * Slice 4.1 (mvs) — protected-route redirect.
 *
 * BUILD_PLAN.md §4.1 explicitly requires a middleware test that
 * protected routes redirect. The route-protection logic lives in
 * `lib/auth-handler.ts` (separated from middleware.ts so tests can
 * import it without pulling in `@/auth`, which transitively imports
 * `next/server` and breaks under vitest's jsdom environment).
 *
 * Three properties pinned:
 *   1. Authenticated request to /trips/abc → no redirect.
 *   2. Unauthenticated request to /trips/abc → redirect to
 *      /login?callbackUrl=/trips/abc.
 *   3. Unauthenticated request to / → no redirect (only /trips/* is
 *      matched).
 *
 * The Response.redirect URL is asserted explicitly so a future refactor
 * that changes the callback parameter name (e.g., `redirect=` instead
 * of `callbackUrl=`) breaks the test rather than silently shipping a
 * login URL the post-login redirect handler doesn't recognize.
 */

import { describe, expect, it } from "vitest";

import { handleAuthRequest } from "@/lib/auth-handler";

function makeRequest({
  pathname,
  origin = "https://tripconcierge.app",
  auth = null,
}: {
  pathname: string;
  origin?: string;
  auth?: unknown;
}) {
  return {
    auth,
    nextUrl: { pathname, origin },
  };
}

describe("handleAuthRequest", () => {
  it("returns undefined for an authenticated request to /trips/abc", () => {
    const result = handleAuthRequest(
      makeRequest({ pathname: "/trips/abc", auth: { user: { id: "u-1" } } }),
    );
    expect(result).toBeUndefined();
  });

  it("redirects an unauthenticated request to /trips/abc to /login with callbackUrl", () => {
    const result = handleAuthRequest(makeRequest({ pathname: "/trips/abc" }));

    expect(result).toBeInstanceOf(Response);
    const loginUrl = new URL((result as Response).headers.get("location") ?? "");
    expect(loginUrl.pathname).toBe("/login");
    expect(loginUrl.searchParams.get("callbackUrl")).toBe("/trips/abc");
  });

  it("does not redirect an unauthenticated request to the home page", () => {
    const result = handleAuthRequest(makeRequest({ pathname: "/" }));
    expect(result).toBeUndefined();
  });
});
