"""URL fetch + parse + 6-defense SSRF stack for add_source.

Slice 3.4b commit 2. The highest-risk surface in v1.0a:
add_source intentionally expands the egress allowlist to "any URL
the user pastes into Claude Desktop." This module contains that
expansion behind a stack of six independent defenses, each pinned
by its own test in tests/test_source_ingestion.py.

The defenses run cheapest-first so the cost of fielding a bad URL
is bounded by the earliest defense that fires:

  1. Scheme allowlist (http/https only) — μs, no I/O
  2. _DENIED_HOSTS canonical list — μs, no I/O
  3. DNS resolve + IP-range validation — ms (DNS)
  4. httpx GET with 10s total timeout
  5. Content-Type allowlist (text/html, text/plain, application/json) — μs after headers
  6. 2 MB streaming size limit — bounded by MAX_BYTES of transfer

Each defense raises a distinct exception class so the route layer
routes to a specific user-facing formatter without parsing exception
messages:

  - DeniedHostError       — defenses 1, 2, 3
  - FetchFailedError      — defense 4 + network errors
  - UnsupportedContentTypeError — defense 5
  - ContentTooLargeError  — defense 6

Known v1.0a limitation: DNS rebinding. Defense 3 resolves the
hostname and validates the IP before handing the URL to httpx, but
httpx re-resolves before connecting. A coordinated attacker
controlling the user's local DNS resolver could return a public IP
on the validation call and a private IP on the connection call.
Robust defense requires pinning the validated IP in a custom httpx
transport. Tracked as a P2 followup. Residual risk is accepted for
v1.0a because the attacker bar is meaningfully higher than basic
SSRF; .claude/rules/dependencies.md §8 documents the limitation.

HTML→text uses stdlib html.parser per the slice-opening Q1 decision.
The extractor is crude by design — discards script/style/nav/footer,
emits paragraph-level text. Better extraction is what v1.0c per-site
parsers (ticket a8c) is for; v1.0a accepts "we got SOMETHING
reasonable from the body" as the bar.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


_ALLOWED_SCHEMES = frozenset({"http", "https"})

# Hosts that pass is_global IP check under some configurations but
# resolve to internal/metadata endpoints in practice. Belt-and-suspenders
# alongside the post-DNS IP-range check (defense 3).
_DENIED_HOSTS = frozenset(
    {
        "metadata.google.internal",  # GCP metadata
        "169.254.169.254",  # AWS / Azure metadata IP
        "localhost",
        "0.0.0.0",
    }
)

_ALLOWED_CONTENT_TYPES = frozenset({"text/html", "text/plain", "application/json"})

# Hard wall-clock ceiling for the entire fetch. See module docstring
# for the trade-off rationale.
_TIMEOUT_SECONDS = 10.0

# Streaming size limit. 2 MB chosen because: (a) most travel research
# articles are under 200 KB; 2 MB gives 10x headroom for image-heavy
# pages whose HTML is small but assets are not (we don't fetch assets);
# (b) 2 MB caps the worst-case memory footprint per concurrent ingest.
MAX_BYTES = 2_000_000

# HTML tags whose text content we keep. Anything outside this set
# (script, style, nav, header, footer, aside, form, button, etc.)
# contributes no text to the extracted output.
_KEEP_TAGS = frozenset(
    {
        "p",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "blockquote",
        "article",
        "section",
        "main",
        "div",
        "span",
        "td",
        "th",
        "dd",
        "dt",
        "body",
    }
)

# Tags whose ENTIRE subtree is dropped, even if it contains a kept tag.
_DROP_SUBTREE_TAGS = frozenset(
    {
        "script",
        "style",
        "nav",
        "header",
        "footer",
        "aside",
        "form",
        "button",
        "noscript",
        "iframe",
        "svg",
    }
)


# ---------------------------------------------------------------------------
# Result and exception types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestResult:
    """Successful fetch + extract. The route persists this as a
    UserSource row via append_user_source.
    """

    raw_text: str
    content_type: str
    byte_count: int


class IngestionError(Exception):
    """Base — route maps subclasses to specific formatters."""


class DeniedHostError(IngestionError):
    """Defenses 1, 2, 3 — bad scheme, denied host, or private IP."""


class FetchFailedError(IngestionError):
    """Defense 4 + network errors — timeout, refused, HTTP 4xx/5xx."""


class UnsupportedContentTypeError(IngestionError):
    """Defense 5 — Content-Type header outside the allowlist."""


class ContentTooLargeError(IngestionError):
    """Defense 6 — body exceeded MAX_BYTES during streaming read."""

    def __init__(self, url: str, byte_count: int) -> None:
        super().__init__(f"content too large at {url}: {byte_count} bytes (cap {MAX_BYTES})")
        self.url = url
        self.byte_count = byte_count


# ---------------------------------------------------------------------------
# Defenses 1-3: pre-fetch validation
# ---------------------------------------------------------------------------


def _validate_url(url: str) -> str:
    """Run defenses 1, 2, 3. Returns the validated hostname on success.

    Raises DeniedHostError with a message naming which defense fired.
    """
    parsed = urlparse(url)

    # Defense 1: scheme allowlist.
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise DeniedHostError(f"unsupported scheme: {parsed.scheme!r}")

    host = (parsed.hostname or "").lower()
    if not host:
        raise DeniedHostError(f"unsupported scheme: missing host in {url!r}")

    # Defense 2: canonical denied-host list.
    if host in _DENIED_HOSTS:
        raise DeniedHostError(f"denied host: {host}")

    # Defense 3: DNS resolve + IP-range check.
    try:
        ip_str = socket.gethostbyname(host)
    except OSError as e:
        raise DeniedHostError(f"DNS resolution failed for {host}: {e}") from e

    try:
        ip_obj = ipaddress.ip_address(ip_str)
    except ValueError as e:
        raise DeniedHostError(f"invalid resolved IP {ip_str} for {host}") from e

    if not ip_obj.is_global:
        raise DeniedHostError(
            f"host {host} resolves to non-public IP {ip_str} (private/loopback/link-local)"
        )

    return host


# ---------------------------------------------------------------------------
# Defenses 4-6: fetch + content-type + size limit
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _open_response_stream(url: str, timeout: float) -> AsyncIterator[httpx.Response]:
    """Open an httpx GET stream. Patchable seam — tests replace this
    with a CM that yields a canned response, avoiding the need to mock
    httpx's nested context-manager chain directly.
    """
    async with (
        httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client,
        client.stream("GET", url) as response,
    ):
        yield response


def _validate_content_type(url: str, content_type_header: str) -> str:
    """Defense 5. Returns the canonical MIME type on success; raises
    UnsupportedContentTypeError otherwise. Parses past parameters
    ("text/html; charset=utf-8" → "text/html").
    """
    main_type = content_type_header.split(";", 1)[0].strip().lower()
    if main_type not in _ALLOWED_CONTENT_TYPES:
        raise UnsupportedContentTypeError(
            f"unsupported Content-Type {content_type_header!r} for {url}"
        )
    return main_type


async def _read_with_limit(url: str, response: httpx.Response) -> bytes:
    """Defense 6. Streams the body in chunks; aborts mid-stream once
    MAX_BYTES is exceeded so the worst-case memory cost is bounded.
    """
    parts: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes(chunk_size=8192):
        total += len(chunk)
        if total > MAX_BYTES:
            raise ContentTooLargeError(url=url, byte_count=total)
        parts.append(chunk)
    return b"".join(parts)


# ---------------------------------------------------------------------------
# HTML → text extractor (stdlib only)
# ---------------------------------------------------------------------------


class _TextExtractor(HTMLParser):
    """Crude HTML→text extractor. Drops scripts/styles/nav/footer/etc.
    entirely; emits text from paragraph-like tags. v1.0c per-site
    parsers (ticket a8c) is the path to better extraction.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._drop_depth = 0  # >0 while inside a dropped subtree
        self._pieces: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in _DROP_SUBTREE_TAGS:
            self._drop_depth += 1
        elif tag.lower() in _KEEP_TAGS:
            # Newline at the start of paragraph-like blocks so the
            # rendered text has visible breaks.
            self._pieces.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _DROP_SUBTREE_TAGS:
            self._drop_depth = max(0, self._drop_depth - 1)
        elif tag.lower() in _KEEP_TAGS:
            self._pieces.append("\n")

    def handle_data(self, data: str) -> None:
        if self._drop_depth > 0:
            return
        self._pieces.append(data)

    def text(self) -> str:
        raw = "".join(self._pieces)
        # Collapse runs of whitespace; preserve paragraph breaks as one blank line.
        lines = [line.strip() for line in raw.splitlines()]
        non_empty = [line for line in lines if line]
        return "\n\n".join(non_empty)


def _extract_text(content_type: str, body: bytes) -> str:
    """Dispatch on canonical content_type."""
    if content_type == "text/html":
        try:
            decoded = body.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            decoded = body.decode("latin-1", errors="replace")
        extractor = _TextExtractor()
        extractor.feed(decoded)
        return extractor.text()

    # text/plain and application/json: pass through verbatim.
    try:
        return body.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return body.decode("latin-1", errors="replace")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def ingest(url: str) -> IngestResult:
    """Fetch + validate + parse. Defenses run cheapest-first.

    Raises:
        DeniedHostError, FetchFailedError, UnsupportedContentTypeError,
        ContentTooLargeError — each maps to a distinct route formatter.
    """
    # Strip query string from log key — query may carry tokens.
    log_host = urlparse(url).hostname or "?"
    logger.info("url_ingest.start", extra={"host": log_host})

    # Defenses 1-3.
    _validate_url(url)

    # Defenses 4-5-6.
    try:
        async with _open_response_stream(url, _TIMEOUT_SECONDS) as response:
            if response.status_code >= 400:
                raise FetchFailedError(f"HTTP {response.status_code} from {url}")
            content_type_header = response.headers.get("content-type", "")
            content_type = _validate_content_type(url, content_type_header)
            body = await _read_with_limit(url, response)
    except httpx.TimeoutException as e:
        logger.warning("url_ingest.failure", extra={"host": log_host, "reason": "timeout"})
        raise FetchFailedError(f"timeout fetching {url}") from e
    except httpx.HTTPError as e:
        logger.warning("url_ingest.failure", extra={"host": log_host, "reason": type(e).__name__})
        raise FetchFailedError(f"fetch failed for {url}: {type(e).__name__}: {e}") from e
    except (DeniedHostError, FetchFailedError, UnsupportedContentTypeError, ContentTooLargeError):
        # Already-typed exceptions propagate verbatim; logging happens
        # at the catch site that has the right context.
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "url_ingest.failure",
            extra={"host": log_host, "reason": f"unexpected:{type(e).__name__}"},
        )
        raise FetchFailedError(f"unexpected error fetching {url}: {type(e).__name__}") from e

    text = _extract_text(content_type, body)
    result = IngestResult(
        raw_text=text,
        content_type=f"url_fetched/{content_type.split('/', 1)[1]}",
        byte_count=len(body),
    )
    logger.info(
        "url_ingest.success",
        extra={"host": log_host, "byte_count": result.byte_count, "content_type": content_type},
    )
    return result
