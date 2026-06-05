import logging
import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class BaseExecutor(ABC):
    """Abstract executor with built-in thread-pool management."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.results: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

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

    @staticmethod
    def _build_error_result(case: Dict[str, Any], error: str) -> Dict[str, Any]:
        return {
            "test_id": case.get("test_id", "unknown"),
            "api_name": case.get("api_name", "unknown"),
            "app_name": case.get("app_name", ""),
            "method": case.get("method", ""),
            "url": case.get("url", ""),
            "base_url": case.get("base_url", ""),
            "tag": case.get("tag", ""),
            "remark": case.get("remark", ""),
            "passed": False,
            "error": error,
            "request_headers": {},
            "request_body": {},
            "response_status": None,
            "response_body": None,
            "assertions": [],
        }
