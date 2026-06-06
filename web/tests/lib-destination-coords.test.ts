/**
 * Unit tests for web/lib/destination-coords.ts (slice 4.4 / o9r).
 *
 * Validates the hardcoded city → coords lookup that powers the v1.0a
 * map's destination-centered view. When backend lat/lng work lands
 * (trip-concierge-423), this helper becomes a fallback for unknown
 * destinations; for v1.0a it's the primary source of truth.
 */

import { describe, expect, it } from "vitest";

describe("getDestinationCoords", () => {
  it.each([
    ["Coorg, Karnataka, India", 75.32, 12.42, 10],
    ["Goa, India", 73.95, 15.3, 9],
    ["Hampi, India", 76.46, 15.34, 11],
    ["Pondicherry, India", 79.83, 11.93, 11],
  ])("returns coords for %s", async (destination, expectedLng, expectedLat, expectedZoom) => {
    const { getDestinationCoords } = await import("@/lib/destination-coords");
    const result = getDestinationCoords(destination);
    expect(result).not.toBeNull();
    expect(result?.lng).toBeCloseTo(expectedLng, 2);
    expect(result?.lat).toBeCloseTo(expectedLat, 2);
    expect(result?.zoom).toBe(expectedZoom);
  });

  it("returns null for unknown destination", async () => {
    const { getDestinationCoords } = await import("@/lib/destination-coords");
    expect(getDestinationCoords("Atlantis, Lost City")).toBeNull();
  });

  it("matches via substring (case-insensitive) so destination strings with extra context resolve", async () => {
    const { getDestinationCoords } = await import("@/lib/destination-coords");
    // The DB stores destinations as "Coorg, Karnataka, India" but the
    // lookup key is "Coorg". Substring match avoids needing exact strings.
    expect(getDestinationCoords("coorg")).not.toBeNull();
    expect(getDestinationCoords("COORG, KARNATAKA, INDIA")).not.toBeNull();
  });
});

describe("DESTINATION_COORDS table integrity", () => {
  it("all entries have valid lat ∈ [-90, 90] and lng ∈ [-180, 180]", async () => {
    const { DESTINATION_COORDS } = await import("@/lib/destination-coords");
    for (const [name, coords] of Object.entries(DESTINATION_COORDS)) {
      expect(coords.lat, `${name} lat`).toBeGreaterThanOrEqual(-90);
      expect(coords.lat, `${name} lat`).toBeLessThanOrEqual(90);
      expect(coords.lng, `${name} lng`).toBeGreaterThanOrEqual(-180);
      expect(coords.lng, `${name} lng`).toBeLessThanOrEqual(180);
      expect(coords.zoom, `${name} zoom`).toBeGreaterThanOrEqual(0);
      expect(coords.zoom, `${name} zoom`).toBeLessThanOrEqual(22);
    }
  });
});
