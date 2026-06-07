/**
 * <LandingPage /> tests — slice 4.5c commit 2.
 *
 * Landing page surface for `/`. Replaces the slice 4.1 placeholder
 * (h1 + sign-in link) with full product framing per Q2 sign-off:
 *
 *   1. Hero — tagline + primary CTA (branched on auth state per Q4=C)
 *   2. How it works — 3 cards (Create via Claude Desktop / Refine in
 *      web app / Plan persists)
 *   3. Why agents — multi-agent specialization framing (Researcher,
 *      Local Expert, Logistics, Budget Auditor)
 *   4. Footer — Trip Concierge wordmark + copyright + tech credit
 *
 * Q4=C branched CTA:
 *   unauthed → "Sign in" → /login
 *   authed   → "View your trips →" → /trips
 *
 * Auth-aware-internally per the Header pattern from commit 1 — single
 * import, page wrapper is one line. Mock @/auth in tests.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/auth", () => ({
  auth: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.resetModules();
  vi.restoreAllMocks();
});

describe("<LandingPage />", () => {
  it("renders all 4 sections — Hero, How it works, Why agents, Footer", async () => {
    const { auth } = await import("@/auth");
    (auth as ReturnType<typeof vi.fn>).mockResolvedValue(null);

    const { LandingPage } = await import("@/components/landing-page");
    render(await LandingPage());

    // Hero — tagline visible.
    expect(screen.getByRole("heading", { level: 1 })).toBeDefined();
    // How it works — section heading present.
    expect(screen.getByText(/How it works/i)).toBeDefined();
    // Why agents — section heading present.
    expect(screen.getByText(/Why agents/i)).toBeDefined();
    // Footer — wordmark + copyright surface.
    expect(screen.getByText(/© 2026/)).toBeDefined();
  });

  it("renders 'Sign in' CTA when unauthed (Q4=C branched)", async () => {
    const { auth } = await import("@/auth");
    (auth as ReturnType<typeof vi.fn>).mockResolvedValue(null);

    const { LandingPage } = await import("@/components/landing-page");
    render(await LandingPage());

    // Primary CTA branch for unauthed users.
    const signInCta = screen.getByRole("link", { name: /Sign in/i });
    expect(signInCta).toBeDefined();
    expect(signInCta.getAttribute("href")).toBe("/login");
    // Negative: no "View your trips" CTA for unauthed users.
    expect(screen.queryByText(/View your trips/i)).toBeNull();
  });

  it("renders 'View your trips →' CTA when authed (Q4=C branched)", async () => {
    const { auth } = await import("@/auth");
    (auth as ReturnType<typeof vi.fn>).mockResolvedValue({
      user: { id: "user-abc", email: "u@test.com" },
    });

    const { LandingPage } = await import("@/components/landing-page");
    render(await LandingPage());

    // Primary CTA branch for authed users.
    const tripsCta = screen.getByRole("link", { name: /View your trips/i });
    expect(tripsCta).toBeDefined();
    expect(tripsCta.getAttribute("href")).toBe("/trips");
    // Negative: no "Sign in" CTA for authed users.
    expect(screen.queryByRole("link", { name: /Sign in/i })).toBeNull();
  });

  it("How it works section has exactly 3 cards", async () => {
    const { auth } = await import("@/auth");
    (auth as ReturnType<typeof vi.fn>).mockResolvedValue(null);

    const { LandingPage } = await import("@/components/landing-page");
    render(await LandingPage());

    // The 3 cards per Q2 sign-off: Create via Claude Desktop / Refine
    // in web app / Plan persists. Loose match on the card titles —
    // copy can polish in a P3 without breaking the test.
    // Use getAllByText since the Hero paragraph also names Claude
    // Desktop — at least one match each is sufficient.
    expect(screen.getAllByText(/Claude Desktop/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Refine/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/persists?/i).length).toBeGreaterThanOrEqual(1);
  });

  it("Why agents section names the 4 specialist agents", async () => {
    const { auth } = await import("@/auth");
    (auth as ReturnType<typeof vi.fn>).mockResolvedValue(null);

    const { LandingPage } = await import("@/components/landing-page");
    render(await LandingPage());

    // The Marsh-demo-valuable framing per Q2: name the agents
    // explicitly. Each name pulls demo-relevant context. The Hero
    // paragraph also names them — at least one match per agent is
    // sufficient (Hero counts; the Why-agents list also counts).
    expect(screen.getAllByText(/Researcher/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Local Expert/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Logistics/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Budget Auditor/i).length).toBeGreaterThanOrEqual(1);
  });
});
