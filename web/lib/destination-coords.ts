/**
 * Hardcoded destination → coords lookup for v1.0a map centering.
 *
 * Slice 4.4 (trip-concierge-o9r). When backend lat/lng population work
 * lands (trip-concierge-423), this helper becomes a fallback for
 * destinations not yet seeded with per-block coords. For v1.0a it's the
 * primary source of truth: the map renders centered on this point with
 * a single destination pin.
 *
 * Zoom levels are eyeballed from each destination's typical block spread
 * in the existing seed data — Coorg trips spread ~30km so zoom 10 fits;
 * Goa is wider so zoom 9; Hampi/Pondicherry are compact so zoom 11.
 *
 * Keys are substring-matched case-insensitively against the destination
 * string. "Coorg, Karnataka, India" matches "coorg"; "Goa, India"
 * matches "goa". This handles the DB convention of comma-separated
 * full names without needing exact-string keys.
 *
 * displayName is the substring before the first comma — that's the
 * tight chrome the popup renders ("3 days in Coorg", not "3 days in
 * Coorg, Karnataka, India").
 */

export interface DestinationCoords {
  lng: number;
  lat: number;
  zoom: number;
  displayName: string;
}

export const DESTINATION_COORDS: Record<string, DestinationCoords> = {
  coorg: { lng: 75.32, lat: 12.42, zoom: 10, displayName: "Coorg" },
  goa: { lng: 73.95, lat: 15.3, zoom: 9, displayName: "Goa" },
  hampi: { lng: 76.46, lat: 15.34, zoom: 11, displayName: "Hampi" },
  pondicherry: { lng: 79.83, lat: 11.93, zoom: 11, displayName: "Pondicherry" },
};

export function getDestinationCoords(destination: string): DestinationCoords | null {
  const lower = destination.toLowerCase();
  for (const [key, coords] of Object.entries(DESTINATION_COORDS)) {
    if (lower.includes(key)) return coords;
  }
  return null;
}
