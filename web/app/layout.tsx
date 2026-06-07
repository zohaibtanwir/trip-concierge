import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trip Concierge",
  description: "Multi-agent AI travel planner.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* Google Fonts loaded here (not via CSS @import) so they don't
         * conflict with Tailwind v4's @import "tailwindcss" expansion
         * ordering. Spec §4.1 + §8 — Montserrat for headlines, Be
         * Vietnam Pro for body, Material Symbols for icons. */}
        <link
          href="https://fonts.googleapis.com/css2?family=Montserrat:wght@600;700&family=Be+Vietnam+Pro:wght@400;500;600&family=Poppins:wght@400;500;600;700&family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        {/*
         * E2E theme sentinels — verify Tailwind v4 tokens compile to
         * expected RGB values + Material Symbols font renders glyphs
         * (not missing-glyph squares) in production builds. Read by
         * web/tests/e2e/slice-4.3-smoke.spec.ts via getComputedStyle and
         * bounding-rect inspection. Visually off-screen at -9999px so
         * production users never see them. Do not remove.
         *
         * Migrated to root layout in slice 4.5c commit 1 — previously
         * lived in /login per slice 4.3. The migration discharges the
         * "configuration correct at writing becomes foot-gun on first
         * reuse" pattern this session has caught twice (playwright
         * regex hardcoded to slice-4.4, step-5b-1 rule named
         * worker.log) and means the sentinels work from any entry
         * route, not just /login.
         */}
        <span
          data-testid="theme-sentinel"
          className="absolute -left-[9999px] bg-primary text-on-primary"
          aria-hidden="true"
        />
        <span
          data-testid="material-symbols-sentinel"
          className="absolute -left-[9999px] material-symbols-outlined"
          aria-hidden="true"
        >
          map
        </span>
        {children}
      </body>
    </html>
  );
}
