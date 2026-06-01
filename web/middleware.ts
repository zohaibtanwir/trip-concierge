/**
 * Auth.js v5 middleware — slice 4.1 (mvs) + edge-middleware-fix.
 *
 * Runs in the Edge Runtime, which forbids Node.js APIs. This file
 * MUST NOT import `@/auth` (that brings in `pg` → Edge crash). It
 * constructs its own NextAuth wrapper from the Edge-safe authConfig
 * and uses that wrapper to attach req.auth before our protected-
 * route check runs.
 *
 * Matcher restricts the middleware to /trips/* routes — slice 4.2
 * will use this to gate the trip list/detail pages.
 */

import NextAuth from "next-auth";

import { authConfig } from "@/auth.config";
import { type AuthRequestLike, handleAuthRequest } from "@/lib/auth-handler";

const { auth } = NextAuth(authConfig);

export default auth((req) => handleAuthRequest(req as unknown as AuthRequestLike));

export const config = {
  matcher: ["/trips/:path*"],
};
