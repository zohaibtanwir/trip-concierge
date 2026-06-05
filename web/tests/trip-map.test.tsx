/**
 * <TripMap /> unit tests (slice 4.4 / o9r).
 *
 * Verifies the component's branching logic + props mapping without
 * actually mounting MapLibre (jsdom can't render WebGL anyway).
 * react-map-gl is mocked so we exercise the wrapper code that decides
 * what to pass into the Map component.
 *
 * E2E coverage of actual MapLibre mounting lives in
 * tests/e2e/slice-4.4-map.spec.ts (uses chromium-authed project).
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("react-map-gl/maplibre", () => ({
  Map: vi.fn(({ children, ...props }) => (
    <div data-testid="mock-map" data-props={JSON.stringify(props)}>
      {children}
    </div>
  )),
  Marker: vi.fn(({ children, longitude, latitude }) => (
    <div data-testid="mock-marker" data-lng={longitude} data-lat={latitude}>
      {children}
    </div>
  )),
  Popup: vi.fn(({ children }) => <div data-testid="mock-popup">{children}</div>),
  NavigationControl: vi.fn(() => <div data-testid="mock-navigation-control" />),
  AttributionControl: vi.fn(() => (
    <div data-testid="mock-attribution-control">© OpenFreeMap contributors</div>
  )),
}));

afterEach(() => cleanup());

describe("<TripMap />", () => {
  it("renders the Map component when destination is known", async () => {
    const { TripMap } = await import("@/components/trip-map");
    render(<TripMap destination="Coorg, Karnataka, India" dayCount={3} />);
    expect(screen.getByTestId("mock-map")).toBeDefined();
  });

  it("renders an empty-state placeholder when destination is unknown", async () => {
    const { TripMap } = await import("@/components/trip-map");
    render(<TripMap destination="Atlantis, Lost City" dayCount={3} />);
    expect(screen.queryByTestId("mock-map")).toBeNull();
    expect(screen.getByText(/isn't available yet|not yet available/i)).toBeDefined();
  });

  it("renders the destination pin Marker with looked-up coords", async () => {
    const { TripMap } = await import("@/components/trip-map");
    render(<TripMap destination="Coorg, Karnataka, India" dayCount={3} />);
    const marker = screen.getByTestId("mock-marker");
    // Coorg is roughly 75.32, 12.42.
    expect(Number(marker.getAttribute("data-lng"))).toBeCloseTo(75.32, 1);
    expect(Number(marker.getAttribute("data-lat"))).toBeCloseTo(12.42, 1);
  });

  it("renders the day-count label inside a Popup with pluralized format + display name", async () => {
    const { TripMap } = await import("@/components/trip-map");
    render(<TripMap destination="Coorg, Karnataka, India" dayCount={3} />);
    const popup = screen.getByTestId("mock-popup");
    expect(popup.textContent).toMatch(/3 days in Coorg/i);
  });

  it("singular 'day' for 1-day trips", async () => {
    const { TripMap } = await import("@/components/trip-map");
    render(<TripMap destination="Goa, India" dayCount={1} />);
    const popup = screen.getByTestId("mock-popup");
    expect(popup.textContent).toMatch(/1 day in Goa/i);
  });

  it("renders the AttributionControl per spec §9.12 + OpenFreeMap requirement", async () => {
    const { TripMap } = await import("@/components/trip-map");
    render(<TripMap destination="Coorg, Karnataka, India" dayCount={3} />);
    expect(screen.getByTestId("mock-attribution-control")).toBeDefined();
  });
});
