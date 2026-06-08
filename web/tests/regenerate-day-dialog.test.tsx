/**
 * <RegenerateDayDialog /> tests — slice 4.6 commit 2.
 *
 * Day-scoped regenerate trigger surface. Per Q2 sign-off (option A):
 *   - Button on Day header → modal with optional hint textarea →
 *     submit → page navigates to /trips/[id] where slice-4.2's
 *     planning-state UX takes over
 *
 * Native <dialog> + showModal pattern mirrors NewTripDialog from
 * slice 4.5c commit 3. Client Component; mocks @/lib/actions for
 * the Server Action.
 *
 * Hint copy per Q2: "make Day 2 chiller / more food / less hiking" —
 * loose-coupled placeholder; empty submit is valid (backend accepts
 * regenerate without hint).
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// next/navigation's useRouter is only available inside the app router
// context — mock to no-op (same pattern as new-trip-dialog test).
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

afterEach(() => cleanup());

describe("<RegenerateDayDialog />", () => {
  it("renders trigger button; dialog content NOT visible by default", async () => {
    const { RegenerateDayDialog } = await import("@/components/regenerate-day-dialog");
    render(<RegenerateDayDialog tripId="trip-1" userId="user-abc" dayNumber={2} />);

    // Trigger button — labeled per Q2 ("Regenerate" or "Regenerate Day").
    expect(screen.getByRole("button", { name: /Regenerate/i })).toBeDefined();
    // Dialog heading absent until opened — load-bearing absence.
    expect(screen.queryByText(/Regenerate Day 2/i)).toBeNull();
  });

  it("opens dialog with heading naming the day number + optional hint textarea", async () => {
    const { RegenerateDayDialog } = await import("@/components/regenerate-day-dialog");
    render(<RegenerateDayDialog tripId="trip-1" userId="user-abc" dayNumber={2} />);

    fireEvent.click(screen.getByRole("button", { name: /Regenerate/i }));

    // Heading names the day explicitly so user knows the scope.
    expect(screen.getByRole("heading", { name: /Regenerate Day 2/i })).toBeDefined();
    // Hint textarea is optional (no "required" attribute).
    const hint = screen.getByLabelText(/Hint|guidance|note/i) as HTMLTextAreaElement;
    expect(hint).toBeDefined();
    expect(hint.required).toBe(false);
    // Submit button — loose match for the verb.
    expect(screen.getByRole("button", { name: /Regenerate Day|Start regen|Begin/i })).toBeDefined();
  });

  it("shows a lock-preservation note + planning-time disclosure", async () => {
    // Per Q8 + Q2 sign-off: dialog copy should explicitly tell the
    // user that locked blocks survive and the crew takes ~3-5 min.
    const { RegenerateDayDialog } = await import("@/components/regenerate-day-dialog");
    render(<RegenerateDayDialog tripId="trip-1" userId="user-abc" dayNumber={2} />);

    fireEvent.click(screen.getByRole("button", { name: /Regenerate/i }));

    // Locked-blocks-preserved disclosure surface — loose regex so copy
    // polish doesn't break the test.
    expect(screen.getByText(/locked|preserve|won't be replaced/i)).toBeDefined();
    // Planning-time disclosure — loose match on min/minute.
    expect(screen.getByText(/3-5|10\s*min|few min/i)).toBeDefined();
  });

  it("close button (X) dismisses the dialog", async () => {
    const { RegenerateDayDialog } = await import("@/components/regenerate-day-dialog");
    render(<RegenerateDayDialog tripId="trip-1" userId="user-abc" dayNumber={2} />);

    fireEvent.click(screen.getByRole("button", { name: /Regenerate/i }));
    expect(screen.getByRole("heading", { name: /Regenerate Day 2/i })).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: /Close/i }));
    expect(screen.queryByRole("heading", { name: /Regenerate Day 2/i })).toBeNull();
  });

  it("submit button is enabled by default — empty hint is a valid submit", async () => {
    // Day regenerate doesn't require any input — hint is optional.
    // Symmetric with the backend's RegenerateRequest schema (hint:
    // str | None = None). Empty submit is a clean "regenerate with
    // no specific guidance" call.
    const { RegenerateDayDialog } = await import("@/components/regenerate-day-dialog");
    render(<RegenerateDayDialog tripId="trip-1" userId="user-abc" dayNumber={2} />);

    fireEvent.click(screen.getByRole("button", { name: /Regenerate/i }));
    const submit = screen.getByRole("button", {
      name: /Regenerate Day|Start regen|Begin/i,
    }) as HTMLButtonElement;
    expect(submit.disabled).toBe(false);
  });
});
