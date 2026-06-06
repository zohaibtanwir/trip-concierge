/**
 * Auth-fixture smoke (slice 4.4 commit 1 — p8l).
 *
 * Verifies the JWE storageState fixture itself works. If the fixture is
 * broken (e.g. NEXTAUTH_SECRET drift, Auth.js v5 cookie format change),
 * these tests fail loudly rather than every auth-gated downstream test
 * failing with the same root cause.
 *
 * Gated by the `chromium-authed` project in playwright.config.ts, which
 * sets storageState: "./playwright-auth.json". The fixture is minted
 * via `scripts/mint-playwright-auth.ts` (run before this spec via
 * `pnpm run test:e2e:auth`).
 *
 * Expected failure modes when this test is first written + run before
 * commit 1's impl lands:
 *   - playwright-auth.json doesn't exist yet → Playwright throws
 *     ENOENT on storageState load (fixture-not-built failure)
 *   - chromium-authed project doesn't exist in config → Playwright
 *     skips with "No tests found" for the project
 *   - fixture exists but JWE is invalid → middleware redirects /trips
 *     to /login → assertion in test 1 fails
 */

import { expect, test } from "@playwright/test";

test.describe("auth fixture smoke (slice 4.4 — p8l)", () => {
  test("/trips loads without redirect to /login (session cookie accepted)", async ({ page }) => {
    const response = await page.goto("/trips", { waitUntil: "domcontentloaded" });

    // Middleware redirect to /login would surface as a 200 on the
    // /login URL or a 307 chain. Either way the final URL contains
    // /login, not /trips.
    expect(response?.status()).toBeLessThan(400);
    expect(page.url()).toContain("/trips");
    expect(page.url()).not.toContain("/login");
  });

  test("/trips renders 'Your trips' heading (auth() resolved to a real user)", async ({ page }) => {
    await page.goto("/trips", { waitUntil: "networkidle" });

    // The page-level h1 from app/trips/page.tsx renders "Your trips"
    // when session.user.id resolves. If the JWE was minted with a
    // valid sub but the user doesn't exist in the DB, auth() resolves
    // to a session with no user and the page renders the "Sign-in
    // required" fallback instead. This test catches both broken-JWE
    // and missing-seed-user states.
    await expect(page.getByRole("heading", { name: /your trips/i })).toBeVisible();
  });
});
