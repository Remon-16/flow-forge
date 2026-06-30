from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import requests

from resolvers.var_resolver import (
    find_all_placeholders,
    has_curly_placeholders,
    has_placeholders,
    resolve_curly_placeholders,
    resolve_placeholders,
)

logger = logging.getLogger(__name__)


class BaseExecutor(ABC):
    """Abstract executor with built-in thread-pool management."""

    _TIMEOUT: int = 30

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.results: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Thread pool
    # ------------------------------------------------------------------

    def run(self, cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not cases:
            logger.warning("No test cases to execute")
            return []

        max_workers = self.config.get("maxThread", 5)
        logger.info("Starting execution with %d workers for %d cases", max_workers, len(cases))

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(self._worker, case): case for case in cases}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    logger.exception("Unexpected error in worker thread")

        return self.results

    def _worker(self, case: Dict[str, Any]) -> None:
        test_id = case.get("test_id", "unknown")
        try:
            result = self.execute_single(case)
        except Exception as exc:
            logger.exception("Unhandled error executing case '%s'", test_id)
            result = self._build_error_result(case, str(exc))

        with self._lock:
            self.results.append(result)

    @abstractmethod
    def execute_single(self, case: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single test case. Must return a standardized result dict."""

    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_url_placeholders(url: str, body: Dict[str, Any]):
        """Resolve #{varName} and {varName} placeholders in the URL from the request body.

        Values found in the body are consumed (removed) so they are not also
        sent as query parameters or JSON fields.  The removed fields are
        recorded in ``cleared_params`` so that a pre-processor can restore
        them if needed.

        Returns ``(resolved_url, remaining_body, cleared_params)``.
        """
        has_hash = has_placeholders(url)
        has_curly = has_curly_placeholders(url)

        if not has_hash and not has_curly:
            return url, body, {}

        body = dict(body)  # shallow copy so we can pop without mutating caller
        cleared: Dict[str, str] = {}

        # Step 1: find all matches and collect values (don't pop yet)
        consumed: Dict[str, str] = {}
        for var_name in find_all_placeholders(url):
            if var_name in body:
                consumed[var_name] = str(body[var_name])

        # Step 2: substitute all placeholders (hash and curly)
        def resolver(var_name: str) -> Optional[str]:
            return consumed.get(var_name)

        if has_hash:
            url = resolve_placeholders(url, resolver)
        if has_curly:
            url = resolve_curly_placeholders(url, resolver)

        # Step 3: remove consumed keys from body
        cleared = dict(consumed)
        for key in consumed:
            body.pop(key, None)

        return url, body, cleared

    @staticmethod
    def _build_url(base_url: str, path: str) -> str:
        base = base_url.rstrip("/") if base_url else ""
        path = path.lstrip("/") if path and path.startswith("/") else path
        return f"{base}/{path}" if base else path

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _send_request(
        self, method: str, url: str, headers: Dict, body: Dict
    ) -> requests.Response:
        kwargs: Dict[str, Any] = {"timeout": self._TIMEOUT, "headers": headers}

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

    # ------------------------------------------------------------------
    # Result factory methods
    # ------------------------------------------------------------------

    @staticmethod
    def _build_result(
        case: Dict[str, Any],
        **overrides,
    ) -> Dict[str, Any]:
        """Build a standardized result dict. Subclasses pass **overrides for
        extra fields (e.g. ``step_id`` for biz flow steps)."""
        result: Dict[str, Any] = {
            "test_id": case.get("test_id", "unknown"),
            "api_name": case.get("api_name", ""),
            "app_name": case.get("app_name", ""),
            "method": case.get("method", ""),
            "url": case.get("url", ""),
            "base_url": "",
            "tag": case.get("tag", ""),
            "remark": case.get("remark", ""),
            "request_headers": {},
            "request_body": {},
            "response_status": None,
            "response_body": None,
            "assertions": [],
            "preprocessor_results": [],
            "postprocessor_results": [],
            "passed": False,
            "error": None,
        }
        result.update(overrides)
        return result

    @staticmethod
    def _build_error_result(case: Dict[str, Any], error: str) -> Dict[str, Any]:
        return BaseExecutor._build_result(
            case,
            base_url=case.get("base_url", ""),
            error=error,
            passed=False,
        )

    # ------------------------------------------------------------------
    # Processor orchestration
    # ------------------------------------------------------------------

    @staticmethod
    def _load_processors(preprocessors: list, postprocessors: list):
        """Lazy-load processor modules and return global config.

        Returns None if neither preprocessors nor postprocessors are configured.
        """
        if not preprocessors and not postprocessors:
            return None
        from processors.loader import discover_processors
        from config.config_manager import get_all
        discover_processors()
        return get_all()

    @staticmethod
    def _run_preprocessors(
        preprocessors: list,
        headers: Dict,
        body: Dict,
        global_config: dict | None,
    ):
        """Run preprocessors, returning ``(headers, body, preprocessor_results)``.

        Raises ProcessorError on failure.
        """
        from processors.runner import run_preprocessors
        return run_preprocessors(
            {
                "request_head": headers,
                "request_body": body,
                "preprocessors": preprocessors,
            },
            global_config,
        )

    @staticmethod
    def _run_postprocessors(
        postprocessors: list,
        headers: Dict,
        body: Dict,
        response: requests.Response,
        global_config: dict | None,
    ):
        """Run postprocessors, returning postprocessor_results list.

        Raises ProcessorError on failure.
        """
        from processors.runner import run_postprocessors
        return run_postprocessors(
            {
                "request_head": headers,
                "request_body": body,
                "postprocessors": postprocessors,
            },
            response,
            global_config,
        )

    # ------------------------------------------------------------------
    # Assertions
    # ------------------------------------------------------------------

    @staticmethod
    def _run_assertions(
        response: requests.Response,
        case: Dict[str, Any],
    ) -> List[Dict]:
        """Run assert_dict + assert_rules, with optional status_code check.

        Returns a list of assertion result dicts.
        """
        from assertion.engine import AssertionEngine

        assertions = AssertionEngine.run(
            response,
            case.get("assert_dict", {}),
            case.get("assert_rules", []),
        )

        expected_status = case.get("status_code")
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

        return assertions
