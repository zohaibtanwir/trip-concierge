/**
 * <BlockAlternativeDialog /> tests — slice 4.6 commit 3.
 *
 * Block-scoped swap trigger surface. Per Q3 sign-off (option B):
 *   - "Swap this" button on block → modal with optional reason
 *     textarea → "Find alternatives" submit → ~90s loading state →
 *     3 alternative cards → user picks one → applyAlternativeAction
 *     fires refine → page redirects to /trips/[id] where slice-4.2's
 *     planning-state UX takes over.
 *
 * 3-state machine — idle (reason + find btn) → loading (~90s spinner +
 * disclosure copy) → showing (3 cards + apply btn each). Tests pin
 * each surface independently so copy polish doesn't break the
 * load-bearing wire behavior.
 *
 * Native <dialog> + showModal mirror of RegenerateDayDialog from
 * commit 2. Client Component; mocks @/lib/actions for both Server
 * Actions (find + apply).
 *
 * Q4=A apply-via-refine semantics: applyAlternativeAction synthesizes
 * a refinement_description naming day + old + alternative venues; the
 * crew handles the swap through the hierarchical refine pipeline.
 * Tests assert applyAlternativeAction is invoked with the correct
 * (tripId, dayNumber, oldVenueName, alternativeVenueName) tuple — the
 * synthesis itself is tested in actions.test.ts.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// next/navigation's useRouter is only available inside the app router
// context — mock to no-op (same pattern as regenerate-day-dialog test).
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

// Mock both Server Actions. Each test reassigns the mock per scenario.
vi.mock("@/lib/actions", () => ({
  findAlternativeAction: vi.fn(),
  applyAlternativeAction: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

const _ALTERNATIVES_FIXTURE = {
  alternatives: [
    {
      venue_name: "Tadiandamol Trek Base",
      type: "activity",
      duration_minutes: 240,
      est_cost: 0,
      currency: "INR",
      source_urls: ["https://example.com/tadiandamol"],
      rationale: "Coorg's highest peak; trek-friendly for couples on a budget.",
    },
    {
      venue_name: "Raja's Seat Sunset Point",
      type: "venue",
      duration_minutes: 60,
      est_cost: 50,
      currency: "INR",
      source_urls: ["https://example.com/rajas-seat"],
      rationale: "Quintessential Madikeri sunset spot; minimal walking.",
    },
    {
      venue_name: "Abbey Falls Trail",
      type: "venue",
      duration_minutes: 90,
      est_cost: 100,
      currency: "INR",
      source_urls: ["https://example.com/abbey-falls"],
      rationale: "Short walk, photographic, near other Madikeri stops.",
    },
  ],
};

describe("<BlockAlternativeDialog />", () => {
  it("renders trigger button; dialog content NOT visible by default", async () => {
    const { BlockAlternativeDialog } = await import("@/components/block-alternative-dialog");
    render(
      <BlockAlternativeDialog
        tripId="trip-1"
        userId="user-abc"
        blockId="block-uuid-1"
        blockVenueName="Tiger Tiger"
        dayNumber={2}
      />,
    );

    // Trigger button — labeled per Q3 ("Swap this" / "Find alternatives" / "Swap").
    expect(screen.getByRole("button", { name: /Swap|Alternative/i })).toBeDefined();
    // Dialog heading absent until opened — load-bearing absence.
    expect(screen.queryByRole("heading", { name: /Find alternatives|Swap/i })).toBeNull();
  });

  it("opens dialog in IDLE state — reason textarea + find-alternatives button", async () => {
    const { BlockAlternativeDialog } = await import("@/components/block-alternative-dialog");
    render(
      <BlockAlternativeDialog
        tripId="trip-1"
        userId="user-abc"
        blockId="block-uuid-1"
        blockVenueName="Tiger Tiger"
        dayNumber={2}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Swap|Alternative/i }));

    // Heading mentions the venue name being swapped (load-bearing — user
    // needs to know which block they're swapping).
    expect(screen.getByText(/Tiger Tiger/)).toBeDefined();
    // Reason textarea is optional (no "required" attribute).
    const reason = screen.getByLabelText(/Reason|Why|optional/i) as HTMLTextAreaElement;
    expect(reason).toBeDefined();
    expect(reason.required).toBe(false);
    // Find-alternatives submit button.
    expect(screen.getByRole("button", { name: /Find alternatives|Find|Search/i })).toBeDefined();
  });

  it("shows ~90s planning-time disclosure in IDLE state", async () => {
    // Per Q3 sign-off: the user must know this takes ~90s BEFORE
    // clicking. Surfacing the wait in the loading state alone is too
    // late — the click commits the wait.
    const { BlockAlternativeDialog } = await import("@/components/block-alternative-dialog");
    render(
      <BlockAlternativeDialog
        tripId="trip-1"
        userId="user-abc"
        blockId="block-uuid-1"
        blockVenueName="Tiger Tiger"
        dayNumber={2}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Swap|Alternative/i }));

    // Loose regex match — copy polish shouldn't break the test.
    expect(screen.getByText(/90 ?s|90 seconds|~1 ?min|up to a minute/i)).toBeDefined();
  });

  it("transitions IDLE → LOADING when Find alternatives is clicked", async () => {
    // Loading state pins the long-wait UX: spinner copy + the disclosure
    // that the crew is searching. The submit button MUST disable while
    // pending to prevent double-fires (rapid click during 90s wait).
    const { findAlternativeAction } = await import("@/lib/actions");
    // Keep the promise pending so we can assert the loading state.
    let _resolveFind: (v: typeof _ALTERNATIVES_FIXTURE) => void = () => {};
    (findAlternativeAction as ReturnType<typeof vi.fn>).mockImplementationOnce(
      () =>
        new Promise((res) => {
          _resolveFind = res;
        }),
    );

    const { BlockAlternativeDialog } = await import("@/components/block-alternative-dialog");
    render(
      <BlockAlternativeDialog
        tripId="trip-1"
        userId="user-abc"
        blockId="block-uuid-1"
        blockVenueName="Tiger Tiger"
        dayNumber={2}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Swap|Alternative/i }));
    fireEvent.click(screen.getByRole("button", { name: /Find alternatives|Find|Search/i }));

    // Loading state surface — loose regex for the "Searching…" / "Finding…"
    // copy. Both "finding" and "please wait" line render together, so use
    // getAllByText and assert at least one matched.
    await waitFor(() => {
      const matches = screen.getAllByText(/Searching|Finding|crew is|please wait/i);
      expect(matches.length).toBeGreaterThan(0);
    });

    // findAlternativeAction was called with the right tuple.
    expect(findAlternativeAction).toHaveBeenCalledWith(
      expect.objectContaining({
        userId: "user-abc",
        tripId: "trip-1",
        blockId: "block-uuid-1",
      }),
    );

    // Resolve so the component doesn't sit pending after the test exits.
    _resolveFind(_ALTERNATIVES_FIXTURE);
  });

  it("transitions LOADING → SHOWING and renders 3 alternative cards with rationale", async () => {
    // Showing state surfaces all 3 ranked alternatives. Each card must
    // include venue_name + rationale so the user can make an informed
    // pick. Apply button per card (Q3-impl: one apply CTA per card,
    // not a radio-then-apply because the latter doubles click count).
    const { findAlternativeAction } = await import("@/lib/actions");
    (findAlternativeAction as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      _ALTERNATIVES_FIXTURE,
    );

    const { BlockAlternativeDialog } = await import("@/components/block-alternative-dialog");
    render(
      <BlockAlternativeDialog
        tripId="trip-1"
        userId="user-abc"
        blockId="block-uuid-1"
        blockVenueName="Tiger Tiger"
        dayNumber={2}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Swap|Alternative/i }));
    fireEvent.click(screen.getByRole("button", { name: /Find alternatives|Find|Search/i }));

    // Wait for the 3 alternative cards to render.
    await waitFor(() => {
      expect(screen.getByText(/Tadiandamol Trek Base/)).toBeDefined();
    });
    expect(screen.getByText(/Raja's Seat Sunset Point/)).toBeDefined();
    expect(screen.getByText(/Abbey Falls Trail/)).toBeDefined();
    // Rationale snippet from at least one card (load-bearing for user
    // decision-making — without rationale, the cards are just names).
    expect(screen.getByText(/Coorg's highest peak/)).toBeDefined();
    // Per-card apply CTA — at least 3 apply buttons rendered.
    const applyBtns = screen.getAllByRole("button", { name: /Apply|Use this|Swap to/i });
    expect(applyBtns.length).toBeGreaterThanOrEqual(3);
  });

  it("clicking Apply on a card transitions SHOWING → CONFIRMING (does NOT fire applyAlternativeAction directly)", async () => {
    // Slice 4.6 commit 4 — Q-impl-c3c confirm-step polish. Apply on a
    // card no longer enqueues refine directly; it transitions to the
    // CONFIRMING surface where the user reviews + confirms the ~10
    // min re-plan commitment.
    const { findAlternativeAction, applyAlternativeAction } = await import("@/lib/actions");
    (findAlternativeAction as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      _ALTERNATIVES_FIXTURE,
    );

    const { BlockAlternativeDialog } = await import("@/components/block-alternative-dialog");
    render(
      <BlockAlternativeDialog
        tripId="trip-1"
        userId="user-abc"
        blockId="block-uuid-1"
        blockVenueName="Tiger Tiger"
        dayNumber={2}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Swap|Alternative/i }));
    fireEvent.click(screen.getByRole("button", { name: /Find alternatives|Find|Search/i }));

    await waitFor(() => {
      expect(screen.getByText(/Tadiandamol Trek Base/)).toBeDefined();
    });

    // Pick the FIRST alternative.
    const applyBtns = screen.getAllByRole("button", { name: /Apply|Use this|Swap to/i });
    fireEvent.click(applyBtns[0]);

    // CONFIRMING surface: shows ~10 min disclosure + Confirm + Back-to-options.
    await waitFor(() => {
      expect(screen.getByText(/10 ?min|10 minute|~10/i)).toBeDefined();
    });
    expect(screen.getByRole("button", { name: /Confirm|Yes|Start re-plan/i })).toBeDefined();
    expect(
      screen.getByRole("button", { name: /Back to options|Pick another|Cancel and pick/i }),
    ).toBeDefined();

    // CRITICAL: applyAlternativeAction was NOT fired yet. The user
    // must click Confirm to commit; just picking an alternative is
    // intentional preview.
    expect(applyAlternativeAction).not.toHaveBeenCalled();
  });

  it("CONFIRMING → SHOWING via Back-to-options preserves alternatives (no refetch)", async () => {
    // Q-impl-c4b sign-off (option A): the alternatives array is
    // preserved when the user backs out. Re-running the 90s find is
    // a bad UX; cached state lives in the dialog.
    const { findAlternativeAction } = await import("@/lib/actions");
    (findAlternativeAction as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      _ALTERNATIVES_FIXTURE,
    );

    const { BlockAlternativeDialog } = await import("@/components/block-alternative-dialog");
    render(
      <BlockAlternativeDialog
        tripId="trip-1"
        userId="user-abc"
        blockId="block-uuid-1"
        blockVenueName="Tiger Tiger"
        dayNumber={2}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Swap|Alternative/i }));
    fireEvent.click(screen.getByRole("button", { name: /Find alternatives|Find|Search/i }));

    await waitFor(() => {
      expect(screen.getByText(/Tadiandamol Trek Base/)).toBeDefined();
    });

    // Pick first → CONFIRMING.
    fireEvent.click(screen.getAllByRole("button", { name: /Apply|Use this|Swap to/i })[0]);
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Back to options|Pick another|Cancel and pick/i }),
      ).toBeDefined();
    });

    // Back to options.
    fireEvent.click(
      screen.getByRole("button", { name: /Back to options|Pick another|Cancel and pick/i }),
    );

    // SHOWING surface restored — all 3 cards still rendered.
    expect(screen.getByText(/Tadiandamol Trek Base/)).toBeDefined();
    expect(screen.getByText(/Raja's Seat Sunset Point/)).toBeDefined();
    expect(screen.getByText(/Abbey Falls Trail/)).toBeDefined();

    // CRITICAL: findAlternativeAction was called exactly ONCE (no
    // refetch on Back-to-options). The 90s wait is not re-paid.
    expect(findAlternativeAction).toHaveBeenCalledTimes(1);
  });

  it("CONFIRMING → Confirm click fires applyAlternativeAction with the right tuple", async () => {
    // The actual commit point. applyAlternativeAction only fires on
    // explicit Confirm; the synthesis test in actions.test.ts covers
    // the refinement_description shape.
    const { findAlternativeAction, applyAlternativeAction } = await import("@/lib/actions");
    (findAlternativeAction as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      _ALTERNATIVES_FIXTURE,
    );
    (applyAlternativeAction as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      job_id: "refine-job-xyz",
      status_url: "/trips/trip-1/plan/status",
    });

    const { BlockAlternativeDialog } = await import("@/components/block-alternative-dialog");
    render(
      <BlockAlternativeDialog
        tripId="trip-1"
        userId="user-abc"
        blockId="block-uuid-1"
        blockVenueName="Tiger Tiger"
        dayNumber={2}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Swap|Alternative/i }));
    fireEvent.click(screen.getByRole("button", { name: /Find alternatives|Find|Search/i }));

    await waitFor(() => {
      expect(screen.getByText(/Tadiandamol Trek Base/)).toBeDefined();
    });
    fireEvent.click(screen.getAllByRole("button", { name: /Apply|Use this|Swap to/i })[0]);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Confirm|Yes|Start re-plan/i })).toBeDefined();
    });

    // Confirm.
    fireEvent.click(screen.getByRole("button", { name: /Confirm|Yes|Start re-plan/i }));

    await waitFor(() => {
      expect(applyAlternativeAction).toHaveBeenCalledWith(
        expect.objectContaining({
          userId: "user-abc",
          tripId: "trip-1",
          dayNumber: 2,
          oldVenueName: "Tiger Tiger",
          alternativeVenueName: "Tadiandamol Trek Base",
        }),
      );
    });
  });

  it("close button (X) dismisses the dialog from any state", async () => {
    const { BlockAlternativeDialog } = await import("@/components/block-alternative-dialog");
    render(
      <BlockAlternativeDialog
        tripId="trip-1"
        userId="user-abc"
        blockId="block-uuid-1"
        blockVenueName="Tiger Tiger"
        dayNumber={2}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Swap|Alternative/i }));
    // Dialog open — IDLE state visible.
    expect(screen.getByText(/Tiger Tiger/)).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: /Close/i }));
    // After close, the IDLE-state markers are gone.
    expect(screen.queryByText(/Find alternatives/i)).toBeNull();
  });

  it("surfaces a user-facing error if findAlternativeAction rejects (504 timeout)", async () => {
    // 504 propagation: backend's 90s ceiling becomes a user-visible
    // "try again" message. Loose regex on the error copy.
    const { findAlternativeAction } = await import("@/lib/actions");
    (findAlternativeAction as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("findAlternativeAction HTTP 504: timed out"),
    );

    const { BlockAlternativeDialog } = await import("@/components/block-alternative-dialog");
    render(
      <BlockAlternativeDialog
        tripId="trip-1"
        userId="user-abc"
        blockId="block-uuid-1"
        blockVenueName="Tiger Tiger"
        dayNumber={2}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Swap|Alternative/i }));
    fireEvent.click(screen.getByRole("button", { name: /Find alternatives|Find|Search/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeDefined();
    });
    // The error message includes the underlying status / text — loose match.
    expect(screen.getByText(/504|timed out|try again/i)).toBeDefined();
  });

  // ─────────────────────────────────────────────────────────────────────
  // Hotfix nwk — modal-mode regression pins (slice 4.6 follow-up,
  // 2026-06-08). Same root cause as RegenerateDayDialog +
  // NewTripDialog — declarative `<dialog open>` threw InvalidStateError
  // in showModal() and left dialogs non-modal (z-index conflicts with
  // map + DayChipTimeline tooltips; Escape didn't close).
  // ─────────────────────────────────────────────────────────────────────

  it("calls showModal() and the call RETURNS cleanly (does NOT throw — modal mode required)", async () => {
    // See regenerate-day-dialog.test.tsx for the rationale — same
    // hotfix-nwk regression assertion.
    const showModalSpy = vi.spyOn(HTMLDialogElement.prototype, "showModal");

    const { BlockAlternativeDialog } = await import("@/components/block-alternative-dialog");
    render(
      <BlockAlternativeDialog
        tripId="trip-1"
        userId="user-abc"
        blockId="block-uuid-1"
        blockVenueName="Tiger Tiger"
        dayNumber={2}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Swap|Alternative/i }));

    await vi.waitFor(() => {
      expect(showModalSpy).toHaveBeenCalled();
    });
    expect(showModalSpy.mock.results[0].type).toBe("return");
    showModalSpy.mockRestore();
  });

  it("Escape close (via native `close` event) dismisses the dialog", async () => {
    const { BlockAlternativeDialog } = await import("@/components/block-alternative-dialog");
    render(
      <BlockAlternativeDialog
        tripId="trip-1"
        userId="user-abc"
        blockId="block-uuid-1"
        blockVenueName="Tiger Tiger"
        dayNumber={2}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Swap|Alternative/i }));
    expect(screen.getByText(/Tiger Tiger/)).toBeDefined();

    const dialog = screen.getByRole("dialog");
    fireEvent(dialog, new Event("close"));

    expect(screen.queryByText(/Find alternatives for/i)).toBeNull();
  });

  it("Backdrop click (target === dialog element) dismisses the dialog", async () => {
    const { BlockAlternativeDialog } = await import("@/components/block-alternative-dialog");
    render(
      <BlockAlternativeDialog
        tripId="trip-1"
        userId="user-abc"
        blockId="block-uuid-1"
        blockVenueName="Tiger Tiger"
        dayNumber={2}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Swap|Alternative/i }));
    expect(screen.getByText(/Tiger Tiger/)).toBeDefined();

    const dialog = screen.getByRole("dialog");
    fireEvent.click(dialog);

    expect(screen.queryByText(/Find alternatives for/i)).toBeNull();
  });
});
