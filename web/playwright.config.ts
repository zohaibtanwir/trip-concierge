/**
 * Playwright config — slice 4.3 unauthed smoke + slice 4.4 auth-gated
 * fixture (trip-concierge-d74, trip-concierge-p8l).
 *
 * Two projects:
 *   - chromium          (unauthed surface — /login, theme tokens, fonts,
 *                        Material Symbols). Run via `pnpm test:e2e:unauthed`.
 *   - chromium-authed   (storageState from `playwright-auth.json`; covers
 *                        /trips and /trips/[id] surfaces). Run via
 *                        `pnpm test:e2e:auth` which seeds the trip and
 *                        mints the cookie before invoking Playwright.
 *
 * Each project's `testIgnore` keeps the other's specs out of its run so
 * a single `playwright test` invocation without `--project` (which CI
 * uses) executes each file in exactly the right context.
 */

import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3000",
    headless: true,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      testIgnore: /auth-fixture-smoke|slice-4\.4/,
      use: { browserName: "chromium" },
    },
    {
      name: "chromium-authed",
      testMatch: /auth-fixture-smoke|slice-4\.4/,
      use: {
        browserName: "chromium",
        // storageState is minted by web/scripts/mint-playwright-auth.ts.
        // Run `pnpm test:e2e:auth` to seed + mint + execute in one shot.
        storageState: "./playwright-auth.json",
      },
    },
  ],
});
