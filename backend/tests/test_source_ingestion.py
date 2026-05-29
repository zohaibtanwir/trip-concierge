"""source_ingestion — URL fetch with 6-defense SSRF stack.

Slice 3.4b commit 2. Each test pins exactly one defense. The
asymmetry vs slice 3.4a tests is deliberate: defenses are independent
contracts that a future refactor could silently disable one at a time.
If only the happy-path test exists, the suite is green while three
defenses are off.

Defense order matches source_ingestion.py module docstring:
1. Scheme allowlist (http/https)
2. _DENIED_HOSTS canonical list (metadata endpoints, localhost, 0.0.0.0)
3. DNS resolve + IP-range validation (private/loopback/link-local blocked)
4. 10s total timeout
5. Content-Type filter (text/html, text/plain, application/json)
6. 2 MB streaming size limit (early abort)

Tests use a patched seam (_open_response_stream) for injected
responses rather than mocking the httpx context-manager chain
directly — keeps test code readable and resilient to httpx API
churn.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from app.services import source_ingestion
from app.services.source_ingestion import (
    ContentTooLargeError,
    DeniedHostError,
    FetchFailedError,
    IngestResult,
    UnsupportedContentTypeError,
    ingest,
)


class _FakeResponse:
    """Duck-type for httpx.Response — only the attrs source_ingestion reads."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        chunks: list[bytes] | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {"content-type": "text/html; charset=utf-8"}
        self._chunks = chunks or [b"<html><body><p>default</p></body></html>"]

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.com")
            response = httpx.Response(status_code=self.status_code, request=request)
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=request,
                response=response,
            )

    async def aiter_bytes(self, chunk_size: int = 8192) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


def _patch_stream(monkeypatch: pytest.MonkeyPatch, response: _FakeResponse) -> None:
    """Replace _open_response_stream with an async CM that yields the fake."""

    @asynccontextmanager
    async def fake_open(url: str, timeout: float) -> AsyncIterator[_FakeResponse]:
        del url, timeout
        yield response

    monkeypatch.setattr(source_ingestion, "_open_response_stream", fake_open)


def _patch_stream_raises(monkeypatch: pytest.MonkeyPatch, exc: BaseException) -> None:
    """Replace _open_response_stream with one that raises before yielding."""

    @asynccontextmanager
    async def fake_open(url: str, timeout: float) -> AsyncIterator[Any]:
        del url, timeout
        raise exc
        yield  # pragma: no cover  # noqa: B901

    monkeypatch.setattr(source_ingestion, "_open_response_stream", fake_open)


def _patch_dns(monkeypatch: pytest.MonkeyPatch, ip: str = "93.184.216.34") -> None:
    """Default IP is example.com's public address — passes defense 3."""
    monkeypatch.setattr(source_ingestion.socket, "gethostbyname", lambda _host: ip)


async def test_ingest_happy_path_extracts_text_and_returns_ingest_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense stack quiet, HTML extractor produces the expected text.
    The assertion is intentionally loose ("extracted SOMETHING reasonable"
    not "exact byte-for-byte match") — the stdlib HTMLParser path is
    crude by design; v1.0c per-site parsers (ticket a8c) is the path
    to better extraction.
    """
    _patch_dns(monkeypatch)
    html = (
        b"<html><head><script>evil()</script><style>x{}</style></head>"
        b"<body><nav>SiteNav</nav>"
        b"<main><p>Goa locals recommend Vinayak Family Restaurant.</p>"
        b"<p>The prawn curry is outstanding.</p></main>"
        b"<footer>copyright</footer></body></html>"
    )
    _patch_stream(
        monkeypatch,
        _FakeResponse(headers={"content-type": "text/html; charset=utf-8"}, chunks=[html]),
    )

    result = await ingest("https://example.com/goa-tips")

    assert isinstance(result, IngestResult)
    assert "Vinayak Family Restaurant" in result.raw_text
    assert "prawn curry" in result.raw_text
    # Script and style content must NOT survive extraction.
    assert "evil()" not in result.raw_text
    assert "x{}" not in result.raw_text
    # Nav/footer boilerplate dropped.
    assert "SiteNav" not in result.raw_text
    assert "copyright" not in result.raw_text
    # content_type captured.
    assert result.content_type.startswith("url_fetched")
    assert result.byte_count > 0


async def test_ingest_rejects_non_http_scheme_before_any_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense 1: file://, gopher://, ftp:// rejected at URL parse,
    before DNS or fetch. Cheapest defense; runs first.
    """
    # If defense 1 fires, _open_response_stream must NOT be called.
    called: list[str] = []

    @asynccontextmanager
    async def trap(url: str, timeout: float) -> AsyncIterator[Any]:
        called.append(url)
        raise AssertionError("defense 1 failed — fetch attempted on non-http scheme")
        yield  # pragma: no cover  # noqa: B901

    monkeypatch.setattr(source_ingestion, "_open_response_stream", trap)

    with pytest.raises(DeniedHostError) as exc:
        await ingest("file:///etc/passwd")

    assert "scheme" in str(exc.value).lower()
    assert not called, "no network call should happen on bad scheme"


async def test_ingest_rejects_canonical_denied_host_before_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense 2: _DENIED_HOSTS check fires before DNS. Catches
    metadata.google.internal, 169.254.169.254, localhost, 0.0.0.0
    on string compare alone — belt-and-suspenders alongside defense 3.
    """

    def trap_dns(_host: str) -> str:
        raise AssertionError("defense 2 failed — DNS resolution attempted on denied host")

    monkeypatch.setattr(source_ingestion.socket, "gethostbyname", trap_dns)

    with pytest.raises(DeniedHostError) as exc:
        await ingest("http://localhost/api")

    assert "denied host" in str(exc.value).lower() or "localhost" in str(exc.value).lower()


async def test_ingest_rejects_private_ip_after_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense 3: hostname resolves to a private IP → DeniedHostError.
    Catches the classic SSRF: attacker-controlled DNS returning an
    RFC1918 address even though the URL has a public-looking hostname.
    """
    _patch_dns(monkeypatch, ip="192.168.1.1")

    @asynccontextmanager
    async def trap(url: str, timeout: float) -> AsyncIterator[Any]:
        raise AssertionError("defense 3 failed — fetch attempted on private IP")
        yield  # pragma: no cover  # noqa: B901

    monkeypatch.setattr(source_ingestion, "_open_response_stream", trap)

    with pytest.raises(DeniedHostError) as exc:
        await ingest("http://internal.corp/api")

    msg = str(exc.value).lower()
    assert "ip" in msg or "192.168" in msg


async def test_ingest_surfaces_timeout_as_fetch_failed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense 4: 10s ceiling. httpx.TimeoutException → FetchFailedError
    with reason='timeout' (string the formatter parses for distinct UX).
    """
    _patch_dns(monkeypatch)
    _patch_stream_raises(monkeypatch, httpx.TimeoutException("timed out", request=None))

    with pytest.raises(FetchFailedError) as exc:
        await ingest("https://example.com/slow")

    assert "timeout" in str(exc.value).lower()


async def test_ingest_rejects_unsupported_content_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense 5: Content-Type allowlist. image/png, video/*, application/pdf
    rejected at header time before reading the body.
    """
    _patch_dns(monkeypatch)
    _patch_stream(
        monkeypatch,
        _FakeResponse(
            headers={"content-type": "image/png"},
            chunks=[b"\x89PNG\r\n\x1a\n"],  # never read
        ),
    )

    with pytest.raises(UnsupportedContentTypeError) as exc:
        await ingest("https://example.com/photo.png")

    assert "image/png" in str(exc.value).lower()


async def test_ingest_aborts_on_body_exceeding_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense 6: streaming size limit. Body that would exceed
    MAX_BYTES (2 MB) raises ContentTooLargeError mid-stream, before
    the full payload reaches memory.
    """
    _patch_dns(monkeypatch)
    # 5 chunks × 600 KB = 3 MB. Exceeds the 2 MB cap mid-stream.
    big_chunk = b"x" * (600 * 1024)
    _patch_stream(
        monkeypatch,
        _FakeResponse(
            headers={"content-type": "text/plain"},
            chunks=[big_chunk] * 5,
        ),
    )

    with pytest.raises(ContentTooLargeError) as exc:
        await ingest("https://example.com/huge.txt")

    assert exc.value.byte_count > 2_000_000
