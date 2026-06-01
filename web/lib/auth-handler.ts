/**
 * Protected-route logic — slice 4.1 (mvs).
 *
 * Lives in lib/ so tests can import it without pulling in @/auth
 * (which transitively imports next/server and breaks under vitest's
 * jsdom environment). middleware.ts composes this function with
 * Auth.js's auth() wrapper to attach req.auth before invocation.
 */

export interface AuthRequestLike {
  auth: unknown;
  nextUrl: { pathname: string; origin: string };
}

export function handleAuthRequest(req: AuthRequestLike): Response | undefined {
  const isProtected = req.nextUrl.pathname.startsWith("/trips");
  if (isProtected && !req.auth) {
    const loginUrl = new URL("/login", req.nextUrl.origin);
    loginUrl.searchParams.set("callbackUrl", req.nextUrl.pathname);
    return Response.redirect(loginUrl);
  }
  return undefined;
}
