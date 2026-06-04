# Trip Concierge — Product Requirements Document

**Version:** 1.0
**Status:** Draft
**Owner:** Zohaib
**Last updated:** May 24, 2026
**Audience:** Engineering, Design

---

## 1. Overview

### 1.1 Product summary

Trip Concierge is a multi-agent AI travel planner with two front doors: an **MCP server** that lives inside Claude and ChatGPT, and a **responsive web app (PWA)** for visual planning and consumption. Both surfaces share one backend — a CrewAI-based crew of four specialized agents that produce constraint-aware, source-cited, day-by-day itineraries.

The product is designed around a single principle: **planning a trip is conversational; consuming a trip is visual.** Each surface plays to its strength.

### 1.2 Problem statement

The 2026 AI travel planner market is saturated with itinerary generators that all do roughly the same thing: produce a list and stop. Independent reviews consistently identify the same unmet needs:

- Recommendations are not source-cited, leading to low user trust (only 35% of users fully trust AI travel outputs per Booking.com 2026 data).
- Constraints (budget caps, mobility, dietary, pace) are softly suggested rather than enforced.
- No tool meaningfully supports **mid-trip replanning** when reality breaks the plan (delays, closures, fatigue).
- AI planners produce itineraries in a vacuum, ignoring the user's own research (Reddit threads, YouTube vlogs, friends' WhatsApp tips).
- Group planning is treated as an afterthought.

### 1.3 Goals

1. Ship a working multi-agent travel planner with two surfaces (MCP + PWA) within four weeks.
2. Demonstrate a clear point-of-view on the unsolved problems above — source citations, hard constraints, mid-trip replan, BYO research.
3. Serve as a learning artifact for CrewAI patterns (sequential vs. hierarchical process, agent-to-agent delegation, built-in memory).
4. Provide a credible demoable product that can double as a discussion artifact in B2B travel-tech client conversations.

### 1.4 Non-goals (v1.0)

- In-app booking or payments (we hand off to Booking.com, Skyscanner, etc.).
- Native iOS/Android apps (PWA covers MVP).
- User-generated content, reviews, social feed.
- Flight/hotel search engine.
- Business travel, expense tracking, corporate travel features.

### 1.5 Success metrics (v1.0)

| Metric | Target |
|---|---|
| Time from intake to **202 Accepted** | < 1 second (p95) |
| Crew completion time (queued → done) | < 12 minutes (p95, v1.0 target) |
| Source-cited recommendations | 100% of venues |
| User-visible agent reasoning steps | ≥ 4 per trip |
| MCP tool reliability (success rate) | ≥ 95% |
| PWA Lighthouse performance score (mobile) | ≥ 85 |
| MCP server cold-start to first token | < 2 seconds |

> **Note on the timing metrics:** the original spec was "< 30 seconds intake → first itinerary". Slice 2.3 live runs measured ~9 minutes for a 3-day Goa plan with the 4-agent sequential crew (Researcher → Local Expert → Logistics → Budget Auditor). Rather than relax the spec as a fudge, we restructured around an async/queued architecture: the user-facing HTTP request returns < 1s with a `job_id`, the actual crew runs in the background, and the PWA/MCP poll for status. This is the right architecture for a multi-agent planner regardless — the original 30s target was a planning artifact from when the spec assumed a single-LLM completion. Reducing the 12-minute crew time is a real optimization target (parallelize agent calls, smaller models for narrowing steps, caching) — captured as a separate workstream after v1.0 ships.

---

## 2. Architecture

### 2.1 System diagram

```
                Claude / ChatGPT          Browser / Mobile
                (user's AI chat)         (tripconcierge.app)
                       │                          │
              ┌────────▼─────────┐      ┌─────────▼─────────┐
              │   MCP Server     │      │   PWA (Next.js)   │
              │  (Python, stdio) │      │                   │
              └────────┬─────────┘      └─────────┬─────────┘
                       │                          │
                       └──────────────┬───────────┘
                                      │
                              ┌───────▼──────────┐
                              │ Backend API      │
                              │ (FastAPI)        │
                              │ /trips, /auth,   │
                              │ /trips/{id}/plan │
                              │ /plan/status     │
                              └───┬───────────┬──┘
                                  │           │
                       enqueue ───┘           └─── reads/writes
                                  │           │
                              ┌───▼───────────▼──┐
                              │ Postgres + pgvec │
                              │ (trips, days,    │
                              │  blocks, sources,│
                              │  job_runs)       │
                              └──────────────────┘
                                  ▲
                                  │ persists results
                                  │
                              ┌───┴──────────────────────────┐
                              │ Agents Service               │
                              │ (FastAPI + arq worker)       │
                              │ ┌──────────────────────────┐ │
                              │ │ CrewAI 4-agent crew      │ │
                              │ │  Researcher              │ │
                              │ │  Local Expert            │ │
                              │ │  Logistics               │ │
                              │ │  Budget Auditor          │ │
                              │ │  (Python audit loop)     │ │
                              │ └──────────────────────────┘ │
                              └──────────┬───────────────────┘
                                         │ jobs in/out
                                  ┌──────▼──────┐
                                  │    Redis    │
                                  │ (arq queue, │
                                  │   cache)    │
                                  └─────────────┘

External calls (from Agents Service):
  Anthropic Sonnet 4 (LLM)
  Tavily / Serper (web search)
  Langfuse (tracing — every audit.pass + agent kickoff is a span)
```

**Why the split (decided in Slice 2.5 architecture review, 2026-05-27):**
The 4-agent crew takes ~9 minutes per kickoff. Production HTTP proxies (Fly.io default gateway, Hetzner Nginx) cap requests at 60s. Putting the crew in the Backend API process would make `POST /trips/{id}/plan` time out before completing. The async/queued pattern lets the user-facing API return `202 Accepted` in < 1s; the actual work happens in the Agents Service worker pool, gated by Redis.

### 2.2 Tech stack

| Layer | Choice | Rationale |
|---|---|---|
| Agent orchestration | CrewAI | Project learning goal; hierarchical process + agent delegation |
| LLM | Claude Sonnet 4 (primary), GPT-4-class fallback | Quality/cost balance; multi-provider for resilience |
| API service | FastAPI | Async, OpenAPI native, fits Python agent code |
| MCP server | Python MCP SDK | Wraps FastAPI; deployable as a stdio or HTTP server |
| Web frontend | Next.js 15 (App Router) + Tailwind | PWA-ready, server components for fast first paint |
| Maps | MapLibre GL + OpenStreetMap tiles | No vendor lock-in, free tier |
| Database | PostgreSQL | Trip state, user data |
| Vector store | pgvector (Postgres extension) | Source embeddings for BYO research, memory |
| Cache / queue | Redis | Agent job queue, rate limiting |
| Auth | Auth.js (NextAuth) with email magic links + OAuth | Low-friction, works across both surfaces |
| Search tools (agent) | Tavily, Serper, web scraping | Researcher agent's data sources |
| Hosting | Web app on Vercel; backend on Fly.io or Hetzner | Cost-aware, deployable from a laptop |
| Observability | Langfuse or LangSmith | Agent trace inspection, eval pipeline |

### 2.3 Data model (high level)

```
User
  id, email, email_verified (TIMESTAMPTZ), image (TEXT),
  name, preferences (JSONB), created_at

Trip
  id, user_id, status (draft|active|completed), destination,
  start_date, end_date, group_size, budget_total, currency,
  constraints (JSONB), pace, created_at, updated_at

Day
  id, trip_id, day_number, date, status, summary

Block (one stop in a day)
  id, day_id, order, type (venue|transit|meal|rest),
  venue_name, lat, lng, start_time, duration_min,
  est_cost, currency, locked (bool), notes

Source (citation backing a recommendation)
  id, block_id, url, source_type (reddit|maps|blog|tourism_board|user),
  excerpt, confidence_score, fetched_at

JobRun (one row per crew-planning job — succeeded / failed / cancelled)
  id, job_id, trip_id, status (succeeded|failed|cancelled),
  error (nullable), agent_summary (JSONB — per-agent events captured
  via CrewAI step_callback, best-effort on failure),
  total_tokens, total_cost, total_duration_ms,
  created_at, started_at, finished_at

  Note: v1.0 design is one row per job, not per agent. Originally
  sketched as per-agent rows in the slice-2.4 spec; revised in slice
  2.5b after the queue/worker architecture review — getting per-agent
  state on partial failure requires reconstructing from Langfuse and
  the partial-write complexity isn't worth it. Per-agent rows are a
  v2.0 question if we ever need finer grain. The agent_summary JSONB
  column gives us the "which agent failed?" answer for free.

UserSource (BYO research)
  id, user_id, trip_id, url_or_text, parsed_content,
  embedding (vector), priority, created_at

Memory
  id, user_id, key, value, source_trip_id, created_at
```

### 2.4 Agent design

Four agents, defined declaratively (role, goal, backstory, tools, memory enabled).

| Agent | Role | Tools | Allow delegation |
|---|---|---|---|
| Researcher | Finds candidate destinations, venues, activities | web_search, web_scrape, user_sources_search | Yes |
| Local Expert | Surfaces non-touristy spots; explains *why* | web_search, reviews_aggregator | Yes |
| Logistics Planner | Day-by-day routing, travel time math | maps_api, calendar_math | Yes |
| Budget Auditor | Challenges plan against constraints | calculator, currency_convert | Yes (adversarial) |

**Process modes supported:**

- `Process.sequential` — for the predictable initial trip generation
- `Process.hierarchical` — for refinement and mid-trip replan (a manager LLM routes between agents)

**Crew memory:** enabled (short-term, long-term, entity). Persisted per `user_id`.

---

## 3. Feature scope — v1.0 (MVP)

### F1. Conversational intake

**User story:** As a user, I want to describe my trip in natural language and get a first draft itinerary in under 30 seconds.

**Surface:** MCP (primary), PWA (secondary chat box)

**Inputs collected:**
- Destination(s) — string, multi-allowed
- Date range — start and end, validated as future and ≤ 30 days
- Group composition — solo / couple / family / friends / custom
- Budget — total or per-day, currency
- Vibe — free text (e.g., "chill, lots of food, no parties")
- Constraints — optional structured (dietary, mobility, no-go list)

**Acceptance criteria:**
- [ ] MCP tool `create_trip` accepts all fields above and returns a `trip_id` plus first-draft Day objects.
- [ ] If any required field is missing, the tool returns a structured prompt asking only for what's missing (no full re-prompt).
- [ ] PWA chat box accepts the same free-text input and routes through the same backend endpoint.
- [ ] First draft is generated in ≤ 30 seconds (p95). Streaming progress updates are emitted at each agent step.
- [ ] Currency defaults to user's locale; user can override.

---

### F2. Day-by-day itinerary view

**User story:** As a user, I want a scannable day-by-day plan with venue names, times, costs, and routing.

**Surface:** PWA (primary), MCP (text version)

**Acceptance criteria:**
- [ ] Each day renders as a vertical scroll of Blocks on mobile, two-column (itinerary + map) on tablet/desktop ≥ 768px.
- [ ] Each Block displays: venue name, start time, duration, estimated cost, travel time to next stop, one thumbnail image (lazy-loaded).
- [ ] Tap a Block to expand: opening hours, full address, photos, source citations, "why this was picked" panel.
- [ ] Swipe-left removes a Block (with undo toast for 5s).
- [ ] Swipe-right locks a Block (excluded from future regeneration).
- [ ] Day navigation: sticky chip bar at top (Day 1 / Day 2 / …); horizontal swipe between days on mobile.
- [ ] MCP `get_trip` returns the same data as a structured JSON payload plus a formatted text summary.

---

### F3. Interactive map view

**User story:** As a user, I want to see my trip on a map with day-filtered pins and routes.

**Surface:** PWA only

**Acceptance criteria:**
- [ ] MapLibre map renders with all venues as pins for the selected day.
- [ ] "All days" toggle shows all pins with color-coding per day.
- [ ] Route lines drawn between consecutive Blocks within a day.
- [ ] Tap a pin → scrolls itinerary to that Block and highlights it.
- [ ] Pinch-zoom and pan on mobile; double-tap to zoom in.
- [ ] Map respects reduced-motion accessibility setting.
- [ ] "Today" mode (active during the trip dates): shows current location and next stop highlighted.

---

### F4. Constraint controls (hard, not soft)

**User story:** As a user, I want my budget, dietary, and mobility constraints enforced, not just suggested.

**Surface:** Both

**Acceptance criteria:**
- [ ] User can set: total budget cap, per-day cap, max walking distance per day, dietary tags (multi-select), accessibility flag, no-go list (free-text + tags).
- [ ] Budget Auditor agent validates the full itinerary against caps before output is finalized; if exceeded, plan is sent back for revision (max 2 retries).
- [ ] If revision fails twice, the user sees an explicit message: "I couldn't fit this within ₹X. Closest plan is ₹Y. Want me to suggest where to flex?"
- [ ] Pace slider (packed / balanced / lazy) maps to a max-blocks-per-day cap (8 / 6 / 4 default).
- [ ] MCP `add_constraint` and `refine_trip` honor the same logic.

---

### F5. Edit and regenerate

**User story:** As a user, I want to change part of the plan without rebuilding the whole trip.

**Surface:** Both

**Acceptance criteria:**
- [ ] PWA: tap "Regenerate" on a single Block — replaces only that Block with an alternative honoring the same constraints.
- [ ] PWA: tap "Regenerate Day" — re-plans only that day; locked Blocks are preserved.
- [ ] MCP `refine_trip` accepts free-text instructions ("make Day 2 chiller", "swap the museum for something outdoor") and routes through the hierarchical process.
- [ ] All edits create an immutable JobRun record; the previous version of the day is recoverable.
- [ ] "Undo last change" is one tap from the day view header.

---

### F6. Source citations on every recommendation

**User story:** As a user, I want to know *why* each venue is in my plan and where the recommendation came from.

**Surface:** Both

**Acceptance criteria:**
- [ ] Every Block of type `venue` or `meal` has at least one Source record attached.
- [ ] PWA: expanded Block view shows up to 3 source links with source type icons (Reddit, Maps, blog, tourism board, user).
- [ ] MCP: `explain_recommendation` tool returns the sources as a structured list plus a one-sentence rationale.
- [ ] Confidence indicator (high / medium / low) shown per Block based on source recency, count, and agent agreement.
- [ ] Hallucinated venues (no source attached) are flagged and removed before the plan is returned to the user.

---

### F7. Bring Your Own Research (BYO Research)

**User story:** As a user, I want to paste a Reddit thread, a YouTube link, or a friend's WhatsApp message, and have the planner prioritize what's in there.

**Surface:** Both

**Acceptance criteria:**
- [ ] MCP `add_source` accepts a URL or raw text and attaches it to a `trip_id`.
- [ ] PWA: "Add a source" button on the trip header; accepts URL paste, drag-drop text, or screenshot OCR (post-MVP for OCR).
- [ ] Researcher agent re-runs with user sources prioritized; venues mentioned in user sources are tagged with a "From your sources" badge.
- [ ] If a user-sourced venue conflicts with a hard constraint (e.g., over budget), the Budget Auditor flags it but doesn't silently drop it — user is asked.

---

### F8. Visible agent activity

**User story:** As a user, I want to see what the AI did so I can trust the output.

**Surface:** Both

**Acceptance criteria:**
- [ ] PWA: collapsible "How this plan was made" panel at the top of each day, listing each agent's contribution in plain English ("Researcher found 12 options, Local Expert narrowed to 4, Budget Auditor cut 1 over budget").
- [ ] MCP: same content returned as structured `agent_activity` array on `get_trip`.
- [ ] JobRun records are persisted and queryable for debugging.
- [ ] Each step shows duration and is tappable to see the agent's reasoning (full text).

---

### F9. Share and export

**User story:** As a user, I want to share my plan with travel companions or save it for offline use.

**Surface:** PWA (primary), MCP (returns the share URL)

**Acceptance criteria:**
- [ ] One-tap "Share" generates a read-only link (`/t/{trip_id}/share/{token}`).
- [ ] "Collaborate" link allows invited users to edit; uses email-magic-link auth.
- [ ] PDF export: each day on its own page, includes map snapshot, QR codes per venue.
- [ ] "Send to WhatsApp" — opens WhatsApp with pre-formatted message containing the plan summary and share link.
- [ ] "Export to Google Maps" creates a saved list via Google Maps URL list import.
- [ ] MCP `export_trip` returns the share URL and PDF URL (signed, expires in 7 days).

---

### F10. Auth and account

**User story:** As a user, I want to start a trip in chat and continue it in the web app without friction.

**Surface:** Both

**Acceptance criteria:**
- [x] First MCP call from an unknown identity returns a short magic-link URL; user clicks once, account is created, future MCP calls are authenticated via a server-side token. *(Slice 4.1b — backend-rendered redeem at `GET /auth/mcp/redeem?code=...`; MCP server polls `GET /auth/mcp/poll/{code}` and saves the JWT to disk once redeemed.)*
- [x] PWA login via email magic link or Google OAuth. *(Slice 4.1 — Auth.js v5 + Resend magic-link + Google OAuth.)*
- [ ] Trips are owned by the user; share links work without recipient sign-in (read-only) or require sign-in (collaborate).
- [ ] User can delete their account; cascade-deletes all trips, sources, and memory.

**MCP-side flow shape (Shape 1, server-driven polling):** The MCP server reads `TC_MCP_USER_EMAIL` from its per-user Claude Desktop config and POSTs to `/auth/mcp/challenge` on first tool call without a token. Backend creates an `auth_challenges` row, sends the magic-link email via Resend (subject distinguishes from PWA sign-in: *"Authorize Trip Concierge for Claude Desktop"*), and returns a short opaque code. The MCP server displays the magic-link URL to the user, then polls `/auth/mcp/poll/{code}` on each subsequent tool call. The user clicks the email link → backend renders an inline HTML success page (no PWA roundtrip — keeps MCP and PWA session trust roots separate). Next tool call's poll returns the minted MCP JWT (one-shot — row transitions to `consumed` so leaked codes can't replay). MCP server writes the JWT to `~/.config/trip-concierge/token`, retries the tool. Future tool calls read the token from disk normally.

Without `TC_MCP_USER_EMAIL` set, MCP tools return a setup-hint message instead of attempting the flow.

---

### F11. Responsive and mobile-first behavior

**User story:** As a mobile user, the app should feel native: fast, touch-friendly, and offline-capable.

**Surface:** PWA only

**Acceptance criteria:**
- [ ] Breakpoints: 360 / 768 / 1024 px. Single-column layout below 768px.
- [ ] All primary CTAs sit in the bottom one-third of the viewport on mobile (thumb-reach zone).
- [ ] Touch targets ≥ 44 × 44 px.
- [ ] Filters and edit forms render as bottom sheets, not modal popups.
- [ ] Pull-to-refresh on the day view triggers a soft re-sync (does not regenerate).
- [ ] PWA manifest + service worker registered; installable to home screen.
- [ ] Last-synced trip + map tiles cached for offline view.
- [ ] Low-data mode: text-only, photos load on tap.
- [ ] Lighthouse mobile performance score ≥ 85.

---

## 4. MCP Server — Tool Specification

All tools return JSON. Authentication is via an `x-tc-token` header (issued during the magic-link flow).

| Tool | Purpose | Inputs | Returns |
|---|---|---|---|
| `create_trip` | Start a new trip from natural-language intake | destination, dates, group, budget, vibe, constraints (all optional but at least one of destination or vibe required) | `trip_id`, first-draft days, share_url |
| `get_trip` | Fetch current state | `trip_id` | Full trip object with days, blocks, sources, agent_activity |
| `refine_trip` | Free-text edit | `trip_id`, `instruction` (string) | Updated trip object + diff summary |
| `regenerate_day` | Re-plan one day | `trip_id`, `day_number`, optional new constraint | Updated day |
| `add_constraint` | Add or modify a constraint | `trip_id`, constraint type, value | Updated trip + revision summary |
| `add_source` | Attach a user research source | `trip_id`, url or text | Source id, parsed summary |
| `find_alternative` | Suggest a replacement for a block | `trip_id`, `block_id`, reason | 3 alternatives with rationale |
| `explain_recommendation` | Why was this picked? | `trip_id`, `block_id` | Sources + agent rationale |
| `replan_from_here` | Mid-trip replan (v2.0 — see roadmap) | — | — |
| `share_trip` | Get shareable URL | `trip_id`, mode (read/collab) | URL + token |
| `export_trip` | Get PDF / formatted text | `trip_id`, format | URL or text |

**Tool description guidelines:** each MCP tool's description must be written from the LLM's perspective — explicit about *when* to call it. Bad: "Creates a trip." Good: "Use when the user expresses intent to plan a new trip with at least a destination or a vibe described. Do not call if a `trip_id` already exists in conversation context — use `refine_trip` instead."

---

## 5. Cross-cutting concerns

### 5.1 Rate limiting and cost control

- Per-user limits: 20 agent runs per hour, 100 per day.
- Per-tool cost budgets enforced at the FastAPI layer (token caps per tool).
- Cost dashboard exposed at `/admin/costs` (internal only).

### 5.2 Observability

- Langfuse traces for every agent run (input, output, tokens, cost, duration).
- Structured logs (JSON) shipped to a single sink.
- Sentry for frontend errors.
- A dashboard showing: trips/day, p50/p95 generation time, agent failure rate, MCP tool call distribution.

### 5.3 Security

- All MCP tools require a per-user token; tokens scoped to the user's trips only.
- No payment data ever stored.
- Email is the only PII stored by default.
- Source URLs are sanitized; HTML stripped before indexing.
- Rate limits applied at IP + token level.

### 5.4 Accessibility

- WCAG 2.1 AA compliance for the PWA.
- All actions reachable via keyboard.
- ARIA labels on interactive map elements.
- Color contrast ≥ 4.5:1; do not encode information by color alone (use icons + text).

### 5.5 Internationalization (v1.0 scope)

- English only for UI in v1.0.
- Itinerary content supports any destination; agent prompts are locale-aware (currency, distance units).
- Right-to-left layout is out of scope until v2.0.

### 5.6 Supply chain security

**Context.** Between March and May 2026, the JavaScript and Python package ecosystems have been hit by a sustained, coordinated supply chain attack campaign (Mini Shai-Hulud / TeamPCP and others). Confirmed compromises include Axios (npm, 70M+ weekly downloads), node-ipc, TanStack (42 packages), Mistral AI SDK (npm and PyPI), Guardrails AI (PyPI), UiPath, OpenSearch, Bitwarden CLI impersonation, and Laravel-Lang (700+ versions, May 22-23, 2026). The attackers target cloud credentials, CI/CD secrets, GitHub tokens, Kubernetes service account tokens, Vault tokens, and SSH keys.

**Mandatory practices for v1.0:**

- **No ranged dependencies.** All `package.json` and `requirements.txt` entries use exact versions. No `^`, no `~`, no `>=`. Renovate or Dependabot proposes updates as PRs; humans review.
- **Lockfile-only installs.** `npm ci` and `pip install --require-hashes` in CI. No `npm install` or `pip install` without a lockfile.
- **Avoid known-compromised packages.** Explicit denylist enforced in CI: `axios` (use native `fetch` or `ky`), `node-ipc`, `mistralai`, `guardrails-ai`, all `@tanstack/*` router packages, any `@uipath/*`, `@squawk/*`, `intercom-client`, `opensearch-project/opensearch`. Re-evaluate quarterly; never reintroduce a package within 60 days of a compromise disclosure.
- **No TanStack ecosystem.** We use Next.js App Router defaults; no `@tanstack/react-query`, `@tanstack/react-router`, or related during the current threat window.
- **Pin SDK versions for AI providers.** Anthropic SDK pinned exactly. No experimental AI tooling SDKs from publishers that haven't been audited in the last 30 days.
- **No `postinstall` scripts in dependencies.** Configure npm with `--ignore-scripts` by default; explicit allowlist for packages that genuinely need install scripts (build tools only). This blocks the most common attack vector seen across Axios, node-ipc, and the Bitwarden CLI impersonation.
- **GitHub Actions hardening.** No `pull_request_target` workflows (the vector used in the TanStack attack). All workflows pin actions to a full SHA, not a version tag. Set `permissions:` minimally (default to `read`). No secret access from forked PR workflows.
- **OIDC trusted publishing** for any package we publish (we don't publish for v1.0, but the rule stands).
- **Composer is irrelevant.** We don't use PHP, so the Laravel-Lang vector doesn't apply — explicitly listed here so reviewers can confirm.
- **Egress monitoring** on production and CI runners. Block known malicious IPs and domains from current advisories (e.g., `git-tanstack[.]com`, `83.142.209[.]194` from the May 11 wave). Log all egress; alert on connections to non-allowlisted destinations from CI runners.
- **Secret hygiene.** No long-lived static tokens in CI; use OIDC where available. Rotate any token quarterly even without an incident.
- **Continuous scanning.** Socket.dev or Snyk on every PR. Block merge on any package flagged as malicious or with a CVE above CVSS 7.0 introduced by the PR.
- **Lockfile diff review.** Any PR that changes the lockfile is reviewed by a second person before merge, even for "automated" dependency bumps.

**Threat model assumption:** Treat every transitive dependency as potentially hostile. The PRD's tech stack is chosen for surface-area minimization, not just feature fit.

**Reassessment cadence:** This section is reviewed monthly during v1.0 build and before every minor release thereafter. The denylist is updated as new compromises are disclosed.

---

## 6. Build plan and milestones

| Week | Milestone | Deliverable |
|---|---|---|
| 1 | Agent backend | CrewAI crew with 4 agents, FastAPI endpoints, Postgres schema, sequential process working end-to-end |
| 2 | MCP server | All 11 tools (10 in v1.0, 1 stubbed for v2.0), test in Claude Desktop, magic-link auth flow |
| 3 | PWA core | Next.js shell, day view, map view, edit flow, share + export, mobile responsive |
| 4 | Polish + deploy | Hierarchical process for refine, BYO research, agent activity panel, Lighthouse pass, production deploy |

**Definition of Done for v1.0:** A new user can describe a trip in Claude (via MCP), receive a draft, open the share URL in their phone browser, see the map, edit one block, export as PDF — all in under 5 minutes, with no support tickets.

---

## 7. Open questions

1. **MCP authentication UX** — magic link in the first response is functional but clunky. Investigate OAuth-style flow for MCP (still maturing in the spec).
2. **Multi-LLM strategy** — should we let users choose Claude vs. GPT-4 for their trip? Adds complexity vs. quality control.
3. **Booking handoff revenue** — affiliate deep links could fund infra. Out of scope for v1.0, decide pre-v2.0.
4. **Memory privacy** — do we surface "what I remember about you" prominently, or only in settings? Trust vs. clutter trade-off.

---

# Appendix A — v2.0 Roadmap

Features de-scoped from v1.0, prioritized for v2.0.

### A1. Mid-trip companion mode (the moat)

- `replan_from_here` MCP tool fully implemented.
- "I'm here now" geolocation re-anchor in the PWA.
- Push notifications for next stop (opt-in).
- 30-second replan when a venue closes, weather breaks, or transit fails.

### A2. Group planning

- Multi-user invitations on a trip, with per-user preference profiles.
- Voting on options (museums vs. beach).
- Conflict resolution view: agents propose compromises with stated rationale.
- Synced arrivals planning (different origins, common destination).

### A3. Cross-trip memory

- User-visible memory page; edit and delete remembered facts.
- "You disliked crowded markets in Bangkok" carries to Istanbul plans.
- Entity memory exposed (favorite cuisines, dealbreakers, preferred hotel types).

### A4. Pace and energy awareness

- Daily walking-distance tracker.
- Fatigue flag with auto-suggested rest blocks.
- Buffer time auto-inserted between long transits.

### A5. Confidence scoring (visible)

- Per-block confidence score surfaced in UI.
- Filter: "show only high-confidence picks".
- Source recency + review depth + agent agreement aggregated.

### A6. Replan diff view

- When the plan changes, show what changed and *why* (which agent and which rule triggered it).
- One-tap revert per change.

### A7. Bookings handoff

- One-tap deep links to Booking.com, Skyscanner, OpenTable, GetYourGuide, Klook.
- Track which bookings were made; feed back into memory.
- No payments held, no fees taken in v2.0 (affiliate revenue evaluated for v2.1).

### A8. OCR + image source ingestion

- Screenshot of a friend's WhatsApp recommendation → parsed and added as a source.
- Photo of a menu → dietary check against trip constraints.

### A9. Native mobile apps

- Evaluate after PWA usage data shows clear native-only needs (push reliability, offline maps, faster cold start).

### A10. Multi-language

- UI localization (start with Hindi, Spanish, French).
- Locale-aware itinerary generation (already partially in v1.0).

### A11. Enterprise / B2B mode

- White-label MCP server for travel ISVs (Open Destinations, Tourplan, mid-market tour operators).
- Tour catalog ingestion as an MCP tool.
- This is where the consumer learning project converts into a B2B product line.

---

# Appendix B — Glossary

- **Agent:** A CrewAI role with a defined goal, backstory, set of tools, and optional delegation rights.
- **Block:** One stop within a Day (a venue, a meal, a transit leg, or a rest).
- **Crew:** A CrewAI ensemble of agents running together under a process (sequential or hierarchical).
- **MCP (Model Context Protocol):** An open protocol that lets AI chat applications (Claude, ChatGPT) call external tools and data sources.
- **PWA (Progressive Web App):** A web application that behaves like a native mobile app — installable, offline-capable, push-enabled.
- **Source:** A citation record backing a recommendation (a URL, an excerpt, a confidence score).
- **Trip:** The top-level object owning Days, Blocks, Sources, Constraints, and JobRuns.
