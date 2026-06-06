/**
 * <PlanControlsPanel /> responsive wrapper test (slice 4.5b / cdr).
 *
 * Mirror of slice 4.5's <ConstraintPanel /> pattern: forceVariant prop
 * pins each variant in jsdom without simulating real viewport changes.
 * Production callers pass the resolved variant from a useMediaQuery
 * hook (currently inline-only on page — same gap as ConstraintPanel,
 * tracked under trip-concierge-gdm).
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => cleanup());

describe("<PlanControlsPanel />", () => {
  it("renders Sheet variant trigger button when forceVariant='sheet' (mobile)", async () => {
    const { PlanControlsPanel } = await import("@/components/plan-controls-panel");
    render(
      <PlanControlsPanel
        tripId="trip-1"
        userId="user-abc"
        currentPace="balanced"
        currentBudgetTotal={null}
        currency="INR"
        forceVariant="sheet"
      />,
    );
    // Trigger renders without opening the sheet.
    expect(screen.getByRole("button", { name: /plan controls|edit settings/i })).toBeDefined();
  });

  it("renders inline variant content directly when forceVariant='inline' (desktop)", async () => {
    const { PlanControlsPanel } = await import("@/components/plan-controls-panel");
    render(
      <PlanControlsPanel
        tripId="trip-1"
        userId="user-abc"
        currentPace="balanced"
        currentBudgetTotal={null}
        currency="INR"
        forceVariant="inline"
      />,
    );
    // Inline variant exposes both pace section + budget section directly.
    // Use exact-match on the fieldset legends to disambiguate from the
    // helper-text sentence at the bottom of the form (which also contains
    // "pace" and "budget" as words).
    expect(screen.getByText(/^Pace$/)).toBeDefined();
    expect(screen.getByText(/^Total budget$/)).toBeDefined();
  });
});
