import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from resolvers.path_resolver import (
    resolve_path,
    resolve_length,
    resolve_path_wildcard,
    resolve_sum,
    resolve_sum_product,
    _Missing,
)

logger = logging.getLogger(__name__)

_FUNC_RE = re.compile(r"^(SUM_PRODUCT|SUM)\((.+)\)$")

# 运算符模式 — 从共享 schema 包导入
# Operator patterns — imported from shared schema package
from flow_forge_schemas import OPERATOR_LIST

_OPERATOR_PATTERNS = [
    (re.compile(op["pattern"]), op["name"], op["name"] not in ("is_not_null", "is_null"))
    for op in OPERATOR_LIST
]


class AssertRulesEngine:

    @staticmethod
    def run(response: Any, assert_rules: List[str]) -> List[Dict[str, Any]]:
        """Execute a list of assertion rule strings against an HTTP response.

        Returns a list of result dicts with keys: field, expected, actual, passed.
        """
        if not assert_rules:
            return []

        try:
            data = response.json()
        except (ValueError, AttributeError):
            data = None

        results = []
        for rule in assert_rules:
            try:
                left, op, expected = AssertRulesEngine._parse_rule(rule)
                actual = AssertRulesEngine._eval_expression(left, data)
                if op not in ("is_null", "is_not_null"):
                    expected = AssertRulesEngine._eval_expected(expected, data)
                passed = AssertRulesEngine._execute_op(actual, op, expected)
                results.append({
                    "field": rule,
                    "expected": expected,
                    "actual": actual,
                    "passed": passed,
                })
            except Exception as e:
                logger.warning("Assert rule evaluation failed: '%s' — %s", rule, e)
                results.append({
                    "field": rule,
                    "expected": None,
                    "actual": f"<error: {e}>",
                    "passed": False,
                })
        return results

    @staticmethod
    def _parse_rule(rule: str) -> Tuple[str, str, Optional[str]]:
        """Parse a rule string into (left_expression, operator, expected_value)."""
        rule = rule.strip()

        for pattern, op, has_expected in _OPERATOR_PATTERNS:
            m = pattern.search(rule)
            if m:
                left = rule[:m.start()].strip()
                expected = m.group(1).strip() if has_expected else None
                return (left, op, expected)

        raise ValueError(f"Unable to parse assertion rule, no operator matched: {rule}")

    @staticmethod
    def _eval_expression(expr: str, data: Any) -> Any:
        """Evaluate a left-side expression: path, function call, or .length()."""
        expr = expr.strip()

        m = _FUNC_RE.match(expr)
        if m:
            func_name = m.group(1)
            args_str = m.group(2)
            args = [a.strip() for a in args_str.split(",")]
            if func_name == "SUM":
                return resolve_sum(data, args[0])
            elif func_name == "SUM_PRODUCT":
                if len(args) >= 2:
                    return resolve_sum_product(data, args[0], args[1])

        if expr.endswith(".length()"):
            return resolve_length(data, expr)

        result = resolve_path(data, expr)
        if isinstance(result, _Missing):
            raise ValueError(f"Path not found: {expr}")
        return result

    @staticmethod
    def _eval_expected(expr: str, data: Any) -> Any:
        """Evaluate a right-side expression: JSON literal, function call, or raw string."""
        expr = expr.strip()

        m = _FUNC_RE.match(expr)
        if m:
            return AssertRulesEngine._eval_expression(expr, data)

        try:
            return json.loads(expr)
        except (json.JSONDecodeError, ValueError):
            pass

        return expr

    @staticmethod
    def _execute_op(actual: Any, op: str, expected: Any) -> bool:
        """Execute a comparison operator."""
        try:
            if op == "==":
                return actual == expected
            elif op == "!=":
                return actual != expected
            elif op == ">":
                return float(actual) > float(expected)
            elif op == ">=":
                return float(actual) >= float(expected)
            elif op == "<":
                return float(actual) < float(expected)
            elif op == "<=":
                return float(actual) <= float(expected)
            elif op == "=~":
                return re.match(str(expected), str(actual)) is not None
            elif op == "in":
                return actual in expected if expected is not None else False
            elif op == "contains":
                return expected in actual if actual is not None else False
            elif op == "not_contains":
                return expected not in actual if actual is not None else True
            elif op == "is_null":
                return actual is None
            elif op == "is_not_null":
                return actual is not None
            elif op == "typeof":
                type_map = {
                    "int": int, "float": float, "str": str, "bool": bool,
                    "list": list, "dict": dict, "int_or_float": (int, float),
                }
                expected_type = type_map.get(str(expected).lower(), str)
                return isinstance(actual, expected_type)
            else:
                return False
        except (TypeError, ValueError) as e:
            logger.debug("Operator '%s' failed: %s", op, e)
            return False
