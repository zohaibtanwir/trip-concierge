/**
 * <BlockLockToggle /> tests — slice 4.6 commit 4.
 *
 * Per Q-impl-c4c sign-off (option A): always-visible lock indicator.
 *   - lock_open material icon when block.locked === false
 *   - lock material icon when block.locked === true
 *   - Single click toggles + fires setBlockLockAction
 *
 * Per Q5 sign-off (optimistic UI): the icon flips IMMEDIATELY on
 * click, before the PATCH completes. If the PATCH rejects, state
 * reverts AND an inline error badge appears next to the icon for 3
 * seconds, then auto-clears. (Q-impl-c4a fallback path — no toast
 * primitive in the project, so we surface inline.)
 *
 * Click target is the icon itself (an icon-button). aria-label names
 * the action that the click WILL take, not the current state:
 *   - locked === false → aria-label="Lock this block"
 *   - locked === true  → aria-label="Unlock this block"
 *
 * Disabled while the action is in flight to prevent double-fires.
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock the Server Action — each test reassigns the mock per scenario.
vi.mock("@/lib/actions", () => ({
  setBlockLockAction: vi.fn(),
}));

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.resetAllMocks();
});

describe("<BlockLockToggle />", () => {
  it("renders lock_open icon when locked is false", async () => {
    const { BlockLockToggle } = await import("@/components/block-lock-toggle");
    render(
      <BlockLockToggle tripId="trip-1" userId="user-abc" blockId="block-1" initialLocked={false} />,
    );

    // Icon-button labels itself with the ACTION the click takes, not
    // the current state — better for screen reader UX.
    const btn = screen.getByRole("button", { name: /Lock this block/i });
    expect(btn).toBeDefined();
    expect(btn.textContent).toMatch(/lock_open/);
    expect(btn.textContent).not.toMatch(/^lock$/);
  });

  it("renders lock icon when locked is true", async () => {
    const { BlockLockToggle } = await import("@/components/block-lock-toggle");
    render(
      <BlockLockToggle tripId="trip-1" userId="user-abc" blockId="block-1" initialLocked={true} />,
    );

    const btn = screen.getByRole("button", { name: /Unlock this block/i });
    expect(btn).toBeDefined();
    // The icon span text content is "lock" — material symbols
    // wrap-text pattern. Match the icon name exactly (no _open suffix).
    expect(btn.textContent).toContain("lock");
    expect(btn.textContent).not.toContain("lock_open");
  });

  it("click optimistically flips the icon AND fires setBlockLockAction with toggled value", async () => {
    // Optimistic UI per Q5: icon flips immediately on click (before
    // the PATCH completes). setBlockLockAction is invoked with the
    // TARGET state (the opposite of current). Use a deferred mock so
    // we can observe the optimistic state.
    const { setBlockLockAction } = await import("@/lib/actions");
    let _resolve: (v: { locked: boolean }) => void = () => {};
    (setBlockLockAction as ReturnType<typeof vi.fn>).mockImplementationOnce(
      () =>
        new Promise((res) => {
          _resolve = res;
        }),
    );

    const { BlockLockToggle } = await import("@/components/block-lock-toggle");
    render(
      <BlockLockToggle tripId="trip-1" userId="user-abc" blockId="block-1" initialLocked={false} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Lock this block/i }));

    // Optimistic flip — aria-label switched to "Unlock" already, even
    // though the promise hasn't resolved.
    expect(screen.getByRole("button", { name: /Unlock this block/i })).toBeDefined();

    // Server Action was called with locked=true (the target).
    expect(setBlockLockAction).toHaveBeenCalledWith({
      userId: "user-abc",
      tripId: "trip-1",
      blockId: "block-1",
      locked: true,
    });

    // Resolve so the component settles.
    await act(async () => {
      _resolve({ locked: true });
    });
  });

  it("on rejection reverts state AND surfaces an inline error badge for 3 seconds", async () => {
    // Q-impl-c4a fallback (B): no toast primitive available — surface
    // failure inline next to the icon. Auto-clear after 3 seconds.
    const { setBlockLockAction } = await import("@/lib/actions");
    (setBlockLockAction as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("setBlockLockAction HTTP 404: block not found"),
    );

    const { BlockLockToggle } = await import("@/components/block-lock-toggle");
    render(
      <BlockLockToggle tripId="trip-1" userId="user-abc" blockId="block-1" initialLocked={false} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Lock this block/i }));

    // After the rejected action settles: icon REVERTS to lock_open
    // (locked=false) AND the inline error badge appears with role="alert".
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeDefined();
    });
    expect(screen.getByRole("button", { name: /Lock this block/i })).toBeDefined();

    // After 3 seconds, the badge auto-clears.
    await act(async () => {
      vi.advanceTimersByTime(3100);
    });
    expect(screen.queryByRole("alert")).toBeNull();
    // Icon still in reverted (locked=false) state.
    expect(screen.getByRole("button", { name: /Lock this block/i })).toBeDefined();
  });

  it("disables the button while the action is in flight (no double-fires)", async () => {
    const { setBlockLockAction } = await import("@/lib/actions");
    let _resolve: (v: { locked: boolean }) => void = () => {};
    (setBlockLockAction as ReturnType<typeof vi.fn>).mockImplementationOnce(
      () =>
        new Promise((res) => {
          _resolve = res;
        }),
    );

    const { BlockLockToggle } = await import("@/components/block-lock-toggle");
    render(
      <BlockLockToggle tripId="trip-1" userId="user-abc" blockId="block-1" initialLocked={false} />,
    );

    const btn = screen.getByRole("button", { name: /Lock this block/i }) as HTMLButtonElement;
    fireEvent.click(btn);

    // Button is disabled while pending — second click while pending
    // is a no-op so setBlockLockAction is only fired ONCE.
    const pendingBtn = screen.getByRole("button", {
      name: /Unlock this block/i,
    }) as HTMLButtonElement;
    expect(pendingBtn.disabled).toBe(true);

    fireEvent.click(pendingBtn);
    expect(setBlockLockAction).toHaveBeenCalledTimes(1);

    await act(async () => {
      _resolve({ locked: true });
    });
  });
});
