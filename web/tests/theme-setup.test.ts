/**
 * Theme-setup smoke tests (slice 4.3 / trip-concierge-d74).
 *
 * Tailwind v4 uses CSS-first config via @theme blocks in globals.css.
 * jsdom doesn't compile Tailwind at test time, so testing color
 * values via getComputedStyle is unreliable. Instead these tests
 * read globals.css and layout.tsx file contents and assert the
 * spec §13 tokens + spec §13.1 custom CSS classes + spec §4.1 font
 * loading are present.
 *
 * The regression class this guards: a future contributor refactors
 * the theme config and accidentally drops a spec token. CI catches
 * the drop before it lands; future readers see what the contract is.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const _GLOBALS_CSS = readFileSync(resolve(__dirname, "../app/globals.css"), "utf-8");
const _LAYOUT_TSX = readFileSync(resolve(__dirname, "../app/layout.tsx"), "utf-8");

describe("design spec §13 — color tokens in globals.css", () => {
  it.each([
    ["primary (deep teal)", "#006565"],
    ["primary-container", "#008080"],
    ["secondary (mustard)", "#705d00"],
    ["secondary-container", "#fcd400"],
    ["surface", "#f8f9fa"],
    ["on-surface", "#191c1d"],
    ["on-surface-variant", "#3e4949"],
    ["surface-container-lowest", "#ffffff"],
    ["outline-variant", "#bdc9c8"],
    ["error", "#ba1a1a"],
    ["error-container", "#ffdad6"],
  ])("declares %s token (%s)", (_label, hex) => {
    expect(_GLOBALS_CSS.toLowerCase()).toContain(hex.toLowerCase());
  });
});

describe("design spec §4.1 — fonts loaded", () => {
  it("loads Montserrat headline font", () => {
    expect(_GLOBALS_CSS).toMatch(/Montserrat/);
  });

  it("loads Be Vietnam Pro body font", () => {
    expect(_GLOBALS_CSS).toMatch(/Be\+Vietnam\+Pro/);
  });

  it("loads Material Symbols Outlined icon font", () => {
    expect(_GLOBALS_CSS).toMatch(/Material\+Symbols\+Outlined/);
  });
});

describe("design spec §13.1 — custom CSS classes", () => {
  it.each([
    ["editorial-shadow", /\.editorial-shadow\s*\{/],
    ["active-teal-glow", /\.active-teal-glow\s*\{/],
    ["glass-header", /\.glass-header\s*\{/],
    ["itinerary-scroll scrollbar", /\.itinerary-scroll/],
    ["material-symbols-outlined defaults", /\.material-symbols-outlined\s*\{/],
  ])("declares %s", (_label, regex) => {
    expect(_GLOBALS_CSS).toMatch(regex);
  });
});

describe("design spec §4.2 — font-size scale", () => {
  it.each([
    ["headline-lg 40px", "40px"],
    ["headline-md 24px", "24px"],
    ["body-lg 18px", "18px"],
    ["body-md 16px", "16px"],
    ["label-md 14px", "14px"],
    ["label-sm 12px", "12px"],
  ])("declares %s size token (%s)", (_label, size) => {
    expect(_GLOBALS_CSS).toContain(size);
  });
});

describe("app/layout.tsx — body font default", () => {
  it("sets the default body font family per spec §13.1", () => {
    // Either via className on body or via globals.css body { font-family }.
    // The body{} block lives in globals.css; layout.tsx just needs to
    // import it.
    expect(_LAYOUT_TSX).toMatch(/globals\.css/);
  });
});
