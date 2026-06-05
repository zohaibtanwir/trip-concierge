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
      <body>{children}</body>
    </html>
  );
}
