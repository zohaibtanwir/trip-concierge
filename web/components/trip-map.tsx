/**
 * TripMap — destination-centered MapLibre panel.
 *
 * Slice 4.4 (trip-concierge-o9r) v1.0a foundation:
 *  - Map centered on the trip's destination via the hardcoded
 *    destination-coords lookup
 *  - Single destination pin + popup with "{N} day(s) in {City}"
 *  - OpenFreeMap demo tiles (override via env.MAPLIBRE_TILE_URL;
 *    production decision tracked as trip-concierge-dj0)
 *  - Empty-state placeholder when destination not in the lookup table
 *
 * Per-block pins, route lines, day color-coding, "Today" mode, and
 * tap-pin-to-scroll all defer to v1.0b (trip-concierge-kue) and depend
 * on backend lat/lng population (trip-concierge-423).
 *
 * Spec authority: §9.12 (added in v1.0.1, this slice).
 */

"use client";

// react-map-gl supports both Mapbox and MapLibre. We use the /maplibre
// subpath explicitly to avoid pulling in Mapbox GL JS (different license
// + requires access token).
import maplibregl from "maplibre-gl";
import {
  AttributionControl,
  // Aliased — `Map` shadows the JS built-in.
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  Popup,
} from "react-map-gl/maplibre";

import "maplibre-gl/dist/maplibre-gl.css";

import { getDestinationCoords } from "@/lib/destination-coords";
import { env } from "@/lib/env";

interface TripMapProps {
  destination: string;
  dayCount: number;
}

function _pluralDays(n: number): string {
  return n === 1 ? "1 day" : `${n} days`;
}

export function TripMap({ destination, dayCount }: TripMapProps) {
  const coords = getDestinationCoords(destination);

  if (coords === null) {
    return (
      <div className="rounded-xl border border-dashed border-outline-variant bg-surface-container-lowest p-6 text-center">
        <p className="text-label-md text-on-surface">Map</p>
        <p className="mt-2 text-body-md text-on-surface-variant">
          Map for this destination isn't available yet.
        </p>
      </div>
    );
  }

  const label = `${_pluralDays(dayCount)} in ${coords.displayName}`;

  return (
    <div className="h-[300px] md:h-[400px] rounded-xl overflow-hidden border border-outline-variant">
      <MapLibreMap
        mapLib={maplibregl}
        initialViewState={{
          longitude: coords.lng,
          latitude: coords.lat,
          zoom: coords.zoom,
        }}
        mapStyle={env.MAPLIBRE_TILE_URL}
        attributionControl={false}
        style={{ width: "100%", height: "100%" }}
      >
        <Marker longitude={coords.lng} latitude={coords.lat} color="#006565" />
        <Popup
          longitude={coords.lng}
          latitude={coords.lat}
          closeButton={false}
          closeOnClick={false}
          anchor="bottom"
          offset={28}
        >
          <span className="text-label-md text-on-surface">{label}</span>
        </Popup>
        <NavigationControl position="top-right" showCompass={false} />
        <AttributionControl position="bottom-right" compact={false} />
      </MapLibreMap>
    </div>
  );
}
