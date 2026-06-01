/**
 * Auth.js v5 — EDGE-SAFE config slice (slice 4.1 mvs + edge-middleware-fix).
 *
 * This module MUST stay Edge-Runtime-compatible. Next.js middleware
 * imports this file, and middleware runs in the Edge Runtime — which
 * forbids Node.js APIs (`crypto`, `net`, `tls`, etc.). That means:
 *
 *   - NO `pg` import here (uses Node `crypto` internally).
 *   - NO `PostgresAdapter` import here (drags in `pg`).
 *   - NO `new Pool(...)` here.
 *
 * The adapter + Pool live in `auth.ts`, which is imported only from
 * Node runtime paths (route handlers, server components). Tests can
 * still import `authConfig` and `sendMagicLink` from here safely.
 *
 * Background: the original commit-2 split co-located the adapter in
 * this file under the assumption that "edge-safe = no next/server".
 * Wrong — Edge also forbids Node APIs. Post-merge smoke test caught
 * the gap (middleware compile pulled in `pg` → Edge error → 500 on
 * every protected route). See bd reopen on trip-concierge-mvs.
 */

import type { NextAuthConfig } from "next-auth";
import Google from "next-auth/providers/google";

import { mintMcpToken } from "@/lib/backend";
import { env } from "@/lib/env";

// Resend (email magic-link) provider is intentionally NOT in this
// file. Auth.js's assertConfig() rejects NextAuth(authConfig) when
// an Email provider is present without an adapter — and the adapter
// can't live here (pg → Edge crash). The Resend provider is added
// in auth.ts alongside the PostgresAdapter so the Node-runtime path
// gets both at once. Middleware uses this Edge-safe config which
// has Google-only providers.

interface ResendSendParams {
  identifier: string;
  url: string;
  provider: { apiKey?: string; from?: string | null };
}

export async function sendMagicLink({
  identifier: email,
  url,
  provider,
}: ResendSendParams): Promise<void> {
  // TODO(slice 5.4 / trip-concierge-38t): per-email rate-limit check
  // before the Resend POST. Bots can spam this endpoint to flood a
  // victim's inbox; 5.4 owns the consolidated rate-limit pass.

  if (!provider.apiKey) {
    throw new Error("Resend provider missing apiKey — check RESEND_API_KEY env");
  }
  if (!provider.from) {
    throw new Error("Resend provider missing from address — check RESEND_FROM_EMAIL env");
  }

  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${provider.apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: provider.from,
      to: email,
      subject: "Sign in to Trip Concierge",
      html: `
        <p>Click below to sign in. Expires in 24 hours.</p>
        <p><a href="${url}">Sign in to Trip Concierge</a></p>
        <p>If you didn't request this, you can ignore this email.</p>
      `,
      text: `Sign in to Trip Concierge: ${url}\n\nExpires in 24 hours.`,
    }),
  });

  if (!response.ok) {
    throw new Error(`Resend send failed: ${response.status} ${await response.text()}`);
  }
}

export const authConfig: NextAuthConfig = {
  providers: [
    Google({
      clientId: env.GOOGLE_CLIENT_ID,
      clientSecret: env.GOOGLE_CLIENT_SECRET,
    }),
  ],
  session: { strategy: "jwt" },
  pages: { signIn: "/login" },
  secret: env.NEXTAUTH_SECRET,
  callbacks: {
    async signIn({ user }) {
      // Side-effect MCP mint — see `auth.ts` module docstring. Logging
      // includes a correlation ID so an operator investigating "I
      // can't use MCP" can match page state to the log line.
      //
      // TODO(slice 4.x Settings/MCP / trip-concierge-vmz): surface
      // mint failures in the PWA Settings page so a user with a
      // broken MCP token sees "Token unavailable — retry" rather than
      // silent failure. Current dev fallback: tc-issue-mcp-token CLI.
      if (user?.id) {
        await mintMcpToken({ userId: user.id }).catch((err) => {
          console.error("mint_mcp_token failed", {
            userId: user.id,
            correlationId: crypto.randomUUID(),
            error: String(err),
          });
        });
      }
      return true;
    },
    async jwt({ token, user }) {
      if (user?.id) {
        token.userId = user.id;
      }
      return token;
    },
    async session({ session, token }) {
      if (token.userId && session.user) {
        session.user.id = token.userId as string;
      }
      return session;
    },
  },
};
