/**
 * <Header /> tests — slice 4.5c commit 1.
 *
 * Header is a React Server Component (async). It reads auth() internally
 * and renders:
 *   - wordmark "Trip Concierge" on the left, linking to /
 *   - right side: "Sign in" link when unauthed
 *              OR profile menu (email + Sign out) when authed
 *
 * Q1 sign-off pinned the auth-aware-internally API: pages drop <Header />
 * with no props, the component reads session itself. Q5b sign-off pinned
 * the wordmark routing to / for both authed and unauthed.
 *
 * Test pattern mirrors trip-detail.test.tsx: vi.mock("@/auth"), render
 * the awaited component, assert on the visible surface.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/auth", () => ({
  auth: vi.fn(),
  signOut: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.resetModules();
  vi.restoreAllMocks();
});

describe("<Header />", () => {
  it("renders the 'Trip Concierge' wordmark linking to /", async () => {
    const { auth } = await import("@/auth");
    (auth as ReturnType<typeof vi.fn>).mockResolvedValue(null);

    const { Header } = await import("@/components/header");
    render(await Header());

    const wordmark = screen.getByRole("link", { name: /Trip Concierge/i });
    expect(wordmark).toBeDefined();
    expect(wordmark.getAttribute("href")).toBe("/");
  });

  it("wordmark routes to / for authed users too (Q5b: 'logo always returns home')", async () => {
    const { auth } = await import("@/auth");
    (auth as ReturnType<typeof vi.fn>).mockResolvedValue({
      user: { id: "user-abc", email: "u@test.com" },
    });

    const { Header } = await import("@/components/header");
    render(await Header());

    const wordmark = screen.getByRole("link", { name: /Trip Concierge/i });
    expect(wordmark.getAttribute("href")).toBe("/");
  });

  it("renders 'Sign in' link when no session", async () => {
    const { auth } = await import("@/auth");
    (auth as ReturnType<typeof vi.fn>).mockResolvedValue(null);

    const { Header } = await import("@/components/header");
    render(await Header());

    const signInLink = screen.getByRole("link", { name: /Sign in/i });
    expect(signInLink).toBeDefined();
    expect(signInLink.getAttribute("href")).toBe("/login");
    // Negative: no profile menu surface for unauthed.
    expect(screen.queryByText(/u@test\.com/)).toBeNull();
  });

  it("renders profile menu with user email when authed", async () => {
    const { auth } = await import("@/auth");
    (auth as ReturnType<typeof vi.fn>).mockResolvedValue({
      user: { id: "user-abc", email: "zohaib@example.com" },
    });

    const { Header } = await import("@/components/header");
    render(await Header());

    // Email shows in the profile menu surface — twice intentionally:
    // once as the <summary> face (menu trigger label) and once inside
    // the dropdown as the read-only "signed in as" display. Both
    // surfaces are visible; the duplication is design, not a bug.
    const emailMatches = screen.getAllByText(/zohaib@example\.com/);
    expect(emailMatches.length).toBeGreaterThanOrEqual(1);
    // Negative: no Sign-in link for authed users.
    expect(screen.queryByRole("link", { name: /Sign in/i })).toBeNull();
  });

  it("profile menu has a Sign out action when authed", async () => {
    const { auth } = await import("@/auth");
    (auth as ReturnType<typeof vi.fn>).mockResolvedValue({
      user: { id: "user-abc", email: "u@test.com" },
    });

    const { Header } = await import("@/components/header");
    render(await Header());

    // Sign out is rendered as a button (form action wires signOut).
    const signOutBtn = screen.getByRole("button", { name: /Sign out/i });
    expect(signOutBtn).toBeDefined();
  });
});
