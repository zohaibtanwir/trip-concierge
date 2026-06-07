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
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => cleanup());

describe("<NewTripDialog />", () => {
  it("renders trigger button with custom label; dialog content NOT visible by default", async () => {
    const { NewTripDialog } = await import("@/components/new-trip-dialog");
    render(<NewTripDialog triggerLabel="New trip" />);

    expect(screen.getByRole("button", { name: /^New trip$/i })).toBeDefined();
    // Dialog heading is the load-bearing content marker — absent until opened.
    expect(screen.queryByText(/Plan your next trip from Claude Desktop/i)).toBeNull();
  });

  it("opens dialog with full content when trigger clicked", async () => {
    const { NewTripDialog } = await import("@/components/new-trip-dialog");
    render(<NewTripDialog triggerLabel="New trip" />);

    fireEvent.click(screen.getByRole("button", { name: /^New trip$/i }));

    // Heading + MCP-first explanation + prompt template placeholders + caveat + link
    expect(screen.getByText(/Plan your next trip from Claude Desktop/i)).toBeDefined();
    // MCP-first explanation: should mention the 4-agent crew or ~10 min
    expect(screen.getByText(/4 specialized agents|10[\s-]?min/i)).toBeDefined();
    // Prompt template prose-style placeholder.
    expect(screen.getByText(/\[DESTINATION\]/)).toBeDefined();
    // Caveat per Q3 addition.
    expect(screen.getByText(/web-only via Claude Desktop/i)).toBeDefined();
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
    expect(screen.getByText(/Plan your next trip from Claude Desktop/i)).toBeDefined();

    // Close button — accessible via aria-label "Close" (X glyph is icon-only).
    fireEvent.click(screen.getByRole("button", { name: /Close/i }));
    expect(screen.queryByText(/Plan your next trip from Claude Desktop/i)).toBeNull();
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
    expect(screen.getByText(/Plan your next trip from Claude Desktop/i)).toBeDefined();
  });
});
