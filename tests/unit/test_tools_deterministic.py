from __future__ import annotations

import datetime

from aura.tools.builtins import CalculatorTool, DateTimeTool, SystemStatusTool


def test_datetime_tool_execution() -> None:
    tool = DateTimeTool()

    res_now = tool.execute(action="now")
    assert res_now.success is True
    assert isinstance(res_now.output, dict)
    assert "datetime_formatted" in res_now.output
    assert "date" in res_now.output
    assert "time" in res_now.output

    res_time = tool.execute(action="time")
    assert res_time.success is True
    assert isinstance(res_time.output, str)
    assert len(res_time.output.split(":")) == 3

    res_date = tool.execute(action="date")
    assert res_date.success is True
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    assert res_date.output == today_str


def test_calculator_tool_valid_expressions() -> None:
    calc = CalculatorTool()

    assert calc.execute(expression="125 * 37").output == 4625
    assert calc.execute(expression="(25 + 5) / 2").output == 15.0
    assert calc.execute(expression="2 ** 8").output == 256
    assert calc.execute(expression="100 % 30").output == 10
    assert calc.execute(expression="-10 + +5").output == -5


def test_calculator_tool_security_rejections() -> None:
    calc = CalculatorTool()

    # Division by zero
    res_zero = calc.execute(expression="10 / 0")
    assert res_zero.success is False
    assert "Division by zero" in res_zero.error  # type: ignore[operator]

    # Malicious function call attempts
    res_func = calc.execute(expression="__import__('os').system('dir')")
    assert res_func.success is False
    assert "unauthorized AST node" in res_func.error or "Invalid math expression" in res_func.error  # type: ignore[operator]

    # Attribute access attempts
    res_attr = calc.execute(expression="(1).bit_length()")
    assert res_attr.success is False

    # Variable lookup attempts
    res_var = calc.execute(expression="x + 5")
    assert res_var.success is False


def test_system_status_tool_execution() -> None:
    status_tool = SystemStatusTool()
    res = status_tool.execute()
    assert res.success is True
    assert "state" in res.output
    assert res.output["is_running"] is True
