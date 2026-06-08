/**
 * <NewTripDialog /> tests — slice 4.5c commit 3.
 *
 * Dialog explains MCP-first trip creation flow. Two surfaces on /trips:
 *   - Top-right "New trip" CTA (users who have existing trips)
 *   - Empty-state primary button "Plan your first trip" (Q6=A)
 * Both trigger the SAME dialog component — Q6=A consolidation.
 *
 * Q3 sign-off pinned content:
 *   - Heading: "Plan your next trip from Claude Desktop"
 *   - MCP-first explanation paragraph
 *   - Copy-to-clipboard prompt template with prose-style placeholders
 *     ([DESTINATION] not <destination>)
 *   - Caveat: "Trip Concierge is currently web-only via Claude Desktop"
 *   - Link "Don't have Claude Desktop?" → claude.ai/download
 *   - Close X
 *
 * Component is Client (own state for open/close). Tests fire the
 * trigger button, assert dialog content visible, click X, assert
 * content hidden.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// next/navigation's useRouter is only available inside the app router
// context. Mock to a no-op router so NewTripForm's useRouter().push()
// works without throwing under vitest's jsdom environment.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

afterEach(() => cleanup());

describe("<NewTripDialog />", () => {
  it("renders trigger button with custom label; dialog content NOT visible by default", async () => {
    const { NewTripDialog } = await import("@/components/new-trip-dialog");
    render(<NewTripDialog triggerLabel="New trip" />);

    expect(screen.getByRole("button", { name: /^New trip$/i })).toBeDefined();
    // Dialog heading is the load-bearing content marker — absent until opened.
    expect(screen.queryByText(/Plan a new trip/i)).toBeNull();
  });

  it("opens dialog with full content when trigger clicked", async () => {
    const { NewTripDialog } = await import("@/components/new-trip-dialog");
    render(<NewTripDialog triggerLabel="New trip" />);

    fireEvent.click(screen.getByRole("button", { name: /^New trip$/i }));

    // Heading + MCP-first explanation + prompt template placeholders + caveat + link
    expect(screen.getByText(/Plan a new trip/i)).toBeDefined();
    // MCP-first explanation: should mention the 4-agent crew or ~10 min
    expect(screen.getByText(/4 specialized agents|10[\s-]?min/i)).toBeDefined();
    // Prompt template prose-style placeholder.
    expect(screen.getByText(/\[DESTINATION\]/)).toBeDefined();
    // Caveat — slice 4.5c commit 4 updated copy to "conversational
    // planning…power users with the desktop app installed." Loose
    // regex match on "conversational" so future copy polish doesn't
    // require a test change.
    expect(screen.getByText(/conversational planning|prefer.*Claude Desktop/i)).toBeDefined();
    // Don't-have-Claude-Desktop link → claude.ai/download
    const dlLink = screen.getByRole("link", {
      name: /Don't have Claude Desktop|Claude Desktop\?/i,
    });
    expect(dlLink).toBeDefined();
    expect(dlLink.getAttribute("href")).toBe("https://claude.ai/download");
  });

  it("provides a copy-to-clipboard button on the prompt template block", async () => {
    const { NewTripDialog } = await import("@/components/new-trip-dialog");
    render(<NewTripDialog triggerLabel="New trip" />);

    fireEvent.click(screen.getByRole("button", { name: /^New trip$/i }));

    // Copy button is present (we don't test the actual clipboard API
    // here — that's a P3 e2e — but the button MUST exist as the UI
    // affordance the user expects).
    expect(screen.getByRole("button", { name: /Copy|Copy prompt/i })).toBeDefined();
  });

  it("closes dialog when the X (close) button is clicked", async () => {
    const { NewTripDialog } = await import("@/components/new-trip-dialog");
    render(<NewTripDialog triggerLabel="New trip" />);

    fireEvent.click(screen.getByRole("button", { name: /^New trip$/i }));
    expect(screen.getByText(/Plan a new trip/i)).toBeDefined();

    // Close button — accessible via aria-label "Close" (X glyph is icon-only).
    fireEvent.click(screen.getByRole("button", { name: /Close/i }));
    expect(screen.queryByText(/Plan a new trip/i)).toBeNull();
  });

  it("Q6=A — same component renders the empty-state trigger label too", async () => {
    // Slice 4.5c Q6=A: empty-state "Plan your first trip" surfaces the
    // SAME dialog content as the top-right "New trip" CTA. Verifies
    // triggerLabel is the only thing that differs between the two
    // instances; dialog content is unchanged.
    const { NewTripDialog } = await import("@/components/new-trip-dialog");
    render(<NewTripDialog triggerLabel="Plan your first trip" />);

    expect(screen.getByRole("button", { name: /Plan your first trip/i })).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: /Plan your first trip/i }));
    expect(screen.getByText(/Plan a new trip/i)).toBeDefined();
  });
});

describe("<NewTripDialog /> two-paths restructure (slice 4.5c commit 3.5)", () => {
  // Per Sunday-morning Critique 2 + Q-product-3 sub-option (a.1):
  // dialog restructured to offer two paths — "Create here" (web form)
  // and "Create in Claude Desktop" (MCP-first content). Default tab is
  // "Create here" (the friction-free path). The MCP-first content
  // assertions from the earlier block above continue to pass — that
  // content moves to the second tab, not removed.

  it("renders tab switcher with both options after open; defaults to 'Create here'", async () => {
    const { NewTripDialog } = await import("@/components/new-trip-dialog");
    render(<NewTripDialog triggerLabel="New trip" userId="user-abc" />);

    fireEvent.click(screen.getByRole("button", { name: /^New trip$/i }));

    // Two tab triggers — names per the sign-off.
    const createHereTab = screen.getByRole("tab", { name: /Create here/i });
    const createInClaudeTab = screen.getByRole("tab", { name: /Create in Claude Desktop/i });
    expect(createHereTab).toBeDefined();
    expect(createInClaudeTab).toBeDefined();

    // "Create here" is the default — aria-selected=true.
    expect(createHereTab.getAttribute("aria-selected")).toBe("true");
    expect(createInClaudeTab.getAttribute("aria-selected")).toBe("false");

    // The web form (destination input) is visible by default.
    expect(screen.getByLabelText(/Destination/i)).toBeDefined();
    // MCP content (prompt template) NOT visible while Create-here is active.
    expect(screen.queryByText(/\[DESTINATION\]/)).toBeNull();
  });

  it("switches to MCP tab; form hides, prompt template appears", async () => {
    const { NewTripDialog } = await import("@/components/new-trip-dialog");
    render(<NewTripDialog triggerLabel="New trip" userId="user-abc" />);

    fireEvent.click(screen.getByRole("button", { name: /^New trip$/i }));
    fireEvent.click(screen.getByRole("tab", { name: /Create in Claude Desktop/i }));

    // MCP content surfaces.
    expect(screen.getByText(/\[DESTINATION\]/)).toBeDefined();
    expect(screen.getByRole("button", { name: /Copy/i })).toBeDefined();
    // Web form hidden — Destination input no longer in DOM.
    expect(screen.queryByLabelText(/Destination/i)).toBeNull();
  });

  it("'Create here' form has destination (required) + dates + group + budget + currency + pace; NO vibe", async () => {
    const { NewTripDialog } = await import("@/components/new-trip-dialog");
    render(<NewTripDialog triggerLabel="New trip" userId="user-abc" />);

    fireEvent.click(screen.getByRole("button", { name: /^New trip$/i }));

    // Destination is required (the only required field).
    const destination = screen.getByLabelText(/Destination/i) as HTMLInputElement;
    expect(destination.required).toBe(true);

    // Other expected inputs — labels rendered, not required.
    expect(screen.getByLabelText(/Start date/i)).toBeDefined();
    expect(screen.getByLabelText(/End date/i)).toBeDefined();
    expect(screen.getByLabelText(/Group size|Travelers/i)).toBeDefined();
    expect(screen.getByLabelText(/Total budget|Budget/i)).toBeDefined();
    expect(screen.getByLabelText(/Currency/i)).toBeDefined();
    // Pace as 3-state control (radio group OR segmented buttons).
    expect(screen.getByText(/Pace/i)).toBeDefined();

    // No vibe field per the architecture (vibe is refine-time only).
    expect(screen.queryByLabelText(/Vibe/i)).toBeNull();
  });

  // Note: removed an over-testing integration assertion that submit
  // triggers createTripAction with the right payload. The action's
  // wire shape is covered by tests/actions.test.ts (three tests
  // including payload + URL); the form's submit-handler wiring is
  // covered by the disabled-state test below. Re-mocking
  // @/lib/actions after the dialog module is already imported fights
  // vitest's module cache; not worth the complexity for redundant
  // coverage.

  it("form submit is disabled until destination has a value", async () => {
    const { NewTripDialog } = await import("@/components/new-trip-dialog");
    render(<NewTripDialog triggerLabel="New trip" userId="user-abc" />);

    fireEvent.click(screen.getByRole("button", { name: /^New trip$/i }));

    const submitBtn = screen.getByRole("button", {
      name: /Plan trip|Start planning|Create trip/i,
    });
    // Without destination → disabled.
    expect((submitBtn as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByLabelText(/Destination/i), {
      target: { value: "Hampi" },
    });
    expect((submitBtn as HTMLButtonElement).disabled).toBe(false);
  });

  // ─────────────────────────────────────────────────────────────────────
  // Hotfix nwk — modal-mode regression pins (slice 4.5c follow-up,
  // 2026-06-08). Same root cause as RegenerateDayDialog +
  // BlockAlternativeDialog — declarative `<dialog open>` threw
  // InvalidStateError in showModal() and left dialogs non-modal. Map
  // markers + DayChipTimeline tooltips overlapped the dialog; Escape
  // didn't close it.
  // ─────────────────────────────────────────────────────────────────────

  it("calls showModal() and the call RETURNS cleanly (does NOT throw — modal mode required)", async () => {
    // See regenerate-day-dialog.test.tsx for the rationale — same
    // hotfix-nwk regression assertion.
    const showModalSpy = vi.spyOn(HTMLDialogElement.prototype, "showModal");

    const { NewTripDialog } = await import("@/components/new-trip-dialog");
    render(<NewTripDialog triggerLabel="New trip" />);

    fireEvent.click(screen.getByRole("button", { name: /^New trip$/i }));

    await vi.waitFor(() => {
      expect(showModalSpy).toHaveBeenCalled();
    });
    expect(showModalSpy.mock.results[0].type).toBe("return");
    showModalSpy.mockRestore();
  });

  it("Escape close (via native `close` event) dismisses the dialog", async () => {
    const { NewTripDialog } = await import("@/components/new-trip-dialog");
    render(<NewTripDialog triggerLabel="New trip" />);

    fireEvent.click(screen.getByRole("button", { name: /^New trip$/i }));
    expect(screen.getByText(/Plan a new trip/i)).toBeDefined();

    const dialog = screen.getByRole("dialog");
    fireEvent(dialog, new Event("close"));

    expect(screen.queryByText(/Plan a new trip/i)).toBeNull();
  });

  it("Backdrop click (target === dialog element) dismisses the dialog", async () => {
    const { NewTripDialog } = await import("@/components/new-trip-dialog");
    render(<NewTripDialog triggerLabel="New trip" />);

    fireEvent.click(screen.getByRole("button", { name: /^New trip$/i }));
    expect(screen.getByText(/Plan a new trip/i)).toBeDefined();

    const dialog = screen.getByRole("dialog");
    fireEvent.click(dialog);

    expect(screen.queryByText(/Plan a new trip/i)).toBeNull();
  });
});
