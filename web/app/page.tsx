/**
 * `/` — landing page route (slice 4.5c commit 2).
 *
 * Page wrapper composes the shell <Header /> + the <LandingPage />
 * content per Q2c sign-off. Both components are auth-aware internally.
 * Pages stay thin; composition stays at the page level.
 *
 * Replaces the slice 4.1 placeholder (h1 + sign-in link) that served
 * as a stopgap while feature slices accumulated on /trips/[id]. Slice
 * 4.5c is the explicit discharge for that shell debt.
 */

import { Header } from "@/components/header";
import { LandingPage } from "@/components/landing-page";

export default function Page() {
  return (
    <>
      <Header />
      <LandingPage />
    </>
  );
}
