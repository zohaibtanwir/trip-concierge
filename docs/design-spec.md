# Trip Concierge — Design Spec

**Version:** 1.0.1
**Status:** Active — authoritative source for visual language across web surfaces.
**Last updated:** 2026-06-05
**Maintainer:** See git blame for current owners.

---

## 0. How to use this document

This spec is the single source of truth for Trip Concierge's visual language. It is read by:

- Engineers implementing new UI components or pages
- Claude Code sessions working on web surfaces (referenced explicitly at slice opener time)
- Future contributors evaluating "does this design decision fit Trip Concierge?"
- Design reviewers checking PRs against established patterns

When adding a new component or page, read this spec first. When deviating from it, justify the deviation in the PR description or open a discussion before merging.

Significant changes to this spec bump the version (1.0 → 2.0). Minor refinements (token value adjustments, copy clarifications) edit in place with a note in the changelog at the bottom.

---

## 1. Identity statement

Trip Concierge is **the intelligent companion that helps you think through a trip**. It is not a booking platform, a marketplace, a luxury service, or a content site. It is a tool that takes "I want to go to Coorg for three days" and produces a thoughtful, researched, refinable itinerary — and provides a surface to view, edit, and act on that itinerary.

The visual language signals:

- **Serious** — this is for real planning, not browsing inspiration
- **Sophisticated** — quality of typography and color signals quality of thinking
- **Calm** — content-dense surfaces deserve restrained chrome
- **Content-respectful** — the trip plan is the product; UI gets out of the way

The visual language explicitly avoids:

- Transactional patterns (book/reserve/checkout)
- Marketplace patterns (browse/discover/recommended-for-you)
- Luxury-status framing (elite/premium/exclusive/member)
- Marketing aesthetics (hero copy, CTAs, social proof)

---

## 2. Provenance

This spec is derived from a Material Design 3-based travel design system (referenced internally as "Voyage Elite") encountered during slice 4.3 design dialogue. The visual system — palette, typography, spacing, component patterns — was adopted with adaptation. The brand framing of the source (luxury concierge service) was dropped.

The four reference HTML files demonstrating the source system are preserved under `docs/design-references/` for visual context. They show the patterns this spec describes; they do not represent Trip Concierge's actual UI.

Trip Concierge owns the resulting aesthetic going forward. Future evolution does not require alignment with the source.

---

## 3. Color system

Implemented as Tailwind theme extensions. All semantic tokens; no raw hex codes in component code.

### 3.1 Primary palette (deep teal)

Used for primary actions, links, focus rings, brand surfaces.

```
primary:                   #006565
on-primary:                #ffffff
primary-container:         #008080
on-primary-container:      #e3fffe
primary-fixed:             #93f2f2
primary-fixed-dim:         #76d6d5
on-primary-fixed:          #002020
on-primary-fixed-variant:  #004f4f
inverse-primary:           #76d6d5
```

### 3.2 Secondary palette (mustard/amber-gold)

Used sparingly for premium accents, status highlights, special-case CTAs. Should not dominate any surface.

```
secondary:                   #705d00
on-secondary:                #ffffff
secondary-container:         #fcd400
on-secondary-container:      #6e5c00
secondary-fixed:             #ffe16d
secondary-fixed-dim:         #e9c400
on-secondary-fixed:          #221b00
on-secondary-fixed-variant:  #544600
```

### 3.3 Tertiary palette (warm neutral gray)

Used for tertiary chrome, disabled states, subtle borders.

```
tertiary:                  #5b5a5a
on-tertiary:               #ffffff
tertiary-container:        #737272
on-tertiary-container:     #fcf8f8
tertiary-fixed:            #e5e2e1
tertiary-fixed-dim:        #c8c6c5
on-tertiary-fixed:         #1c1b1b
on-tertiary-fixed-variant: #474746
```

### 3.4 Surface palette

The surface system carries content. Multiple levels for elevation.

```
surface:                    #f8f9fa  /* page background */
on-surface:                 #191c1d  /* primary text */
on-surface-variant:         #3e4949  /* secondary text */
surface-bright:             #f8f9fa
surface-dim:                #d9dadb
surface-variant:            #e1e3e4
surface-container-lowest:   #ffffff  /* elevated cards */
surface-container-low:      #f3f4f5  /* secondary surfaces */
surface-container:          #edeeef
surface-container-high:     #e7e8e9
surface-container-highest:  #e1e3e4
surface-tint:               #006a6a
inverse-surface:            #2e3132  /* dark blocks in light theme — CTA panels */
inverse-on-surface:         #f0f1f2
background:                 #f8f9fa
on-background:              #191c1d
```

### 3.5 Outline + error

```
outline:             #6e7979
outline-variant:     #bdc9c8
error:               #ba1a1a
on-error:            #ffffff
error-container:     #ffdad6
on-error-container:  #93000a
```

### 3.6 Trip state badges (semantic mapping)

The four trip states (`planning`, `succeeded`, `failed`, `no_job`) map to the palette as follows. This replaces the slate/amber/emerald/rose scheme used in earlier slice work.

| State | Background class | Text class | Label |
|---|---|---|---|
| `planning` | `bg-primary-fixed-dim/20` | `text-on-primary-fixed-variant` | "Planning…" |
| `succeeded` | `bg-primary-container/10` | `text-primary` | "Ready" |
| `failed` | `bg-error-container` | `text-on-error-container` | "Failed" |
| `no_job` | `bg-surface-container-high` | `text-on-surface-variant` | "Not started" |

Existing components using the old palette get refactored when touched. Do not retroactively refactor; let it migrate naturally as surfaces evolve.

---

## 4. Typography

Two font families, both loaded from Google Fonts.

### 4.1 Font families

- **Headlines:** Montserrat (weights 600, 700)
- **Body:** Be Vietnam Pro (weights 400, 500, 600)
- **Fallback:** Poppins (weights 400–700) — also acceptable where Be Vietnam Pro is unavailable

Loaded via:

```html
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@600;700&family=Be+Vietnam+Pro:wght@400;500;600&family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet" />
```

System fallback: `system-ui, -apple-system, sans-serif`.

### 4.2 Type scale

| Token | Size | Line height | Letter spacing | Weight | Use |
|---|---|---|---|---|---|
| `display-lg` | 64px | 1.1 | -0.02em | 700 | Hero copy (rare in-app) |
| `headline-lg` | 40px | 1.2 | -0.01em | 600 | Page titles |
| `headline-lg-mobile` | 32px | 1.2 | — | 600 | Page titles on mobile |
| `headline-md` | 24px | 1.3 | — | 600 | Section headers, card titles |
| `body-lg` | 18px | 1.6 | — | 400 | Intro paragraphs, hero text |
| `body-md` | 16px | 1.5 | — | 400 | Primary body |
| `label-md` | 14px | 1.0 | 0.05em | 600 | UPPERCASE labels, button text |
| `label-sm` | 12px | 1.0 | — | 500 | Metadata, captions |

All sizes implemented as Tailwind `text-*` utilities via theme config.

### 4.3 Voice and copy

**Use:**

- "Your trips" (possessive, personal)
- "Plan your trip" / "Refine your plan" (action-oriented)
- "Day 3 of 5" (clear, factual)
- "View itinerary" / "Open trip" (utilitarian)
- Destination names rendered as content, not chrome

**Avoid:**

- "Elite," "Premium," "Exclusive," "Curated for the discerning…"
- "Membership," "Member benefits," "Inner circle," "VIP"
- "Book now," "Reserve," "Boarding pass" — Trip Concierge doesn't book anything
- "Embark on a journey of discovery" — marketing prose
- "Concierge service" — implies human-staffed service; Trip Concierge is an AI tool
- Stars, ratings, reviews — Trip Concierge isn't a review platform

---

## 5. Spacing

```
unit:            8px   /* base unit; all spacing multiplies this */
gutter:          24px  /* between grid items */
margin-mobile:   16px
margin-tablet:   32px
margin-desktop:  64px
container-max:   1440px
```

Standard page layout:

```html
<main class="max-w-container-max mx-auto px-margin-mobile md:px-margin-tablet lg:px-margin-desktop">
```

Component spacing uses multiples of 8px: 8 / 16 / 24 / 32 / 48 / 64. Trip Concierge content is dense by nature, so the layout stays generously spaced to give content room.

---

## 6. Border radius

```
DEFAULT:  0.25rem   /* 4px  — small inputs, tight chips */
lg:       0.5rem    /* 8px  — buttons, nested cards */
xl:       0.75rem   /* 12px — primary cards, image containers */
full:     9999px    /* badges, pills, avatars */
```

Do not use `rounded-2xl` or larger. Trip Concierge is restrained.

---

## 7. Shadows

Soft, teal-tinted — matches the brand color rather than neutral black.

```css
.editorial-shadow {
  box-shadow: 0px 8px 24px rgba(0, 128, 128, 0.04);
}

.active-teal-glow {
  box-shadow: 0px 8px 24px rgba(0, 128, 128, 0.08);
}
```

Used sparingly. Default cards use `border border-outline-variant` for separation. Reserve shadows for:

- Sticky panels (right column on detail pages)
- Hover states on interactive cards
- Active/selected items in navigation

---

## 8. Iconography

**Material Symbols Outlined** (Google Fonts).

```html
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet" />

<style>
.material-symbols-outlined {
  font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
  vertical-align: middle;
}
</style>
```

- Default: `FILL 0` (outlined)
- Active/selected: `FILL 1` (filled) via inline `style="font-variation-settings: 'FILL' 1;"`
- Size: 24px default, override with Tailwind `text-*` classes for variants

Usage:

```html
<span class="material-symbols-outlined">map</span>
<span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 1;">favorite</span>
```

Do not mix with other icon libraries (Lucide, Phosphor, Heroicons). One icon family across the app.

---

## 9. Component patterns

### 9.1 Sticky glass header

```html
<header class="fixed top-0 left-0 right-0 z-50 glass-header border-b border-outline-variant">
  <nav class="flex justify-between items-center w-full px-margin-desktop max-w-container-max mx-auto h-20">
    <!-- brand + nav links + actions -->
  </nav>
</header>

<style>
.glass-header {
  backdrop-filter: blur(12px);
  background: rgba(255, 255, 255, 0.8);
}
</style>
```

Height: 80px (`h-20`). Active nav item: `text-primary border-b-2 border-primary pb-1`.

### 9.2 Page layout: two-column with sticky sidebar

Used for trip detail pages.

```html
<main class="max-w-container-max mx-auto px-margin-desktop py-12">
  <div class="grid grid-cols-12 gap-gutter items-start">
    <div class="col-span-12 md:col-span-8 space-y-12">
      <!-- primary content -->
    </div>
    <aside class="col-span-12 md:col-span-4 sticky top-28">
      <!-- secondary content (map, summary, actions) -->
    </aside>
  </div>
</main>
```

Sticky top offset (`top-28`) accounts for the fixed header.

### 9.3 Bento card grid

Used for asymmetric content displays (e.g., trip list with featured item).

```html
<div class="grid grid-cols-12 grid-rows-2 gap-gutter h-[800px]">
  <div class="col-span-12 md:col-span-8 row-span-2 ..."> <!-- featured --> </div>
  <div class="col-span-6 md:col-span-4 row-span-1 ..."> <!-- secondary --> </div>
  <div class="col-span-6 md:col-span-4 row-span-1 ..."> <!-- secondary --> </div>
</div>
```

### 9.4 Horizontal day-scroll timeline

For navigating between days of a multi-day trip.

```html
<div class="itinerary-scroll flex overflow-x-auto pb-6 gap-4 snap-x">
  <div class="min-w-[200px] bg-surface-container-lowest p-5 rounded-xl border border-outline-variant snap-start">
    <p class="text-label-sm text-on-surface-variant mb-1">Day 1 • Jul 12</p>
    <h3 class="font-label-md text-on-surface mb-3">Departure</h3>
    <div class="w-full h-1 bg-surface-variant rounded-full overflow-hidden">
      <div class="bg-primary h-full w-full"></div>
    </div>
  </div>
</div>

<style>
.itinerary-scroll::-webkit-scrollbar { height: 6px; }
.itinerary-scroll::-webkit-scrollbar-track { background: #f1f1f1; }
.itinerary-scroll::-webkit-scrollbar-thumb { background: #006565; border-radius: 10px; }
</style>
```

**Active day** (current viewing target):

```html
<div class="min-w-[200px] bg-surface-container-lowest p-5 rounded-xl border-2 border-primary editorial-shadow snap-start relative">
  <div class="absolute -top-3 right-4 bg-primary text-on-primary text-[10px] px-2 py-0.5 rounded-full uppercase font-bold">
    Current
  </div>
  <!-- content -->
</div>
```

**Completed day:** opacity-60 + full progress bar.
**Future day:** default styling + empty progress bar.

### 9.5 Vertical timeline (blocks within a day)

```html
<div class="space-y-6">
  <div class="flex gap-6 group">
    <div class="flex flex-col items-center">
      <div class="w-10 h-10 rounded-full bg-primary-container text-on-primary-container flex items-center justify-center font-bold">
        1
      </div>
      <div class="w-0.5 h-full bg-outline-variant my-2"></div>
    </div>
    <div class="pb-6">
      <div class="flex items-center gap-2 mb-1">
        <span class="material-symbols-outlined text-primary text-lg">restaurant</span>
        <h5 class="font-label-md text-on-surface">Block title</h5>
      </div>
      <p class="font-body-md text-on-surface-variant">Description</p>
      <span class="inline-block mt-2 text-label-sm bg-surface-container-high px-2 py-1 rounded">11:00 – 13:00</span>
    </div>
  </div>
  <!-- more blocks -->
</div>
```

**Current/active block:** circle uses `bg-primary text-on-primary`.
**Connector line for current → next:** `border-dashed border-2` instead of solid.

### 9.6 Card with image header

```html
<div class="bg-surface-container-lowest rounded-xl overflow-hidden border border-outline-variant group hover:active-teal-glow transition-all cursor-pointer">
  <div class="h-48 relative overflow-hidden">
    <img class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700" />
    <div class="absolute top-4 right-4 ...">
      <!-- optional badge -->
    </div>
  </div>
  <div class="p-6">
    <!-- content -->
  </div>
</div>
```

### 9.7 Status badge / pill

```html
<span class="px-3 py-1 rounded-full bg-primary-fixed-dim/20 text-on-primary-fixed-variant font-label-sm text-label-sm">
  Planning…
</span>
```

### 9.8 Primary button

```html
<button class="bg-primary text-on-primary px-6 py-3 rounded-lg font-label-md text-label-md hover:opacity-90 transition-all active:scale-95">
  View itinerary
</button>
```

### 9.9 Secondary button (outlined)

```html
<button class="border-2 border-primary text-primary px-6 py-3 rounded-lg font-label-md text-label-md hover:bg-primary hover:text-on-primary transition-all">
  Refine
</button>
```

### 9.10 Sidebar navigation (account/settings)

```html
<aside class="w-64 flex-shrink-0">
  <h2 class="font-label-md text-label-md text-on-surface-variant uppercase tracking-widest mb-4">Account</h2>
  <nav class="flex flex-col gap-1">
    <a class="flex items-center gap-3 px-4 py-3 rounded-lg bg-primary-container text-on-primary-container active-teal-glow">
      <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 1;">person</span>
      <span class="font-label-md">Personal Info</span>
    </a>
    <a class="flex items-center gap-3 px-4 py-3 rounded-lg text-on-surface-variant hover:bg-surface-container-low">
      <span class="material-symbols-outlined">map</span>
      <span class="font-label-md">My Trips</span>
    </a>
  </nav>
</aside>
```

Active item: filled icon, `bg-primary-container`, `text-on-primary-container`, `active-teal-glow` shadow.

### 9.11 Empty/no-data state

```html
<div class="rounded-xl border border-dashed border-outline-variant p-8 text-center">
  <p class="text-on-surface font-medium">No trips yet.</p>
  <p class="text-sm text-on-surface-variant mt-2">
    Plan your first trip from Claude Desktop, or <a href="/" class="underline">return home</a>.
  </p>
</div>
```

Dashed border (not solid) distinguishes empty state from content card.

### 9.12 Map panel (right rail)

Added in v1.0.1 (slice 4.4). Used on trip detail pages
(`/trips/[id]`). Stacks in the sticky right aside between the day-chip
timeline (§9.4) and the "How this plan was made" panel.

**Placement:** Right column, between DayChipTimeline (above) and
PlanHistoryPanel (below). Visible on succeeded + failed trip states
only — planning state shows the in-progress section in the left
column with no right-rail map.

**Dimensions:** `h-[300px]` on mobile, `md:h-[400px]` on desktop. Full
width within the right aside; rounded-xl per §6 + 1px border-outline-
variant for visual separation.

**No shadow on the panel itself.** TripMap uses `border-outline-
variant` for visual separation, matching the other right-rail
components (DayChipTimeline, PlanHistoryPanel). The right-rail as a
whole is the sticky panel; individual components within it don't
carry independent shadow elevation. This is a deliberate spec choice
per §7 — shadows are reserved for sticky surfaces, not for visual
polish on nested elements.

**Tech choice:** [`react-map-gl`](https://visgl.github.io/react-map-gl/)
(MapLibre subpath) + [`maplibre-gl`](https://maplibre.org/). Imported
explicitly as `react-map-gl/maplibre` to avoid pulling in Mapbox GL JS
(different license, requires access token). Both deps exact-pinned per
CLAUDE.md.

**Tile source:** OpenFreeMap's `liberty` style via env-overridable URL
`MAPLIBRE_TILE_URL` (default
`https://tiles.openfreemap.org/styles/liberty`). Production tile
source decision deferred to `trip-concierge-dj0`.

**Destination pin pattern (v1.0a):**
- Single Marker at the destination's coordinates (color: `#006565` to
  match the spec §3.1 primary).
- Popup anchored bottom of the pin with `closeButton={false}` and
  `closeOnClick={false}` — always-open chrome.
- Popup label format: `{N} day(s) in {City}` where City is the
  substring of `trip.destination` before the first comma.
- NavigationControl at top-right (zoom +/-; compass hidden).
- AttributionControl at bottom-right per OpenFreeMap requirements
  (legal — not optional).

**Empty state:** When the destination doesn't match the hardcoded
lookup table (`web/lib/destination-coords.ts`), render a dashed-border
placeholder card with copy "Map for this destination isn't available
yet." — honest about state without overstating cause.

```tsx
<TripMap destination={trip.destination} dayCount={trip.days.length} />
```

**v1.0b additions (deferred — see §17.11):** per-block pins,
day-filtered visibility, color-coding per day, route lines between
consecutive blocks, "Today" mode, tap-pin-to-scroll itinerary.

---

## 10. Dark mode

**Deferred to Phase 5.** v1.0a ships light mode only.

The Material Design 3 color system has dark-mode tokens defined; the architecture extends cleanly. Tailwind config keeps `darkMode: "class"` for future support. Do not add `dark:` variants to component code yet — they would be untested.

When dark mode is implemented, the inverse tokens already in the palette (`inverse-surface`, `inverse-primary`, `inverse-on-surface`) provide the foundation.

---

## 11. Motion

Restrained. Trip Concierge is a thinking tool, not an expressive app.

| Trigger | Animation |
|---|---|
| Card hover | `transition-all duration-300` + subtle shadow shift or `scale-105` on inner image |
| Image hover (inside card) | `group-hover:scale-105 transition-transform duration-700` |
| Button press | `active:scale-95` |
| Link/nav hover | `transition-colors` |
| Page transitions | Next.js defaults |

Do not use:

- Framer Motion or other animation libraries (v1.0a)
- Bouncy spring physics
- Expressive page transitions
- Animated illustrations
- Auto-playing content (carousels, ticker text)

---

## 12. Things explicitly NOT in scope

This section exists to prevent scope drift during design dialogues. The source design system included these patterns; Trip Concierge does not.

- **Booking/reservation:** search forms, date pickers, guest counts, pricing breakdowns, "Reserve Now" CTAs
- **Membership framing:** Elite tiers, Voyager Status, Inner Circle, Membership badges
- **Marketplace patterns:** featured destinations, recommended-for-you, browse-and-discover
- **Human concierge personification:** named human reps ("Marco Russo, Elite Concierge"). Trip Concierge IS the AI; no separate human persona.
- **Travel documents framing:** boarding passes, vaccination records, passports. Trip Concierge plans, doesn't document.
- **Pricing displays in primary chrome:** "$1,450/night" prominently. Cost data lives inside block details, not on card chrome.
- **Stars/ratings/reviews:** Trip Concierge isn't a review platform.
- **Marketing/conversion patterns:** social proof, urgency banners, limited-time offers.

If a future slice considers adding any of these, surface the conflict with this spec before proceeding.

---

## 13. Implementation: Tailwind config

The full Tailwind config extension for `web/tailwind.config.ts`:

```typescript
import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#006565",
        "on-primary": "#ffffff",
        "primary-container": "#008080",
        "on-primary-container": "#e3fffe",
        "primary-fixed": "#93f2f2",
        "primary-fixed-dim": "#76d6d5",
        "on-primary-fixed": "#002020",
        "on-primary-fixed-variant": "#004f4f",
        "inverse-primary": "#76d6d5",

        secondary: "#705d00",
        "on-secondary": "#ffffff",
        "secondary-container": "#fcd400",
        "on-secondary-container": "#6e5c00",
        "secondary-fixed": "#ffe16d",
        "secondary-fixed-dim": "#e9c400",
        "on-secondary-fixed": "#221b00",
        "on-secondary-fixed-variant": "#544600",

        tertiary: "#5b5a5a",
        "on-tertiary": "#ffffff",
        "tertiary-container": "#737272",
        "on-tertiary-container": "#fcf8f8",
        "tertiary-fixed": "#e5e2e1",
        "tertiary-fixed-dim": "#c8c6c5",
        "on-tertiary-fixed": "#1c1b1b",
        "on-tertiary-fixed-variant": "#474746",

        surface: "#f8f9fa",
        "on-surface": "#191c1d",
        "on-surface-variant": "#3e4949",
        "surface-bright": "#f8f9fa",
        "surface-dim": "#d9dadb",
        "surface-variant": "#e1e3e4",
        "surface-container-lowest": "#ffffff",
        "surface-container-low": "#f3f4f5",
        "surface-container": "#edeeef",
        "surface-container-high": "#e7e8e9",
        "surface-container-highest": "#e1e3e4",
        "surface-tint": "#006a6a",
        "inverse-surface": "#2e3132",
        "inverse-on-surface": "#f0f1f2",
        background: "#f8f9fa",
        "on-background": "#191c1d",

        outline: "#6e7979",
        "outline-variant": "#bdc9c8",
        error: "#ba1a1a",
        "on-error": "#ffffff",
        "error-container": "#ffdad6",
        "on-error-container": "#93000a",
      },
      borderRadius: {
        DEFAULT: "0.25rem",
        lg: "0.5rem",
        xl: "0.75rem",
        full: "9999px",
      },
      spacing: {
        unit: "8px",
        gutter: "24px",
        "margin-mobile": "16px",
        "margin-tablet": "32px",
        "margin-desktop": "64px",
        "container-max": "1440px",
      },
      fontFamily: {
        "headline-lg": ["Montserrat", "sans-serif"],
        "headline-md": ["Montserrat", "sans-serif"],
        "display-lg": ["Montserrat", "sans-serif"],
        "body-md": ["Be Vietnam Pro", "Poppins", "sans-serif"],
        "body-lg": ["Be Vietnam Pro", "Poppins", "sans-serif"],
        "label-md": ["Be Vietnam Pro", "Poppins", "sans-serif"],
        "label-sm": ["Be Vietnam Pro", "Poppins", "sans-serif"],
      },
      fontSize: {
        "display-lg": ["64px", { lineHeight: "1.1", letterSpacing: "-0.02em", fontWeight: "700" }],
        "headline-lg": ["40px", { lineHeight: "1.2", letterSpacing: "-0.01em", fontWeight: "600" }],
        "headline-lg-mobile": ["32px", { lineHeight: "1.2", fontWeight: "600" }],
        "headline-md": ["24px", { lineHeight: "1.3", fontWeight: "600" }],
        "body-lg": ["18px", { lineHeight: "1.6", fontWeight: "400" }],
        "body-md": ["16px", { lineHeight: "1.5", fontWeight: "400" }],
        "label-md": ["14px", { lineHeight: "1", letterSpacing: "0.05em", fontWeight: "600" }],
        "label-sm": ["12px", { lineHeight: "1", fontWeight: "500" }],
      },
    },
  },
  plugins: [],
};

export default config;
```

### 13.1 Global CSS additions

Add to `app/globals.css`:

```css
@import url("https://fonts.googleapis.com/css2?family=Montserrat:wght@600;700&family=Be+Vietnam+Pro:wght@400;500;600&family=Poppins:wght@400;500;600;700&family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap");

body {
  font-family: "Be Vietnam Pro", "Poppins", system-ui, -apple-system, sans-serif;
}

.material-symbols-outlined {
  font-variation-settings: "FILL" 0, "wght" 400, "GRAD" 0, "opsz" 24;
  vertical-align: middle;
}

.editorial-shadow {
  box-shadow: 0px 8px 24px rgba(0, 128, 128, 0.04);
}

.active-teal-glow {
  box-shadow: 0px 8px 24px rgba(0, 128, 128, 0.08);
}

.glass-header {
  backdrop-filter: blur(12px);
  background: rgba(255, 255, 255, 0.8);
}

.itinerary-scroll::-webkit-scrollbar {
  height: 6px;
}

.itinerary-scroll::-webkit-scrollbar-track {
  background: #f1f1f1;
}

.itinerary-scroll::-webkit-scrollbar-thumb {
  background: #006565;
  border-radius: 10px;
}
```

---

## 14. Migration plan

Existing components from slice 4.2 that adopt this spec when next touched:

| Component | Refactor scope | Slice |
|---|---|---|
| `state-badge.tsx` | Replace slate/amber/emerald/rose with palette tokens per §3.6 | 4.3 |
| `trip-list-row.tsx` | Adopt card-with-image-header (§9.6); replace shadows with `active-teal-glow` on hover | 4.3 |
| `trip-day.tsx` | Adopt vertical timeline pattern (§9.5); numbered circles with `bg-primary-container` | 4.3 |
| `trip-block.tsx` | Restructure to flex `gap-6 group`; add Material Symbols icon for venue type | 4.3 |
| `app/trips/page.tsx` | Adopt sticky glass header (§9.1) + page layout (§9.2); replace generic typography | 4.3 |
| `app/trips/[id]/page.tsx` | Adopt two-column layout (§9.2) with sticky right panel placeholder | 4.3 |
| Auth pages (`app/login`) | Adopt typography and palette; not a structural refactor | Phase 5 polish |

Refactor opportunistically. Don't write a dedicated "migrate to new theme" slice — let it migrate as surfaces evolve.

---

## 15. Open questions for v2.0

Items intentionally deferred from v1.0 of this spec, to revisit when Phase 5 polish begins:

- Dark mode token activation
- Mobile-first responsive patterns for the two-column layout (drawer? bottom sheet?)
- Animation language refinement (when does motion add value vs. distract?)
- Icon vocabulary expansion (is Material Symbols sufficient for travel-specific concepts?)
- Accessibility tightening (focus-visible rings across all interactive surfaces, WCAG AA color contrast verification)
- Print stylesheet for itineraries (high-value for travelers)

---

## 16. Visual references

Four HTML files under `docs/design-references/` demonstrate the source patterns:

- `voyage-elite-explore.html` — landing/discovery surface with hero, search, bento featured grid, recommendation cards
- `voyage-elite-itinerary.html` — itinerary detail surface with horizontal day timeline, vertical block list, sticky right-column with map/weather/concierge panels
- `voyage-elite-booking.html` — venue detail with bento image gallery, amenities grid, sticky booking sidebar
- `voyage-elite-profile.html` — account/settings surface with sidebar nav, profile card, saved-content grids

Open these in a browser to see what the patterns in §9 look like in context. They reflect the source system's full brand framing (which Trip Concierge has dropped) — read for visual structure, not for copy or product framing.

---

## 17. v1.1 prep — gaps surfaced during slice 4.3

The following patterns were used during slice 4.3 component design but are not formally defined in v1.0 of this spec. They will land as proper sections in v1.1 (tracked as `trip-concierge-auu`) once two-or-three of them settle through implementation cycles.

### 17.1 Sticky variant of §9.4 day-scroll timeline

When scrolling within a day's block list, the day chip timeline pins to the top. Slice 4.3 implementation (`web/components/day-chip-timeline.tsx`) uses `sticky top-20` + `.glass-header` backdrop blur on the chip bar container. v1.1 to formalize the offset value and the chip transition states (when does a chip transition from "future" → "current" → "completed"?).

### 17.2 Dialog component pattern (shadcn / Radix Dialog)

Introduced in slice 4.3 for: (a) Plan-again confirm flow on failed trips (`web/components/plan-again-dialog.tsx`), (b) desktop variant of block expand-on-tap (`web/components/block-expand.tsx`). v1.1 to define overlay backdrop opacity, max-width per content type, close-button positioning.

### 17.3 Sheet pattern (shadcn / Radix Dialog `side="bottom"`)

Introduced in slice 4.3 for mobile block expand-on-tap (`web/components/block-expand.tsx`). v1.1 to define sheet height (full / half / fit-content), drag-to-dismiss behavior, header treatment.

### 17.4 Block expand-state field list

v1.0a slice 4.3 renders: notes, start_time + duration, est_cost, sources (URLs). Backend block enrichment (`trip-concierge-gco`) adds opening_hours, full_address, photos, why_picked. v1.1 formalizes the expanded-state layout once enrichment lands. Until then, `BlockDetail` ships honest empty-state placeholders.

### 17.5 "How this plan was made" panel (PRD §F8 partial)

Slice 4.3 ships a collapsible panel (`web/components/plan-history-panel.tsx`) that reads `JobRun.agent_summary` and renders one row per agent step with duration. v1.1 to define row icon set, completion-state rendering, expand-step-to-show-reasoning interaction (requires backend enrichment to surface per-step reasoning text).

### 17.6 Swipe gesture states (PRD §F2 deferred)

PRD §F2 specifies swipe-left removes + swipe-right locks. Visual states during swipe (threshold-crossed feedback, snap-back animation, lock-confirmed pulse) are undefined in v1.0. Bundled into `trip-concierge-0hi`. v1.1 lands visual states alongside gesture implementation.

### 17.7 Material Symbol → block type mapping

Slice 4.3 maps block types to Material Symbols inline in `web/components/trip-block.tsx`:

- venue → `location_on`
- meal → `restaurant`
- transit → `directions_car`
- rest → `bed`

v1.1 to define the full mapping table including future block types and icon variation settings (fill/weight) for active vs default.

### 17.8 Plan-again confirm flow

Slice 4.3 wires a Dialog confirm + Server Action POST to `/trips/{id}/plan` on failed trips (`web/components/plan-again-dialog.tsx` + `web/lib/actions.ts`). v1.1 to define the broader pattern: when does a destructive or expensive action require Dialog confirmation vs. inline button?

### 17.9 Tailwind v4 CSS-first config

Spec §13 in v1.0 shows v3-syntax `tailwind.config.ts`. v1.0a project is on Tailwind v4 with CSS-first `@theme` blocks in `app/globals.css`. v1.1 to update §13 with v4 syntax (semantic content unchanged; mechanical syntax migration).

### 17.11 Map panel — pin-less → pinned migration (v1.0a → v1.0b)

§9.12 documents the v1.0a destination-centered map (single pin, no
per-block pins). v1.0b transitions to:

- Per-block pins (depends on `trip-concierge-423` backend lat/lng
  population via crew prompts + geocoding integration)
- Day-filtered pin visibility (depends on `trip-concierge-kue`'s UI
  toggle work)
- Day color-coding when "All days" toggle active
- Route lines between consecutive blocks within a day (depends on
  Directions API integration in `kue`)
- Tap-pin-to-scroll itinerary to that block (state synchronization
  between map and TripDay components)
- "Today" mode (geolocation + current-block computation)

v1.1 of the spec adds these patterns to §9.12 once the v1.0b backend
work lands and the UX settles.

### 17.10 Motion language clarification — CSS-utility animations

§11 states "No Framer Motion or other animation libraries (v1.0a)" — written with JS-based expressive motion libraries in mind. Slice 4.3 ships shadcn primitives that include `tw-animate-css` utilities for Sheet/Dialog enter/exit micro-interactions. These are CSS keyframe animations, not JS expressive motion, and don't violate §11's substance (restrained motion language for a thinking tool).

v1.1 to clarify §11 with the distinction between:

- **ALLOWED:** CSS-utility-based open/close/hover micro-interactions (`tw-animate-css`, native CSS transitions, transform-only effects).
- **DEFERRED:** JS-based animation libraries (Framer Motion, GSAP, React Spring) — still excluded for v1.0a, can revisit Phase 5.

This isn't a behavior change — slice 4.3's animations are correct per §11's intent. v1.1 just makes the boundary explicit.

---

## Changelog

- **v1.0.1** (2026-06-05) — Added §9.12 (Map panel, right rail) and §17.11 (pin-less → pinned migration v1.1 prep notes) from slice 4.4. Additive only — no breaking changes to existing tokens or patterns.
- **v1.0** (2026-06-05) — Initial spec. Derived from Voyage Elite reference during slice 4.3 design dialogue. Trip Concierge brand framing established (thinking-tool, not marketplace). All tokens, patterns, and copy guidance defined.
