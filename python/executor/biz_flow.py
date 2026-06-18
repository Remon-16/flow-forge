import json
import logging
import re
import threading
from typing import Any, Dict, List, Optional

import requests

from assertion.engine import AssertionEngine
from auth.login_manager import LoginManager
from config.config_manager import get_app, get_all
from core.path_resolver import resolve_path, _Missing
from core.var_resolver import has_placeholders
from executor.base import BaseExecutor
from processors.base import ProcessorError

logger = logging.getLogger(__name__)

_TIMEOUT = 30
_VAR_RE = re.compile(r"#\{([^}]+)\}")


class BizFlowExecutor(BaseExecutor):
    """Executes multi-step business flow test cases.

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

        headers = dict(step.get("request_head") or {})
        body = dict(step.get("request_body") or {})
        expected_status = step.get("status_code")
        trans = step.get("trans", "")

        app_config = get_app(app_name) if app_name else {}
        base_url = app_config.get("baseURL", "") if app_config else {}
        url = self._build_url(base_url, path)

        url, body = self._resolve_url_placeholders(url, body)

        if trans:
            try:
                trans_mapping = self._parse_trans(trans)
                body = self._resolve_vars(body, trans_mapping)
                headers = self._resolve_vars(headers, trans_mapping)
                url = self._resolve_vars(url, trans_mapping)
            except Exception as e:
                return self._build_step_result(step, step_id, base_url, path,
                                               headers, body, passed=False,
                                               error=f"Trans resolution error: {e}")

        # 仅当 headTokenName header 中仍有未解析的 #{} 时，才调用 LoginManager
        # Trans 已处理的 #{} 不会被 LoginManager 覆写
        head_token_name = app_config.get("headTokenName") if app_config else None
        if head_token_name and head_token_name in headers and has_placeholders(headers[head_token_name]):
            resolved_headers, token_error = LoginManager.resolve_token(app_config, headers)
            if token_error:
                return self._build_step_result(step, step_id, base_url, path,
                                               headers, body, passed=False, error=token_error)
            headers = resolved_headers

        # ---- PreProcessors ----
        preprocessors = step.get("preprocessors") or []
        postprocessors = step.get("postprocessors") or []
        global_config = None

        if preprocessors or postprocessors:
            from processors.loader import discover_processors
            discover_processors()
            global_config = get_all()

        if preprocessors:
            from processors.runner import run_preprocessors
            try:
                headers, body, preprocessor_results = run_preprocessors(
                    {"request_head": headers, "request_body": body, "preprocessors": preprocessors},
                    global_config,
                )
                result = self._build_step_result(step, step_id, base_url, path, headers, body)
                result["preprocessor_results"] = preprocessor_results
            except ProcessorError as e:
                return self._build_step_result(
                    step, step_id, base_url, path, headers, body,
                    passed=False, error=f"[{e.processor_name}] {e}",
                )
        else:
            result = self._build_step_result(step, step_id, base_url, path, headers, body)

        try:
            response = self._send_request(method, url, headers, body)
            result["response_status"] = response.status_code
            result["response_body"] = self._extract_body(response)

            assertions = AssertionEngine.run(
                response,
                step.get("assert_dict", {}),
                step.get("assert_rules", []),
            )

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

            # ---- PostProcessors ----
            if postprocessors and global_config is not None:
                from processors.runner import run_postprocessors
                try:
                    postprocessor_results = run_postprocessors(
                        {"request_head": headers, "request_body": body, "postprocessors": postprocessors},
                        response,
                        global_config,
                    )
                    result["postprocessor_results"] = postprocessor_results
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
            result["error"] = f"Request timeout after {_TIMEOUT}s"
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

    def _parse_trans(self, trans: str) -> Dict[str, tuple]:
        mapping: Dict[str, tuple] = {}
        pairs = [p.strip() for p in trans.split(",")]
        for pair in pairs:
            if not pair or "=" not in pair:
                continue
            key, value = pair.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not value:
                continue
            dot_idx = value.find(".")
            if dot_idx == -1:
                mapping[key] = (value, "")
            else:
                step_id = value[:dot_idx]
                path = value[dot_idx + 1:]
                mapping[key] = (step_id, path)
        return mapping

    def _resolve_vars(
        self, data: Any, trans_mapping: Dict[str, tuple]
    ) -> Any:
        if isinstance(data, dict):
            result = {}
            for k, v in data.items():
                result[k] = self._resolve_vars(v, trans_mapping)
            return result
        if isinstance(data, list):
            return [self._resolve_vars(item, trans_mapping) for item in data]
        if isinstance(data, str):
            result = data
            if result.startswith("\\#"):
                return result[1:]
            def replacer(match):
                var_name = match.group(1)
                if var_name in trans_mapping:
                    step_id, path = trans_mapping[var_name]
                    responses = getattr(self._step_data, "responses", {})
                    step_data = responses.get(step_id)
                    if step_data is not None:
                        if path:
                            resolved = resolve_path(step_data, path)
                            if isinstance(resolved, _Missing):
                                logger.warning("Trans path not found: %s.%s", step_id, path)
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
        return {
            "test_id": step_id,
            "step_id": step_id,
            "api_name": step.get("api_name", ""),
            "app_name": step.get("app_name", ""),
            "base_url": base_url,
            "method": step.get("method", ""),
            "url": path,
            "tag": step.get("tag", ""),
            "remark": step.get("remark", ""),
            "request_headers": dict(headers),
            "request_body": dict(body),
            "response_status": None,
            "response_body": None,
            "assertions": [],
            "preprocessor_results": [],
            "postprocessor_results": [],
            "passed": passed,
            "error": error,
        }

    @staticmethod
    def _build_url(base_url: str, path: str) -> str:
        base = base_url.rstrip("/") if base_url else ""
        path = path.lstrip("/") if path and path.startswith("/") else path
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
