/**
 * Slice 4.1 (mvs) — Resend sendVerificationRequest contract.
 *
 * The `sendMagicLink` function is the callback Auth.js's Resend
 * provider invokes when a user submits the email form. It calls
 * Resend's HTTPS endpoint (`POST api.resend.com/emails`) with the
 * verification URL Auth.js mints.
 *
 * We unit-test the callback directly — full Auth.js integration with
 * a running Next.js server is out of scope for v1.0a (would need
 * Playwright; covered manually before merging by the slice's PR
 * description). Here we mock global.fetch and assert:
 *
 *   1. The POST hits api.resend.com with the right headers.
 *   2. The from-address comes from env.RESEND_FROM_EMAIL.
 *   3. The verification URL is preserved verbatim in BOTH html and
 *      text bodies (so HTML-blocked email clients still get the link).
 *   4. Resend non-2xx → throw (Auth.js will surface the error to the
 *      user as "couldn't send link").
 *
 * Does NOT test rate-limiting (deferred to slice 5.4 per
 * trip-concierge-38t) or magic-link expiry (Auth.js owns that).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { sendMagicLink } from "@/auth.config";

const _SAMPLE_URL =
  "https://tripconcierge.app/api/auth/callback/email?token=tok-abc&email=u%40x.com";
const _SAMPLE_EMAIL = "u@x.com";
const _SAMPLE_PROVIDER = {
  apiKey: "re_test_dummy_key",
  from: "auth@tripconcierge.app",
};

describe("sendMagicLink", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("posts to api.resend.com with bearer auth and JSON content type", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response("{}", { status: 200 }),
    );

    await sendMagicLink({
      identifier: _SAMPLE_EMAIL,
      url: _SAMPLE_URL,
      provider: _SAMPLE_PROVIDER,
    });

    expect(globalThis.fetch).toHaveBeenCalledOnce();
    const [url, init] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe("https://api.resend.com/emails");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe(`Bearer ${_SAMPLE_PROVIDER.apiKey}`);
    expect(init.headers["Content-Type"]).toBe("application/json");
  });

  it("preserves the verification URL in both html and text bodies", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response("{}", { status: 200 }),
    );

    await sendMagicLink({
      identifier: _SAMPLE_EMAIL,
      url: _SAMPLE_URL,
      provider: _SAMPLE_PROVIDER,
    });

    const [, init] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    const body = JSON.parse(init.body);
    expect(body.to).toBe(_SAMPLE_EMAIL);
    expect(body.from).toBe(_SAMPLE_PROVIDER.from);
    expect(body.html).toContain(_SAMPLE_URL);
    expect(body.text).toContain(_SAMPLE_URL);
  });

  it("throws when Resend returns a non-2xx response", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response('{"error": "rate limited"}', { status: 429 }),
    );

    await expect(
      sendMagicLink({
        identifier: _SAMPLE_EMAIL,
        url: _SAMPLE_URL,
        provider: _SAMPLE_PROVIDER,
      }),
    ).rejects.toThrow(/Resend send failed/);
  });
});
