/**
 * Auth.js v5 config — slice 4.1 (mvs).
 *
 * Split out from `auth.ts` per the Auth.js Edge-Runtime guidance: the
 * config object is pure data + functions, importable from Edge code
 * (middleware) and from tests without pulling in Next.js's server
 * APIs. `auth.ts` calls NextAuth(authConfig) — that import path
 * pulls in next/server.
 *
 * Two providers (Resend email magic-link + Google OAuth), JWT
 * session strategy, PostgreSQL adapter. See the alembic 0008
 * migration for the schema and `web/auth.ts` module docstring for
 * the two-writers pattern.
 */

import PostgresAdapter from "@auth/pg-adapter";
import type { NextAuthConfig } from "next-auth";
import Google from "next-auth/providers/google";
import Resend from "next-auth/providers/resend";
import { Pool } from "pg";

import { mintMcpToken } from "@/lib/backend";
import { env } from "@/lib/env";

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

// Pool construction is lazy — pg's `new Pool()` does not connect
// until the first query. Tests that import this module don't trigger
// any network activity.
const pool = new Pool({ connectionString: env.DATABASE_URL });

export const authConfig: NextAuthConfig = {
  adapter: PostgresAdapter(pool),
  providers: [
    Google({
      clientId: env.GOOGLE_CLIENT_ID,
      clientSecret: env.GOOGLE_CLIENT_SECRET,
    }),
    Resend({
      apiKey: env.RESEND_API_KEY,
      from: env.RESEND_FROM_EMAIL,
      sendVerificationRequest: sendMagicLink,
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
      // TODO(slice 4.x Settings/MCP): surface mint failures in the
      // PWA Settings page so a user with a broken MCP token sees
      // "Token unavailable — retry" rather than silent failure.
      // Current dev fallback: tc-issue-mcp-token CLI.
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
