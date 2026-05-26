"""Safe arithmetic eval. The LLM hands in an expression string; we lock
it down to digits + - * / ( ) % . _ and evaluate. Anything else raises.

Per .claude/rules/agent-code-style.md rule #3: tool is a pure function with
typed input/output and structured logging at start/success/failure.
"""

from __future__ import annotations

import logging
import re

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Digits, basic operators, parens, decimal points, whitespace. No names, no calls.
_SAFE_RE = re.compile(r"^[\d\s\.\+\-\*\/\(\)\%]+$")


class CalculatorInput(BaseModel):
    expression: str = Field(
        description="Arithmetic expression. Only digits, + - * / ( ) % and decimal points.",
    )


class CalculatorTool(BaseTool):
    name: str = "calculator"
    description: str = (
        "Evaluate a basic arithmetic expression. Use this when summing per-day "
        "costs, applying a percentage tax/tip, or doing any math the user has "
        "asked you to be precise about. Returns the numeric result as a string. "
        "Only supports + - * / ( ) % on plain numbers — no variables or "
        "function calls."
    )
    args_schema: type[BaseModel] = CalculatorInput

    def _run(self, expression: str) -> str:
        logger.info("calculator.call", extra={"expression": expression})
        if not _SAFE_RE.match(expression):
            logger.warning("calculator.rejected", extra={"expression": expression})
            raise ValueError(f"calculator only accepts digits + - * / ( ) %: got {expression!r}")
        try:
            result = eval(expression, {"__builtins__": {}}, {})  # noqa: S307
        except (SyntaxError, ZeroDivisionError, OverflowError, ValueError) as e:
            logger.warning("calculator.error", extra={"expression": expression, "err": str(e)})
            raise ValueError(f"could not evaluate {expression!r}: {e}") from e
        logger.info("calculator.success", extra={"result": result})
        return str(result)


calculator_tool = CalculatorTool()
