"""Currency conversion with rough static rates.

This is a stub. Real FX would come from an API in production; this exists so
the Auditor can do approximate cross-currency math during planning without
external network calls. The output always carries `is_stub: true` so callers
know not to trust precision below a few percent.
"""

from __future__ import annotations

import json
import logging

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Indicative rates vs USD as of 2026-05; intentionally not maintained live.
_RATES_VS_USD: dict[str, float] = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.78,
    "INR": 83.0,
    "JPY": 150.0,
    "AUD": 1.51,
    "CAD": 1.36,
    "CNY": 7.20,
    "SGD": 1.34,
    "THB": 35.0,
    "AED": 3.67,
}


class CurrencyConvertInput(BaseModel):
    amount: float = Field(ge=0)
    from_currency: str = Field(min_length=3, max_length=3)
    to_currency: str = Field(min_length=3, max_length=3)


class CurrencyConvertTool(BaseTool):
    name: str = "currency_convert"
    description: str = (
        "Convert an amount between currencies using rough static rates. Output "
        "carries `is_stub: true` because these rates aren't live — use only for "
        "directional checks (e.g. is 40000 INR roughly within a USD budget cap?), "
        "not for precise quotes. Supported currencies: USD, EUR, GBP, INR, JPY, "
        "AUD, CAD, CNY, SGD, THB, AED."
    )
    args_schema: type[BaseModel] = CurrencyConvertInput

    def _run(self, amount: float, from_currency: str, to_currency: str) -> str:
        f = from_currency.upper()
        t = to_currency.upper()
        if f not in _RATES_VS_USD:
            raise ValueError(f"unsupported from_currency: {from_currency!r}")
        if t not in _RATES_VS_USD:
            raise ValueError(f"unsupported to_currency: {to_currency!r}")
        usd_amount = amount / _RATES_VS_USD[f]
        target_amount = usd_amount * _RATES_VS_USD[t]
        rate = _RATES_VS_USD[t] / _RATES_VS_USD[f]
        logger.info(
            "currency_convert.call",
            extra={
                "amount": amount,
                "from": f,
                "to": t,
                "result": round(target_amount, 2),
            },
        )
        return json.dumps(
            {
                "amount": amount,
                "from_currency": f,
                "to_currency": t,
                "converted": round(target_amount, 2),
                "rate_via_usd": round(rate, 4),
                "is_stub": True,
            }
        )


currency_convert_tool = CurrencyConvertTool()
