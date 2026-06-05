/**
 * shadcn Button smoke test (slice 4.3).
 *
 * Verifies the primitive imports cleanly and renders. Variant API
 * (default, outline) maps to spec §9.8/§9.9.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => {
  cleanup();
});

describe("<Button />", () => {
  it("imports + renders default variant without crashing", async () => {
    const { Button } = await import("@/components/ui/button");
    render(<Button>View itinerary</Button>);
    expect(screen.getByRole("button", { name: /view itinerary/i })).toBeDefined();
  });

  it("renders outline variant", async () => {
    const { Button } = await import("@/components/ui/button");
    render(<Button variant="outline">Refine</Button>);
    const btn = screen.getByRole("button", { name: /refine/i });
    expect(btn).toBeDefined();
    // The variant class is whatever shadcn's CVA emits; we don't pin
    // the exact string (changes across shadcn versions). The smoke is
    // "outline variant doesn't crash + renders the label".
  });
});
