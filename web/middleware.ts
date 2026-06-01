/**
 * Auth.js v5 middleware — slice 4.1 (mvs).
 *
 * Wraps handleAuthRequest with Auth.js's auth() so req.auth is
 * attached before our protected-route check runs. The matcher
 * config restricts the middleware to /trips/* routes — slice 4.2
 * will use this to gate the trip list/detail pages.
 */

import { auth } from "@/auth";
import { type AuthRequestLike, handleAuthRequest } from "@/lib/auth-handler";

export default auth((req) => handleAuthRequest(req as unknown as AuthRequestLike));

export const config = {
  matcher: ["/trips/:path*"],
};
