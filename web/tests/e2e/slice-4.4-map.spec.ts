/**
 * Slice 4.4 map smoke (chromium-authed project).
 *
 * Renders /trips/[id] for the seeded Coorg test trip (uuid
 * 22222222-2222-2222-2222-222222222222 from web/scripts/seed-e2e-trip.ts).
 * Verifies the MapLibre map mounts, renders its destination pin, exposes
 * OpenFreeMap attribution, and respects responsive layout.
 *
 * Auth-gated: requires the p8l fixture (chromium-authed project's
 * storageState). Run via `pnpm test:e2e:auth`.
 *
 * Mobile collapse test (375px viewport) verifies the map doesn't stay
 * pinned in the sticky aside on small viewports — the spec §9.2 stacks
 * the right column below the left on <md.
 */

import { expect, test } from "@playwright/test";

const SEED_TRIP_ID = "22222222-2222-2222-2222-222222222222";

test.describe("slice 4.4 map smoke (Coorg seed trip)", () => {
  test("MapLibre canvas mounts without console errors", async ({ page }) => {
    const pageErrors: string[] = [];
    const consoleErrors: string[] = [];
    page.on("pageerror", (err) => pageErrors.push(err.message));
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        const text = msg.text();
        // Filter known Auth.js + Next.js dev noise that isn't a map regression.
        if (/Unexpected end of JSON input|favicon|MetaMask|Failed to load resource/.test(text))
          return;
        consoleErrors.push(text);
      }
    });

    await page.goto(`/trips/${SEED_TRIP_ID}`, { waitUntil: "networkidle" });

    expect(pageErrors).toEqual([]);
    expect(consoleErrors).toEqual([]);

    // MapLibre renders a <canvas> inside its mount node. Wait for it.
    await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible({ timeout: 10000 });
  });

  test("destination pin Marker renders on the map", async ({ page }) => {
    await page.goto(`/trips/${SEED_TRIP_ID}`, { waitUntil: "networkidle" });
    await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible({ timeout: 10000 });

    // Markers are rendered as DOM nodes that overlay the canvas. react-map-gl
    // applies class `maplibregl-marker` to each.
    await expect(page.locator(".maplibregl-marker").first()).toBeVisible({
      timeout: 5000,
    });
  });

  test("OpenFreeMap attribution is visible bottom-right", async ({ page }) => {
    await page.goto(`/trips/${SEED_TRIP_ID}`, { waitUntil: "networkidle" });
    await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible({ timeout: 10000 });

    // MapLibre's AttributionControl renders as `.maplibregl-ctrl-attrib`.
    const attribution = page.locator(".maplibregl-ctrl-attrib");
    await expect(attribution).toBeVisible();
    await expect(attribution).toContainText(/openfreemap|openstreetmap|osm/i);
  });

  test("mobile viewport (375px) — map collapses below day cards in single column", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    await page.goto(`/trips/${SEED_TRIP_ID}`, { waitUntil: "networkidle" });

    // The map should still mount on mobile.
    await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible({ timeout: 10000 });

    // At 375px the aside collapses below the main content (single-column
    // layout). Verify by checking that the aside's bounding box is BELOW
    // the h1 destination header.
    const h1Box = await page.locator("h1").first().boundingBox();
    const asideBox = await page.locator("aside").first().boundingBox();
    expect(h1Box).not.toBeNull();
    expect(asideBox).not.toBeNull();
    expect(asideBox?.y).toBeGreaterThan(h1Box?.y ?? 0);
  });

  test("no map-related pageerror events fire during page load", async ({ page }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (err) => {
      if (/maplibre|map|webgl|tile/i.test(err.message)) {
        pageErrors.push(err.message);
      }
    });

    await page.goto(`/trips/${SEED_TRIP_ID}`, { waitUntil: "networkidle" });
    await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible({ timeout: 10000 });

    expect(pageErrors).toEqual([]);
  });
});
