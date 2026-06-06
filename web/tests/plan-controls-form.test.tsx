/**
 * <PlanControlsForm /> unit tests (slice 4.5b / cdr).
 *
 * Pure form component — manages local state for 2 settings-shaped
 * controls:
 *   - pace: 3-state segmented control (packed / balanced / lazy)
 *     rendered as aria-pressed buttons (per spec §9.14's segmented-
 *     control pattern, mirror of constraint-form's chip aria pattern)
 *   - budget_total: numeric input (currency from props)
 *
 * Emits {pace?, budgetTotal?} on submit via the onSubmit prop, with
 * undefined for fields the user didn't touch. Parent
 * (PlanControlsPanel) wires onSubmit to updateTripSettingsAction.
 *
 * 4 tests cover the state transitions that matter:
 *   - pace segmented control single-select behavior
 *   - budget input accepts numeric value
 *   - submit emits {pace, budgetTotal} when both touched
 *   - submit-disabled / no-emit when neither field touched (matches
 *     backend's at-least-one-of validator — UI prevents the empty
 *     PATCH that backend would 422)
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => cleanup());

describe("<PlanControlsForm />", () => {
  it("pace segmented control selects single value (mutually exclusive)", async () => {
    const onSubmit = vi.fn();
    const { PlanControlsForm } = await import("@/components/plan-controls-form");
    render(
      <PlanControlsForm
        currentPace="balanced"
        currentBudgetTotal={null}
        currency="INR"
        onSubmit={onSubmit}
      />,
    );

    const packedBtn = screen.getByRole("button", { name: /packed/i });
    const balancedBtn = screen.getByRole("button", { name: /balanced/i });
    const lazyBtn = screen.getByRole("button", { name: /lazy/i });

    // Initial state from currentPace prop: balanced is pressed.
    expect(balancedBtn.getAttribute("aria-pressed")).toBe("true");
    expect(packedBtn.getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(packedBtn);
    expect(packedBtn.getAttribute("aria-pressed")).toBe("true");
    expect(balancedBtn.getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(lazyBtn);
    expect(lazyBtn.getAttribute("aria-pressed")).toBe("true");
    expect(packedBtn.getAttribute("aria-pressed")).toBe("false");
  });

  it("budget input accepts numeric value and renders currency label", async () => {
    const onSubmit = vi.fn();
    const { PlanControlsForm } = await import("@/components/plan-controls-form");
    render(
      <PlanControlsForm
        currentPace="balanced"
        currentBudgetTotal={null}
        currency="INR"
        onSubmit={onSubmit}
      />,
    );

    // Currency should appear somewhere near the budget input as a label/prefix.
    expect(screen.getAllByText(/INR/i).length).toBeGreaterThan(0);

    const budgetInput = screen.getByLabelText(/total budget/i) as HTMLInputElement;
    fireEvent.change(budgetInput, { target: { value: "50000" } });
    expect(budgetInput.value).toBe("50000");
  });

  it("submit emits {pace, budgetTotal} when both touched", async () => {
    const onSubmit = vi.fn();
    const { PlanControlsForm } = await import("@/components/plan-controls-form");
    render(
      <PlanControlsForm
        currentPace="balanced"
        currentBudgetTotal={null}
        currency="INR"
        onSubmit={onSubmit}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /packed/i }));
    const budgetInput = screen.getByLabelText(/total budget/i) as HTMLInputElement;
    fireEvent.change(budgetInput, { target: { value: "50000" } });

    const submitBtn = screen.getByRole("button", { name: /update settings and re-?plan/i });
    fireEvent.click(submitBtn);

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const args = onSubmit.mock.calls[0][0];
    expect(args.pace).toBe("packed");
    expect(args.budgetTotal).toBe(50000);
  });

  it("submit is no-op when neither field touched (no PATCH for empty diff)", async () => {
    // Backend's at-least-one-of validator would 422 a fully-empty PATCH.
    // The UI should prevent the round-trip instead of relying on the
    // server to reject. Either: submit button disabled OR onSubmit not
    // called when nothing changed.
    const onSubmit = vi.fn();
    const { PlanControlsForm } = await import("@/components/plan-controls-form");
    render(
      <PlanControlsForm
        currentPace="balanced"
        currentBudgetTotal={null}
        currency="INR"
        onSubmit={onSubmit}
      />,
    );

    const submitBtn = screen.getByRole("button", { name: /update settings and re-?plan/i });
    fireEvent.click(submitBtn);

    expect(onSubmit).not.toHaveBeenCalled();
  });
});
