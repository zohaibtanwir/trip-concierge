/**
 * <ConstraintPanel /> responsive wrapper test (slice 4.5 / z9o).
 *
 * Mirror of slice 4.3's BlockExpand pattern: forceVariant prop pins
 * each variant in jsdom without simulating real viewport changes.
 * Production callers pass the resolved variant from a useMediaQuery
 * hook.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => cleanup());

describe("<ConstraintPanel />", () => {
  it("renders Sheet variant trigger button when forceVariant='sheet' (mobile)", async () => {
    const { ConstraintPanel } = await import("@/components/constraint-panel");
    render(
      <ConstraintPanel tripId="trip-1" userId="user-abc" existingRules={[]} forceVariant="sheet" />,
    );
    // The trigger button is rendered without opening the sheet.
    expect(screen.getByRole("button", { name: /constraints|edit/i })).toBeDefined();
  });

  it("renders inline variant content directly when forceVariant='inline' (desktop)", async () => {
    const { ConstraintPanel } = await import("@/components/constraint-panel");
    render(
      <ConstraintPanel
        tripId="trip-1"
        userId="user-abc"
        existingRules={[]}
        forceVariant="inline"
      />,
    );
    // The inline variant exposes the form section labels directly
    // (no Sheet/trigger gating).
    expect(screen.getByText(/dietary/i)).toBeDefined();
  });
});
