/**
 * LandingPage — product framing surface for `/` (slice 4.5c commit 2).
 *
 * Four sections per Q2 sign-off:
 *   1. Hero — tagline + branched CTA (Q4=C: unauthed Sign in / authed
 *      "View your trips →") + subtle brand-color gradient backdrop
 *   2. How it works — 3 cards (Create via Claude Desktop / Refine in
 *      web app / Plan persists across both)
 *   3. Why agents — multi-agent specialization framing naming all 4
 *      specialists (Researcher, Local Expert, Logistics, Budget
 *      Auditor) — Marsh demo-valuable
 *   4. Footer — wordmark + © 2026 + tech credit (inline, no extracted
 *      <Footer /> until a reuse case appears per Q2e)
 *
 * Auth-aware-internally per Q1=A consistency with Header. Page wrapper
 * at app/page.tsx composes <Header /> + <LandingPage /> per Q2c.
 *
 * Developer-draft copy throughout per Q2; refinement is a P3 follow-up.
 */

import Link from "next/link";

import { auth } from "@/auth";

function _Hero({ authed }: { authed: boolean }) {
  // Subtle brand-color gradient backdrop (primary → primary-container)
  // at low opacity. Coheres with the teal Header above without
  // overpowering the page content. Per Q2d sign-off: dial UP later
  // is easier than dial DOWN, so this lands subtle.
  return (
    <section className="relative overflow-hidden">
      <div
        className="absolute inset-0 bg-gradient-to-br from-primary/15 via-primary-container/30 to-primary-container/10 pointer-events-none"
        aria-hidden
      />
      <div className="relative mx-auto max-w-[1440px] px-4 md:px-8 lg:px-16 pt-24 pb-20 md:pt-32 md:pb-28">
        <h1 className="text-headline-md text-on-surface md:text-headline-lg max-w-3xl">
          Travel planning that thinks like a senior travel writer.
        </h1>
        <p className="mt-6 max-w-2xl text-body-lg text-on-surface-variant">
          Trip Concierge is a multi-agent AI travel planner. Four specialist agents — Researcher,
          Local Expert, Logistics Planner, and Budget Auditor — collaborate to build an itinerary
          that holds up in practice, not just on paper.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-3">
          {/* Primary CTA — "Plan a trip" routes through auth as needed
           * and lands on /trips with the dialog auto-opened. Critique 1
           * sign-off: action-oriented entry point matters more than
           * passive "Sign in" / "View your trips" copy for first-time
           * visitors who want to do something, not just browse. */}
          <Link
            href={
              authed
                ? "/trips?new=true"
                : `/login?callbackUrl=${encodeURIComponent("/trips?new=true")}`
            }
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-3 text-label-md text-on-primary hover:bg-primary/90 transition-colors"
          >
            Plan a trip
          </Link>
          {authed ? (
            <Link
              href="/trips"
              className="inline-flex items-center gap-2 rounded-lg border border-outline-variant bg-surface-container-lowest px-6 py-3 text-label-md text-on-surface hover:bg-surface-container-low transition-colors"
            >
              View your trips →
            </Link>
          ) : (
            <Link
              href="/login"
              className="inline-flex items-center gap-2 rounded-lg border border-outline-variant bg-surface-container-lowest px-6 py-3 text-label-md text-on-surface hover:bg-surface-container-low transition-colors"
            >
              Sign in
            </Link>
          )}
        </div>
      </div>
    </section>
  );
}

function _HowItWorks() {
  const cards = [
    {
      title: "Create via Claude Desktop",
      body: "Tell Claude what kind of trip you want. The MCP tool kicks off a 10-minute multi-agent crew that researches venues, validates costs, and builds a day-by-day itinerary.",
    },
    {
      title: "Refine in the web app",
      body: "Adjust pace, budget, and constraints from the trip detail page. The crew re-plans, the Budget Auditor verifies, and your plan updates in place.",
    },
    {
      title: "Plan persists across both",
      body: "The same trip is reachable from Claude Desktop AND from this web app. Edits in one surface show up in the other; no syncing, no exports.",
    },
  ];
  return (
    <section className="mx-auto max-w-[1440px] px-4 md:px-8 lg:px-16 py-16 md:py-24">
      <h2 className="text-headline-sm text-on-surface md:text-headline-md mb-10">How it works</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {cards.map((card) => (
          <div
            key={card.title}
            className="rounded-xl border border-outline-variant bg-surface-container-lowest p-6"
          >
            <h3 className="text-label-lg text-on-surface mb-3">{card.title}</h3>
            <p className="text-body-md text-on-surface-variant">{card.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function _WhyAgents() {
  const agents = [
    { name: "Researcher", role: "finds venues with real citations, not stock recommendations" },
    {
      name: "Local Expert",
      role: "narrows the list to what beats the obvious tourist alternative",
    },
    { name: "Logistics Planner", role: "orders the day with realistic travel times and pacing" },
    { name: "Budget Auditor", role: "validates against your cap and surgically revises if over" },
  ];
  return (
    <section className="bg-surface-container-low">
      <div className="mx-auto max-w-[1440px] px-4 md:px-8 lg:px-16 py-16 md:py-24">
        <h2 className="text-headline-sm text-on-surface md:text-headline-md mb-4">
          Why agents, not just AI
        </h2>
        <p className="max-w-3xl text-body-md text-on-surface-variant mb-10">
          A single LLM can produce a plausible itinerary. A specialist crew produces one that
          survives contact with reality — because each agent owns one concern, hands off through
          structured outputs, and gets audited before anything ships.
        </p>
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {agents.map((agent) => (
            <li
              key={agent.name}
              className="rounded-lg border border-outline-variant bg-surface-container-lowest p-4 flex items-baseline gap-3"
            >
              <span className="text-label-md text-on-surface font-semibold">{agent.name}</span>
              <span className="text-body-md text-on-surface-variant">{agent.role}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function _Footer() {
  return (
    <footer className="border-t border-outline-variant">
      <div className="mx-auto max-w-[1440px] px-4 md:px-8 lg:px-16 py-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <span className="text-label-md text-on-surface">Trip Concierge</span>
        <span className="text-label-sm text-on-surface-variant">© 2026</span>
        <span className="text-label-sm text-on-surface-variant">
          Built with CrewAI + Claude Sonnet 4
        </span>
      </div>
    </footer>
  );
}

export async function LandingPage() {
  const session = await auth();
  const authed = Boolean(session?.user);
  return (
    <main>
      <_Hero authed={authed} />
      <_HowItWorks />
      <_WhyAgents />
      <_Footer />
    </main>
  );
}
