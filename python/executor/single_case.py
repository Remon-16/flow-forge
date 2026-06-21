import logging
from typing import Any, Dict

import requests

from auth.login_manager import LoginManager
from config.config_manager import get_app
from executor.base import BaseExecutor
from processors.base import ProcessorError

logger = logging.getLogger(__name__)


class SingleCaseExecutor(BaseExecutor):
    """单接口用例执行器。Executes single API test cases via HTTP requests and assertions."""

    def execute_single(self, case: Dict[str, Any]) -> Dict[str, Any]:
        test_id = case.get("test_id", "unknown")
        app_name = case.get("app_name") or ""
        method = (case.get("method") or "GET").upper()
        path = case.get("url", "")

        if "<URL not exist>" in path:
            return self._build_result(case, error=f"URL not found in API documentation: {path}")

        headers, body, url, base_url = self._prepare_request(case, app_name, method, path)

        result = self._build_result(
            case,
            base_url=base_url,
            method=method,
            request_headers=dict(headers),
            request_body=dict(body),
        )

        logger.info("[%s] %s %s (app=%s)", test_id, method, url, app_name)

        return self._execute_request(result, case, test_id, url, headers, body, app_name)

    def _prepare_request(
        self, case: Dict[str, Any], app_name: str, method: str, path: str
    ):
        """Extract headers, body and build URL from case and app config.

        Returns ``(headers, body, url, base_url)``.
        """
        headers = dict(case.get("request_head") or {})
        body = dict(case.get("request_body") or {})

        app_config = get_app(app_name) if app_name else {}
        base_url = app_config.get("baseURL", "") if app_config else ""
        url = self._build_url(base_url, path)
        url, body = self._resolve_url_placeholders(url, body)
        return headers, body, url, base_url

    def _execute_request(
        self,
        result: Dict[str, Any],
        case: Dict[str, Any],
        test_id: str,
        url: str,
        headers: Dict,
        body: Dict,
        app_name: str,
    ) -> Dict[str, Any]:
        """Token resolution → preprocessors → HTTP request → assertions → postprocessors."""

        # ---- Token / Login ----
        app_config = get_app(app_name) if app_name else {}
        resolved_headers, token_error = LoginManager.resolve_token(app_config, headers)
        if token_error:
            result["error"] = token_error
            logger.warning("[%s] Token resolution failed: %s", test_id, token_error)
            return result

        headers = resolved_headers
        result["request_headers"] = dict(headers)

        # ---- PreProcessors ----
        preprocessors = case.get("preprocessors") or []
        postprocessors = case.get("postprocessors") or []
        global_config = self._load_processors(preprocessors, postprocessors)

        if preprocessors:
            try:
                headers, body, preprocessor_results = self._run_preprocessors(
                    preprocessors, headers, body, global_config)
                result["request_headers"] = dict(headers)
                result["request_body"] = dict(body)
                result["preprocessor_results"] = preprocessor_results
            except ProcessorError as e:
                result["error"] = f"[{e.processor_name}] {e}"
                result["passed"] = False
                return result

        # ---- HTTP request + Assertions ----
        try:
            response = self._send_request(case.get("method", "GET").upper(), url, headers, body)
            result["response_status"] = response.status_code
            result["response_body"] = self._extract_body(response)

            assertions = self._run_assertions(response, case)
            result["assertions"] = assertions

            # ---- PostProcessors ----
            if postprocessors and global_config is not None:
                try:
                    result["postprocessor_results"] = self._run_postprocessors(
                        postprocessors, headers, body, response, global_config)
                except ProcessorError as e:
                    result["error"] = f"[{e.processor_name}] {e}"
                    result["passed"] = False

            result["passed"] = all(a["passed"] for a in assertions) if not result.get("error") else False

            if result["passed"]:
                logger.info("[%s] PASS", test_id)
            else:
                failed_fields = [a["field"] for a in assertions if not a["passed"]]
                logger.info("[%s] FAIL — assertions failed: %s", test_id, failed_fields)

        except requests.Timeout:
            result["error"] = f"Request timeout after {self._TIMEOUT}s"
            logger.warning("[%s] %s", test_id, result["error"])
        except requests.ConnectionError as e:
            result["error"] = f"Connection error: {e}"
            logger.warning("[%s] %s", test_id, result["error"])
        except requests.RequestException as e:
            result["error"] = f"Request error: {e}"
            logger.warning("[%s] %s", test_id, result["error"])

        return result
