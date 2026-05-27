"""calculator tool: safe expressions accepted, unsafe rejected."""

from __future__ import annotations

import pytest

from trip_agents.tools.calculator import calculator_tool


def test_basic_arithmetic() -> None:
    assert calculator_tool._run("2 + 2") == "4"
    assert calculator_tool._run("(10 + 5) * 3") == "45"
    assert calculator_tool._run("100 / 4") == "25.0"
    assert calculator_tool._run("100 % 7") == "2"


def test_decimal() -> None:
    assert calculator_tool._run("1.5 * 2") == "3.0"


def test_rejects_names() -> None:
    with pytest.raises(ValueError, match="only accepts"):
        calculator_tool._run("os.system('rm -rf /')")


def test_rejects_function_calls() -> None:
    with pytest.raises(ValueError, match="only accepts"):
        calculator_tool._run("__import__('os')")


def test_rejects_empty() -> None:
    with pytest.raises(ValueError, match="only accepts"):
        calculator_tool._run("")


def test_rejects_string_concat() -> None:
    with pytest.raises(ValueError, match="only accepts"):
        calculator_tool._run("'a' + 'b'")
