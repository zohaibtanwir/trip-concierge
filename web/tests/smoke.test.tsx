import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// Slice 4.5c: app/page.tsx now composes <Header /> + <LandingPage />,
// both async RSCs. vitest can't await nested RSC children when rendering
// the page directly. Mock both to no-ops; their surfaces are covered by
// tests/header.test.tsx and tests/landing-page.test.tsx respectively.
vi.mock("@/auth", () => ({
  auth: vi.fn(async () => null),
}));
vi.mock("@/components/header", () => ({
  Header: () => null,
}));
vi.mock("@/components/landing-page", () => ({
  LandingPage: () => <h1>Trip Concierge</h1>,
}));

describe("home page", () => {
  it("composes <Header /> and <LandingPage /> at the page level", async () => {
    // Smoke test for the page wrapper itself — ensures the composition
    // doesn't throw and renders something. Header + LandingPage have
    // their own component-level tests for the actual surface.
    const Page = (await import("../app/page")).default;
    render(await Page());
    expect(screen.getByRole("heading", { level: 1 })).toBeDefined();
  });
});
