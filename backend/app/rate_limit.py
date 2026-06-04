"""Shared slowapi Limiter instance.

Lives in its own module to avoid the circular import that would arise
from `routes/auth.py` ↔ `main.py` if Limiter were declared in either.

slowapi 0.1.9 was the version current at slice 4.1b time (published
2026 Feb 5). The package is mature but releases slowly — if a CVE
ever surfaces, expect to evaluate alternatives (fastapi-limiter
needs Redis, starlette-limiter is younger). For v1.0a we accept the
trade-off.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
