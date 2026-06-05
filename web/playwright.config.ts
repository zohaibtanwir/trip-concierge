/**
 * Playwright config — slice 4.3 minimal e2e smoke (trip-concierge-d74).
 *
 * Scoped narrowly: covers UNAUTHENTICATED surface only (/, /login). The
 * auth-gated smoke fixture (JWE cookie storageState approach) is tracked
 * as a separate followup ticket for slice 4.4 to consume.
 *
 * Run: pnpm exec playwright test
 * Run against an already-running dev server: BASE_URL=http://localhost:3000 pnpm exec playwright test
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
      use: { browserName: "chromium" },
    },
  ],
});
