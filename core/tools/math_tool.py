"""Tier 0: safe math expression evaluation."""

from __future__ import annotations

import ast
import operator
from typing import Any

from core.policy import ToolTier
from core.tools.base import BaseTool, ToolExecutionResult

# Only allow a small set of operators
_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def _eval_node(node: ast.AST) -> float | int:
    if isinstance(node, ast.Constant):
        val = node.value
        if isinstance(val, (int, float)):
            return val
        raise ValueError("Only numbers allowed")
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        op = _SAFE_OPS.get(type(node.op))
        if op is None:
            raise ValueError("Operator not allowed")
        return op(left, right)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_node(node.operand)
    raise ValueError("Invalid expression")


def safe_eval(expr: str) -> float | int:
    """Evaluate a numeric expression. Only numbers and + - * / // ** and unary minus."""
    tree = ast.parse(expr, mode="eval")
    if not isinstance(tree.body, (ast.BinOp, ast.UnaryOp, ast.Constant)):
        raise ValueError("Only simple math expressions allowed")
    return _eval_node(tree.body)


class MathTool(BaseTool):
    name = "math"
    tier = ToolTier.TIER0

    def execute(self, payload: dict[str, Any]) -> ToolExecutionResult:
        expr = (payload.get("expression") or payload.get("expr") or "").strip()
        if not expr:
            return ToolExecutionResult(ok=False, output={"error": "Missing 'expression' or 'expr'"})
        try:
            result = safe_eval(expr)
            return ToolExecutionResult(ok=True, output={"expression": expr, "result": result})
        except (ValueError, SyntaxError) as e:
            return ToolExecutionResult(ok=False, output={"error": str(e)})
