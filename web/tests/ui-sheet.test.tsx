/**
 * shadcn Sheet smoke test (slice 4.3).
 *
 * Used for mobile block expand-on-tap. side="bottom" is the Trip
 * Concierge default — slides up from bottom for mobile-native feel.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => {
  cleanup();
});

describe("<Sheet />", () => {
  it("imports + renders trigger without crashing", async () => {
    const { Sheet, SheetTrigger, SheetContent } = await import("@/components/ui/sheet");
    render(
      <Sheet>
        <SheetTrigger>Open</SheetTrigger>
        <SheetContent side="bottom">Body content</SheetContent>
      </Sheet>,
    );
    expect(screen.getByText(/open/i)).toBeDefined();
  });
});
