/**
 * <ConstraintList /> read-only chip rendering (slice 4.5 / z9o).
 *
 * Renders trip.constraints["rules"] (the slice 3.4a-appended list) as
 * chips with per-kind icons. v1.0a chips are read-only — removal
 * requires a DELETE constraint endpoint that doesn't exist yet
 * (deferred to a P3 ticket per slice 4.5 dialogue Q14).
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => cleanup());

describe("<ConstraintList />", () => {
  it("renders one chip per rule, each with a kind label visible", async () => {
    const { ConstraintList } = await import("@/components/constraint-list");
    render(
      <ConstraintList
        rules={[
          { kind: "dietary", value: "vegetarian", raw_text: "I'm vegetarian" },
          { kind: "mobility", value: "no stairs", raw_text: "no stairs please" },
          { kind: "accessibility", value: "wheelchair", raw_text: "wheelchair access" },
        ]}
      />,
    );
    // Each chip surfaces both the kind (as a label/badge) and the value.
    expect(screen.getByText(/vegetarian/i)).toBeDefined();
    expect(screen.getByText(/no stairs/i)).toBeDefined();
    expect(screen.getByText(/wheelchair/i)).toBeDefined();
    // Per-kind icons render via Material Symbols spans (spec §8). Loose
    // assertion: at least one icon element per chip.
    const icons = document.querySelectorAll(".material-symbols-outlined");
    expect(icons.length).toBeGreaterThanOrEqual(3);
  });
});
