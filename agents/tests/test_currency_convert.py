"""currency_convert tool: shape + direction."""

from __future__ import annotations

import json

import pytest

from tools.currency_convert import currency_convert_tool


def test_returns_expected_shape() -> None:
    out = json.loads(currency_convert_tool._run(amount=100, from_currency="USD", to_currency="INR"))
    assert out["amount"] == 100
    assert out["from_currency"] == "USD"
    assert out["to_currency"] == "INR"
    assert out["is_stub"] is True
    assert isinstance(out["converted"], float)
    assert isinstance(out["rate_via_usd"], float)


def test_usd_to_inr_is_more() -> None:
    """100 USD should be more than 100 INR."""
    out = json.loads(currency_convert_tool._run(amount=100, from_currency="USD", to_currency="INR"))
    assert out["converted"] > 100


def test_inr_to_usd_is_less() -> None:
    """100 INR should be less than 100 USD."""
    out = json.loads(currency_convert_tool._run(amount=100, from_currency="INR", to_currency="USD"))
    assert out["converted"] < 100


def test_same_currency_roundtrip() -> None:
    out = json.loads(currency_convert_tool._run(amount=42, from_currency="EUR", to_currency="EUR"))
    assert out["converted"] == 42


def test_lowercase_input_normalized() -> None:
    out = json.loads(currency_convert_tool._run(amount=100, from_currency="usd", to_currency="inr"))
    assert out["from_currency"] == "USD"
    assert out["to_currency"] == "INR"


def test_unknown_currency_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        currency_convert_tool._run(amount=100, from_currency="XYZ", to_currency="USD")
