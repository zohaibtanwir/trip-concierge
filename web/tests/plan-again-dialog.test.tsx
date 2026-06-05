/**
 * <PlanAgainDialog /> test (slice 4.3).
 *
 * Behavior pinned:
 * - Renders a "Plan again" trigger button (rendered by the parent on
 *   failed state — the component itself doesn't gate; the parent does).
 * - Clicking the trigger opens the Dialog with confirm + cancel buttons.
 * - Clicking confirm invokes the passed planAgainAction with tripId.
 * - Q9 decision: failed-only is enforced by the PARENT (detail page),
 *   not this component. PlanAgainDialog is reusable from any failed
 *   surface.
 *
 * Server Action mocked — the actual planAgainAction in web/lib/actions.ts
 * is exercised by integration. Here we verify the wiring: dialog opens,
 * confirm dispatches the action with the right tripId.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => cleanup());

describe("<PlanAgainDialog />", () => {
  it("renders the trigger button", async () => {
    const { PlanAgainDialog } = await import("@/components/plan-again-dialog");
    const action = vi.fn();
    render(<PlanAgainDialog tripId="trip-1" action={action} />);
    expect(screen.getByRole("button", { name: /plan again/i })).toBeDefined();
  });

  it("opens the confirm dialog when the trigger is clicked", async () => {
    const { PlanAgainDialog } = await import("@/components/plan-again-dialog");
    const action = vi.fn();
    render(<PlanAgainDialog tripId="trip-1" action={action} />);

    fireEvent.click(screen.getByRole("button", { name: /plan again/i }));
    // The confirm text inside the Dialog body — loose copy match.
    expect(screen.getByText(/start a new plan|replan|confirm/i)).toBeDefined();
  });

  it("dispatches the action with tripId when confirm is clicked", async () => {
    const { PlanAgainDialog } = await import("@/components/plan-again-dialog");
    const action = vi.fn();
    render(<PlanAgainDialog tripId="trip-1" action={action} />);

    fireEvent.click(screen.getByRole("button", { name: /plan again/i }));
    // The dialog's confirm button has its own label (e.g., "Replan now" or
    // "Yes, plan again"). Find it by role + a regex that matches both.
    const confirmBtn = screen.getByRole("button", {
      name: /yes|confirm|replan now|plan now/i,
    });
    fireEvent.click(confirmBtn);

    expect(action).toHaveBeenCalledTimes(1);
    expect(action).toHaveBeenCalledWith("trip-1");
  });
});
