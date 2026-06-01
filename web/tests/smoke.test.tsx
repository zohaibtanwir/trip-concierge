import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// Page now uses auth() — slice 4.1 — so the smoke test mocks @/auth
// to avoid pulling in next/server under vitest's jsdom environment.
vi.mock("@/auth", () => ({
  auth: vi.fn(async () => null),
}));

describe("home page", () => {
  it("renders the Trip Concierge heading and a sign-in link when not signed in", async () => {
    const Page = (await import("../app/page")).default;
    render(await Page());

    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.textContent).toBe("Trip Concierge");

    const signInLink = screen.getByRole("link", { name: /sign in/i });
    expect(signInLink.getAttribute("href")).toBe("/login");
  });
});
