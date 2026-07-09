import logging
from typing import Any, Dict, List

from resolvers.path_resolver import resolve_path, _Missing

logger = logging.getLogger(__name__)


class AssertionEngine:
    """Runs field-level assertions against an HTTP response."""

    @staticmethod
    def run(response: Any, assert_dict: Dict[str, Any],
            assert_rules: List[str] = None) -> List[Dict[str, Any]]:
        """Execute all assertions in assert_dict and assert_rules against the response.

        Returns a list of assertion result dicts, each with keys:
            field, expected, actual, passed
        """
        results = []

        if assert_dict:
            response_json = AssertionEngine._try_parse_json(response)

            for field, expected in assert_dict.items():
                if field == "status_code":
                    results.append(
                        AssertionEngine._assert_status_code(response.status_code, expected)
                    )
                else:
                    results.append(
                        AssertionEngine._assert_field(response_json, field, expected)
                    )

        if assert_rules:
            from assertion.rules_engine import AssertRulesEngine
            results.extend(AssertRulesEngine.run(response, assert_rules))

        return results

    @staticmethod
    def _try_parse_json(response: Any) -> Any:
        try:
            return response.json()
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _assert_status_code(actual: int, expected: Any) -> Dict[str, Any]:
        try:
            expected_int = int(expected)
        except (ValueError, TypeError):
            expected_int = expected
        passed = actual == expected_int
        return {
            "field": "status_code",
            "expected": expected_int,
            "actual": actual,
            "passed": passed,
        }

    @staticmethod
    def _assert_field(
        data: Any, field_path: str, expected: Any
    ) -> Dict[str, Any]:
        if data is None:
            return {
                "field": field_path,
                "expected": expected,
                "actual": "<non-JSON body>",
                "passed": False,
            }

        actual = resolve_path(data, field_path)

        if isinstance(actual, _Missing):
            return {
                "field": field_path,
                "expected": expected,
                "actual": "<not found>",
                "passed": False,
            }

        passed = str(actual) == str(expected)
        return {
            "field": field_path,
            "expected": expected,
            "actual": actual,
            "passed": passed,
        }
