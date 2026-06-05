/**
 * shadcn Dialog smoke test (slice 4.3).
 *
 * Used for: (a) Plan-again confirm on failed trips, (b) desktop
 * variant of block expand-on-tap. Radix Dialog primitive underneath.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => {
  cleanup();
});

describe("<Dialog />", () => {
  it("imports + renders trigger without crashing", async () => {
    const { Dialog, DialogTrigger, DialogContent } = await import("@/components/ui/dialog");
    render(
      <Dialog>
        <DialogTrigger>Plan again</DialogTrigger>
        <DialogContent>Confirm replan?</DialogContent>
      </Dialog>,
    );
    expect(screen.getByText(/plan again/i)).toBeDefined();
  });
});
