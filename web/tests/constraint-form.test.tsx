/**
 * <ConstraintForm /> unit tests (slice 4.5 / z9o).
 *
 * Pure form component — manages local state for 4 control sections
 * (dietary multi-select, mobility radio, accessibility toggle, no-go
 * list) and emits the user's selections on submit via an onSubmit
 * prop. Parent (ConstraintPanel) wires onSubmit to addConstraintAction.
 *
 * 4 tests cover the state transitions that matter:
 *   - dietary chip click toggles selection (multi-select state)
 *   - mobility radio click changes the single selected option
 *   - accessibility toggle flips on/off
 *   - no-go input + add button maintains list; remove drops entry
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => cleanup());

describe("<ConstraintForm />", () => {
  it("dietary multi-select toggles state on chip click", async () => {
    const onSubmit = vi.fn();
    const { ConstraintForm } = await import("@/components/constraint-form");
    render(<ConstraintForm onSubmit={onSubmit} />);

    const vegChip = screen.getByRole("button", { name: /vegetarian/i });
    fireEvent.click(vegChip);
    // aria-pressed=true after click; aria-pressed=false after second click.
    expect(vegChip.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(vegChip);
    expect(vegChip.getAttribute("aria-pressed")).toBe("false");
  });

  it("mobility radio changes selection (single-value semantics)", async () => {
    const onSubmit = vi.fn();
    const { ConstraintForm } = await import("@/components/constraint-form");
    render(<ConstraintForm onSubmit={onSubmit} />);

    const noStairs = screen.getByLabelText(/no stairs/i);
    fireEvent.click(noStairs);
    expect((noStairs as HTMLInputElement).checked).toBe(true);

    const walkingDistance = screen.getByLabelText(/walking distance/i);
    fireEvent.click(walkingDistance);
    expect((walkingDistance as HTMLInputElement).checked).toBe(true);
    // Radios are mutually exclusive — previous selection cleared.
    expect((noStairs as HTMLInputElement).checked).toBe(false);
  });

  it("accessibility toggle flips on/off", async () => {
    const onSubmit = vi.fn();
    const { ConstraintForm } = await import("@/components/constraint-form");
    render(<ConstraintForm onSubmit={onSubmit} />);

    const toggle = screen.getByRole("checkbox", { name: /accessibility/i });
    expect((toggle as HTMLInputElement).checked).toBe(false);
    fireEvent.click(toggle);
    expect((toggle as HTMLInputElement).checked).toBe(true);
    fireEvent.click(toggle);
    expect((toggle as HTMLInputElement).checked).toBe(false);
  });

  it("no-go input + add maintains the list; remove drops entry", async () => {
    const onSubmit = vi.fn();
    const { ConstraintForm } = await import("@/components/constraint-form");
    render(<ConstraintForm onSubmit={onSubmit} />);

    // Use the placeholder text — unique to the input element. The
    // legend "No-go list" and the add button's aria-label "Add no-go
    // entry" both also match aria-label-based queries; placeholder is
    // the only fully-disambiguating selector.
    const input = screen.getByPlaceholderText(/loud bars/i) as HTMLInputElement;
    const addBtn = screen.getByRole("button", { name: /add no.?go/i });

    fireEvent.change(input, { target: { value: "loud bars" } });
    fireEvent.click(addBtn);
    expect(screen.getByText(/loud bars/i)).toBeDefined();
    expect(input.value).toBe(""); // cleared after add

    fireEvent.change(input, { target: { value: "crowded markets" } });
    fireEvent.click(addBtn);
    expect(screen.getByText(/crowded markets/i)).toBeDefined();

    // Each chip has a remove button.
    const removeButtons = screen.getAllByRole("button", { name: /remove/i });
    fireEvent.click(removeButtons[0]);
    expect(screen.queryByText(/loud bars/i)).toBeNull();
    expect(screen.getByText(/crowded markets/i)).toBeDefined();
  });
});
