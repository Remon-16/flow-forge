import json
import logging
import re
import threading
from typing import Any, Dict, List, Optional

import requests

from auth.login_manager import LoginManager
from config.config_manager import get_app
from resolvers.path_resolver import resolve_path, _Missing
from resolvers.var_resolver import has_placeholders
from executor.base import BaseExecutor
from processors.base import ProcessorError

logger = logging.getLogger(__name__)

_VAR_RE = re.compile(r"#\{([^}]+)\}")


class BizFlowExecutor(BaseExecutor):
    """业务链路用例执行器。Executes multi-step business flow test cases.

    Each business flow (one Excel sheet) runs in its own thread.
    Steps within a flow execute sequentially, with ThreadLocal step data
    for variable resolution between steps.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._step_data = threading.local()

    def execute_single(self, biz_flow: Dict[str, Any]) -> Dict[str, Any]:
        sheet_name = biz_flow.get("sheet_name", "unknown")
        steps = biz_flow.get("steps", [])
        parse_error = biz_flow.get("parse_error")

        if parse_error:
            return {
                "sheet_name": sheet_name,
                "api_name": sheet_name,
                "steps": [],
                "flow_chain": "",
                "failed_step": None,
                "passed": False,
                "parse_error": parse_error,
            }

        if not steps:
            return self._build_result(biz_flow, error="Biz flow has no steps to execute")

        try:
            self._step_data.responses = {}

            step_results = []
            flow_parts = []
            failed_step = None
            all_passed = True

            for step in steps:
                step_id = step.get("step_id", step.get("test_id", "unknown"))
                api_name = step.get("api_name", "")

                result = self._execute_step(step, step_id)

                if result.get("response_body") is not None and result.get("response_status"):
                    self._step_data.responses[step_id] = result["response_body"]

                step_results.append(result)

                if result["passed"]:
                    flow_parts.append(api_name or step_id)
                else:
                    flow_parts.append(f"× {api_name or step_id}")
                    failed_step = step_id
                    all_passed = False
                    break

            return {
                "sheet_name": sheet_name,
                "api_name": sheet_name,
                "steps": step_results,
                "flow_chain": " → ".join(flow_parts),
                "failed_step": failed_step,
                "passed": all_passed,
                "parse_error": None,
            }
        finally:
            if hasattr(self._step_data, "responses"):
                del self._step_data.responses

    def _execute_step(
        self, step: Dict[str, Any], step_id: str
    ) -> Dict[str, Any]:
        app_name = step.get("app_name") or ""
        method = (step.get("method") or "GET").upper()
        path = step.get("url", "")

        if "<URL not exist>" in path:
            return self._build_step_result(
                step, step_id, "", path, {}, {},
                passed=False,
                error=f"URL not found in API documentation: {path}",
            )

        try:
            headers, body, url, base_url, cleared_params = self._prepare_step_request(step, app_name, path)
        except InheritResolutionError as e:
            return self._build_step_result(
                step, step_id, "", path, {}, {},
                passed=False,
                error=f"Inherit resolution error: {e}",
            )

        result = self._build_step_result(step, step_id, base_url, path, headers, body)

        return self._execute_step_request(result, step, step_id, url, headers, body, app_name, method, cleared_params)

    def _prepare_step_request(
        self, step: Dict[str, Any], app_name: str, path: str
    ):
        """Extract headers, body, resolve inherit vars, and build URL.

        Returns ``(headers, body, url, base_url, cleared_params)``.
        """
        headers = dict(step.get("request_head") or {})
        body = dict(step.get("request_body") or {})
        inherit_data = step.get("inherit", "")

        app_config = get_app(app_name) if app_name else {}
        base_url = app_config.get("baseURL", "") if app_config else ""
        url = self._build_url(base_url, path)
        url, body, cleared_params = self._resolve_url_placeholders(url, body)

        if inherit_data:
            try:
                inherit_mapping = self._parse_inherit(inherit_data)
                body = self._resolve_vars(body, inherit_mapping)
                headers = self._resolve_vars(headers, inherit_mapping)
                url = self._resolve_vars(url, inherit_mapping)
            except Exception as e:
                # Signal error via a sentinel so caller can build error result
                raise InheritResolutionError(str(e)) from e

        return headers, body, url, base_url, cleared_params

    def _execute_step_request(
        self,
        result: Dict[str, Any],
        step: Dict[str, Any],
        step_id: str,
        url: str,
        headers: Dict,
        body: Dict,
        app_name: str,
        method: str,
        cleared_params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Token resolution → preprocessors → HTTP request → assertions → postprocessors."""

        # ---- Token / Login (conditional — only if headTokenName header still has unresolved #{}) ----
        app_config = get_app(app_name) if app_name else {}
        head_token_name = app_config.get("headTokenName") if app_config else None
        if head_token_name and head_token_name in headers and has_placeholders(headers[head_token_name]):
            resolved_headers, token_error = LoginManager.resolve_token(app_config, headers)
            if token_error:
                result["error"] = token_error
                result["passed"] = False
                return result
            headers = resolved_headers
            result["request_headers"] = dict(headers)

        # ---- PreProcessors ----
        preprocessors = step.get("preprocessors") or []
        postprocessors = step.get("postprocessors") or []
        global_config = self._load_processors(preprocessors, postprocessors)

        if preprocessors:
            try:
                if global_config is not None and cleared_params:
                    config_for_proc = dict(global_config)
                    config_for_proc["_cleared_path_params"] = cleared_params
                else:
                    config_for_proc = global_config
                headers, body, preprocessor_results = self._run_preprocessors(
                    preprocessors, headers, body, config_for_proc)
                result["request_headers"] = dict(headers)
                result["request_body"] = dict(body)
                result["preprocessor_results"] = preprocessor_results
            except ProcessorError as e:
                result["error"] = f"[{e.processor_name}] {e}"
                result["passed"] = False
                return result

        # ---- HTTP request + Assertions ----
        try:
            response = self._send_request(method, url, headers, body)
            result["response_status"] = response.status_code
            result["response_body"] = self._extract_body(response)

            assertions = self._run_assertions(response, step)
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
                logger.info("[%s] PASS", step_id)
            else:
                failed_fields = [a["field"] for a in assertions if not a["passed"]]
                logger.info("[%s] FAIL — assertions failed: %s", step_id, failed_fields)

        except requests.Timeout:
            result["error"] = f"Request timeout after {self._TIMEOUT}s"
            result["passed"] = False
            logger.warning("[%s] %s", step_id, result["error"])
        except requests.ConnectionError as e:
            result["error"] = f"Connection error: {e}"
            result["passed"] = False
            logger.warning("[%s] %s", step_id, result["error"])
        except requests.RequestException as e:
            result["error"] = f"Request error: {e}"
            result["passed"] = False
            logger.warning("[%s] %s", step_id, result["error"])

        return result

    def _parse_inherit(self, inherit_data) -> Dict[str, tuple]:
        mapping: Dict[str, tuple] = {}

        def _store(key: str, value: str) -> None:
            dot_idx = value.find(".")
            if dot_idx == -1:
                mapping[key] = (value, "")
            else:
                mapping[key] = (value[:dot_idx], value[dot_idx + 1:])

        # 新格式：JSON dict（YAML 原生映射 或 Excel 解析后的 dict）
        if isinstance(inherit_data, dict):
            for key, value in inherit_data.items():
                key = str(key).strip()
                val = str(value).strip()
                if key and val:
                    _store(key, val)
            return mapping

        # 旧格式回退：逗号分隔字符串
        if isinstance(inherit_data, str) and inherit_data.strip():
            pairs = [p.strip() for p in inherit_data.split(",")]
            for pair in pairs:
                if not pair or "=" not in pair:
                    continue
                key, value = pair.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key and value:
                    _store(key, value)

        return mapping

    def _resolve_vars(
        self, data: Any, inherit_mapping: Dict[str, tuple]
    ) -> Any:
        if isinstance(data, dict):
            result = {}
            for k, v in data.items():
                result[k] = self._resolve_vars(v, inherit_mapping)
            return result
        if isinstance(data, list):
            return [self._resolve_vars(item, inherit_mapping) for item in data]
        if isinstance(data, str):
            result = data
            if result.startswith("\\#"):
                return result[1:]
            def replacer(match):
                var_name = match.group(1)
                if var_name in inherit_mapping:
                    step_id, path = inherit_mapping[var_name]
                    responses = getattr(self._step_data, "responses", {})
                    step_data = responses.get(step_id)
                    if step_data is not None:
                        if path:
                            resolved = resolve_path(step_data, path)
                            if isinstance(resolved, _Missing):
                                logger.warning("Inherit path not found: %s.%s", step_id, path)
                                return match.group(0)
                            if isinstance(resolved, (dict, list)):
                                return json.dumps(resolved, ensure_ascii=False)
                            return str(resolved)
                        return json.dumps(step_data, ensure_ascii=False)
                return match.group(0)
            return _VAR_RE.sub(replacer, result)
        return data

    @staticmethod
    def _build_step_result(
        step: Dict[str, Any],
        step_id: str,
        base_url: str,
        path: str,
        headers: Dict,
        body: Dict,
        passed: bool = False,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        return BaseExecutor._build_result(
            step,
            test_id=step_id,
            step_id=step_id,
            base_url=base_url,
            url=path,
            request_headers=dict(headers),
            request_body=dict(body),
            passed=passed,
            error=error,
        )


class InheritResolutionError(Exception):
    """Raised when inherit variable resolution fails."""
