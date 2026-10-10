"""Evaluate the small arithmetic language used by the demo calculator."""
import ast
import math
import operator

_BINARY = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_LIMIT = 1_000_000_000_000


def calculate(expression):
    """Accept bounded numbers and arithmetic, without executing Python code."""
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 256:
        raise ValueError("Use an arithmetic expression of at most 256 characters.")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except (SyntaxError, ValueError, RecursionError):
        raise ValueError("Use a valid arithmetic expression.") from None
    if sum(1 for _ in ast.walk(tree)) > 128:
        raise ValueError("The expression has too many operations.")

    def bounded(value):
        if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > _LIMIT:
            raise ValueError("Numbers and results must be finite and no larger than 1e12.")
        return value

    def evaluate(node, depth=0):
        if depth > 16:
            raise ValueError("The expression is nested too deeply.")
        if isinstance(node, ast.Constant):
            return bounded(node.value)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return bounded(_UNARY[type(node.op)](evaluate(node.operand, depth + 1)))
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            left = evaluate(node.left, depth + 1)
            right = evaluate(node.right, depth + 1)
            if isinstance(node.op, ast.Pow) and abs(right) > 12:
                raise ValueError("Exponents must be between -12 and 12.")
            try:
                return bounded(_BINARY[type(node.op)](left, right))
            except (ZeroDivisionError, OverflowError):
                raise ValueError("The arithmetic operation cannot be evaluated.") from None
        raise ValueError("Only numbers and arithmetic operators are supported.")

    return evaluate(tree.body)
