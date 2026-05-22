import json
import logging
from typing import Any, Dict

import requests

from assertion.engine import AssertionEngine
from executor.base import BaseExecutor

logger = logging.getLogger(__name__)

_TIMEOUT = 30


class ApiTestExecutor(BaseExecutor):
    """Executes API test cases by sending HTTP requests and running assertions."""

    def execute_single(self, case: Dict[str, Any]) -> Dict[str, Any]:
        test_id = case.get("test_id", "unknown")
        method = (case.get("method") or "GET").upper()
        url = self._build_url(case.get("url", ""))
        headers = case.get("request_head") or {}
        body = case.get("request_body") or {}
        expected_status = case.get("status_code")

        logger.info("[%s] %s %s", test_id, method, url)

        result = {
            "test_id": test_id,
            "api_name": case.get("api_name", ""),
            "method": method,
            "url": case.get("url", ""),
            "tag": case.get("tag", ""),
            "remark": case.get("remark", ""),
            "request_headers": dict(headers),
            "request_body": dict(body),
            "response_status": None,
            "response_body": None,
            "assertions": [],
            "passed": False,
            "error": None,
        }

        try:
            response = self._send_request(method, url, headers, body)
            result["response_status"] = response.status_code
            result["response_body"] = self._extract_body(response)

            assertions = AssertionEngine.run(response, case.get("assert_dict", {}))

            if expected_status is not None:
                status_match = int(expected_status) == response.status_code
                if not any(a["field"] == "status_code" for a in assertions):
                    assertions.insert(
                        0,
                        {
                            "field": "status_code",
                            "expected": int(expected_status),
                            "actual": response.status_code,
                            "passed": status_match,
                        },
                    )

            result["assertions"] = assertions
            result["passed"] = all(a["passed"] for a in assertions)

            if result["passed"]:
                logger.info("[%s] PASS", test_id)
            else:
                failed_fields = [a["field"] for a in assertions if not a["passed"]]
                logger.info("[%s] FAIL — assertions failed: %s", test_id, failed_fields)

        except requests.Timeout:
            result["error"] = f"Request timeout after {_TIMEOUT}s"
            logger.warning("[%s] %s", test_id, result["error"])
        except requests.ConnectionError as e:
            result["error"] = f"Connection error: {e}"
            logger.warning("[%s] %s", test_id, result["error"])
        except requests.RequestException as e:
            result["error"] = f"Request error: {e}"
            logger.warning("[%s] %s", test_id, result["error"])

        return result

    def _build_url(self, path: str) -> str:
        base = self.config.get("baseURL", "").rstrip("/")
        path = path.lstrip("/") if path.startswith("/") else path
        return f"{base}/{path}" if base else path

    def _send_request(
        self, method: str, url: str, headers: Dict, body: Dict
    ) -> requests.Response:
        kwargs: Dict[str, Any] = {"timeout": _TIMEOUT, "headers": headers}

        if method in ("GET", "DELETE"):
            if body:
                kwargs["params"] = body
        elif method in ("POST", "PUT", "PATCH"):
            kwargs["json"] = body
        else:
            if body:
                kwargs["json"] = body

        return requests.request(method, url, **kwargs)

    @staticmethod
    def _extract_body(response: requests.Response) -> Any:
        try:
            return response.json()
        except (ValueError, requests.JSONDecodeError):
            return response.text
