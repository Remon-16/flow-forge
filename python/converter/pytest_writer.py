"""Generate standalone pytest test files from Flow Forge test cases.

The generated code has **zero** Flow Forge dependencies — only pytest + requests
are needed to run it.  Copy the output directory anywhere and run::

    python -m pytest test_single_cases.py -v
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# ============================================================================
# Template: conftest.py
# ============================================================================

_CONFTEST_TEMPLATE = r'''"""Shared fixtures and helpers — no Flow Forge dependency."""
import hashlib
import hmac
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pytest
import requests

logger = logging.getLogger(__name__)

# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="session")
def base_url():
    """Base URL for the API under test. Set via BASE_URL env var."""
    return os.environ.get("BASE_URL", "http://localhost:8000")


# ============================================================
# Path resolver (dot/bracket notation)
# ============================================================

_SPLIT_RE = re.compile(r"[\.\[\]]")


class _Missing:
    """Sentinel for unresolved paths."""


def _resolve_path(data: Any, path: str) -> Any:
    """Traverse nested dict/list using dot/bracket paths.

    Examples: 'data.items.0.name', 'data.records[0].id', '$.data.token'
    """
    if not path:
        return _Missing()
    clean = path
    if clean.startswith("$."):
        clean = clean[2:]
    current = data
    for part in _SPLIT_RE.split(clean):
        if not part:
            continue
        if current is None:
            return _Missing()
        if isinstance(current, dict):
            current = current.get(part, _Missing())
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (IndexError, ValueError):
                return _Missing()
        else:
            return _Missing()
        if isinstance(current, _Missing):
            return current
    return current


# ============================================================
# URL placeholder resolver
# ============================================================

_VAR_PATTERN = re.compile(r"#\{([^}]+)\}")
_CURLY_PATTERN = re.compile(r"\{([^}]+)\}")


def _resolve_url(url: str, body: Dict[str, Any]) -> str:
    """Replace #{var} and {var} placeholders in URL with values from body."""
    result = url
    for pattern in (_VAR_PATTERN, _CURLY_PATTERN):
        def _replacer(m, b=body):
            key = m.group(1)
            val = b.get(key)
            return str(val) if val is not None else m.group(0)
        result = pattern.sub(_replacer, result)
    return result


# ============================================================
# Assertion helpers
# ============================================================

_FUNC_RE = re.compile(r"^(SUM_PRODUCT|SUM)\((.+)\)$")
_OPERATORS = [
    (re.compile(r"\s+is_not_null\s*$"), "is_not_null", False),
    (re.compile(r"\s+is_null\s*$"), "is_null", False),
    (re.compile(r"\s+typeof\s+(.+)$"), "typeof", True),
    (re.compile(r"\s+not_contains\s+(.+)$"), "not_contains", True),
    (re.compile(r"\s+contains\s+(.+)$"), "contains", True),
    (re.compile(r"\s+\bin\b\s+(.+)$"), "in", True),
    (re.compile(r"\s+!=\s*(.+)$"), "!=", True),
    (re.compile(r"\s+==\s*(.+)$"), "==", True),
    (re.compile(r"\s+>=\s*(.+)$"), ">=", True),
    (re.compile(r"\s+<=\s*(.+)$"), "<=", True),
    (re.compile(r"\s+=~\s*(.+)$"), "=~", True),
    (re.compile(r"\s+>\s*(.+)$"), ">", True),
    (re.compile(r"\s+<\s*(.+)$"), "<", True),
]


def _assert_field(data: Any, path: str, expected: Any) -> bool:
    """Compare a JSON field at *path* against *expected*. Returns True/False."""
    if data is None:
        return False
    actual = _resolve_path(data, path)
    if isinstance(actual, _Missing):
        return False
    return str(actual) == str(expected)


def _assert_rules(data: Any, rules: List[str]) -> List[Dict[str, Any]]:
    """Execute assertion rules and return result dicts."""
    results = []
    for rule in rules:
        try:
            left, op, expected = _parse_rule(rule)
            actual = _eval_expression(left, data)
            if op not in ("is_null", "is_not_null"):
                expected = _eval_expected(expected, data)
            passed = _execute_op(actual, op, expected)
            results.append({"field": rule, "expected": expected, "actual": actual, "passed": passed})
        except Exception as e:
            results.append({"field": rule, "expected": None, "actual": f"<error: {e}>", "passed": False})
    return results


def _parse_rule(rule: str) -> Tuple[str, str, Optional[str]]:
    rule = rule.strip()
    for pattern, op, has_expected in _OPERATORS:
        m = pattern.search(rule)
        if m:
            left = rule[:m.start()].strip()
            expected = m.group(1).strip() if has_expected else None
            return left, op, expected
    raise ValueError(f"Cannot parse rule: {rule}")


def _eval_expression(expr: str, data: Any) -> Any:
    expr = expr.strip()
    m = _FUNC_RE.match(expr)
    if m:
        func = m.group(1)
        args = [a.strip() for a in m.group(2).split(",")]
        if func == "SUM":
            vals = _resolve_wildcard(data, args[0])
            return sum(float(v) for v in vals) if vals else 0.0
        elif func == "SUM_PRODUCT" and len(args) >= 2:
            v1 = _resolve_wildcard(data, args[0])
            v2 = _resolve_wildcard(data, args[1])
            if len(v1) == len(v2):
                return sum(float(a) * float(b) for a, b in zip(v1, v2))
            return 0.0
    if expr.endswith(".length()"):
        inner = expr[:-len(".length()")]
        val = _resolve_path(data, inner)
        if isinstance(val, _Missing) or val is None:
            return 0 if val is None else -1
        return len(val) if isinstance(val, (list, dict, str)) else -1
    result = _resolve_path(data, expr)
    if isinstance(result, _Missing):
        raise ValueError(f"Path not found: {expr}")
    return result


def _resolve_wildcard(data: Any, path: str) -> List[Any]:
    parts = [p for p in _SPLIT_RE.split(path) if p]
    if parts and parts[0].startswith("$."):
        parts[0] = parts[0][2:]
    if not parts:
        return [data]

    def _walk(d, idx):
        if idx >= len(parts):
            return [d]
        p = parts[idx]
        if p == "*":
            if not isinstance(d, list):
                return []
            result = []
            for item in d:
                result.extend(_walk(item, idx + 1))
            return result
        if isinstance(d, dict):
            if p in d:
                return _walk(d[p], idx + 1)
            return []
        if isinstance(d, list):
            try:
                return _walk(d[int(p)], idx + 1)
            except (IndexError, ValueError):
                return []
        return []
    return _walk(data, 0)


def _eval_expected(expr: str, data: Any) -> Any:
    expr = expr.strip()
    m = _FUNC_RE.match(expr)
    if m:
        return _eval_expression(expr, data)
    try:
        return json.loads(expr)
    except (json.JSONDecodeError, ValueError):
        pass
    return expr


def _execute_op(actual: Any, op: str, expected: Any) -> bool:
    try:
        if op == "==": return actual == expected
        if op == "!=": return actual != expected
        if op == ">": return float(actual) > float(expected)
        if op == ">=": return float(actual) >= float(expected)
        if op == "<": return float(actual) < float(expected)
        if op == "<=": return float(actual) <= float(expected)
        if op == "=~": return re.match(str(expected), str(actual)) is not None
        if op == "in": return actual in expected if expected is not None else False
        if op == "contains": return expected in actual if actual is not None else False
        if op == "not_contains": return expected not in actual if actual is not None else True
        if op == "is_null": return actual is None
        if op == "is_not_null": return actual is not None
        if op == "typeof":
            type_map = {
                "int": int, "float": float, "str": str, "bool": bool,
                "list": list, "dict": dict, "int_or_float": (int, float),
            }
            expected_type = type_map.get(str(expected).lower(), str)
            return isinstance(actual, expected_type)
        return False
    except (TypeError, ValueError):
        return False


# ============================================================
# Token / Login helpers
# ============================================================

_token_cache: Dict[str, str] = {}


def _resolve_token(headers: Dict[str, Any], app_name: Optional[str]) -> Dict[str, Any]:
    """Replace #{userParam} placeholders in Authorization header."""
    from _config import APPS
    if not app_name or app_name not in APPS:
        return headers
    app_config = APPS[app_name]
    head_token_name = app_config.get("headTokenName", "Authorization")
    token_value = headers.get(head_token_name, "")
    if not isinstance(token_value, str) or "#{" not in token_value:
        return headers
    matches = _VAR_PATTERN.findall(token_value)
    if not matches:
        return headers
    headers = dict(headers)
    for user_key in matches:
        cache_key = f"{app_name}:{user_key}"
        if cache_key in _token_cache:
            token = _token_cache[cache_key]
        else:
            token = _do_login(app_name, app_config, user_key)
            if token:
                _token_cache[cache_key] = token
            else:
                continue
        headers[head_token_name] = token_value.replace(f"#{{{user_key}}}", token)
    return headers


def _do_login(app_name: str, app_config: Dict[str, Any], user_key: str) -> Optional[str]:
    """Call login API and extract token."""
    base_url = app_config.get("baseURL", "")
    login_path = app_config.get("loginPath", "")
    res_token_path = app_config.get("resTokenPath", "")
    login_body_fields = [f.strip() for f in app_config.get("loginBody", "").split(",") if f.strip()]
    user_config = app_config.get(user_key, {})
    login_body = {f: user_config.get(f, "") for f in login_body_fields}
    url = f"{base_url.rstrip('/')}/{login_path.lstrip('/')}"
    logger.info("Logging in '%s' for app '%s': %s", user_key, app_name, url)
    try:
        resp = requests.post(url, json=login_body, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        token = _resolve_path(data, res_token_path)
        if isinstance(token, _Missing) or token is None:
            logger.warning("Token not found at '%s' in login response", res_token_path)
            return None
        return str(token)
    except Exception as e:
        logger.warning("Login failed for '%s': %s", user_key, e)
        return None


# ============================================================
# Built-in processor equivalents
# ============================================================

def _apply_timestamp(headers: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> None:
    """Inject X-Timestamp (ISO 8601 UTC) and X-Request-Id (UUID4) headers."""
    cfg = config or {}
    headers[cfg.get("header_timestamp", "X-Timestamp")] = datetime.now(timezone.utc).isoformat()
    headers[cfg.get("header_request_id", "X-Request-Id")] = str(uuid.uuid4())


def _apply_hmac_sign(headers: Dict[str, Any], body: Dict[str, Any],
                      config: Optional[Dict[str, Any]] = None) -> None:
    """Compute HMAC-SHA256 signature and add to headers."""
    cfg = config or {}
    secret_env = cfg.get("secret_env", "SIGN_SECRET")
    secret = os.environ.get(secret_env, "")
    if not secret:
        logger.warning("HMAC secret env var '%s' is empty or not set", secret_env)
        return
    body_str = json.dumps(body, ensure_ascii=False, sort_keys=True) if body else ""
    payload = cfg.get("body_template", "{body}").format(body=body_str, method="", path="")
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    headers[cfg.get("header_name", "X-Signature")] = digest


def _verify_hmac(response_headers: Dict[str, Any], response_body: Any,
                 config: Optional[Dict[str, Any]] = None) -> None:
    """Verify HMAC signature in response. Raises AssertionError on mismatch."""
    cfg = config or {}
    secret_env = cfg.get("secret_env", "SIGN_SECRET")
    header_name = cfg.get("header_name", "X-Signature")
    secret = os.environ.get(secret_env, "")
    if not secret:
        logger.warning("HMAC verify secret env var '%s' is empty", secret_env)
        return
    expected = response_headers.get(header_name)
    if not expected:
        raise AssertionError(f"HMAC header '{header_name}' not found in response")
    if response_body is None:
        body_str = ""
    elif isinstance(response_body, str):
        body_str = response_body
    else:
        body_str = json.dumps(response_body, ensure_ascii=False, sort_keys=True)
    payload = cfg.get("body_template", "{body}").format(body=body_str)
    actual = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(actual, expected):
        raise AssertionError(f"HMAC signature mismatch in response header '{header_name}'")


def _print_request(headers: Dict[str, Any], body: Dict[str, Any],
                   prefix: str = "[PreDemo]") -> None:
    """Log request summary at INFO level."""
    logger.info("%s Request — Headers: %s | Body: %.200s", prefix, list(headers.keys()), str(body))


def _print_response(response_headers: Dict[str, Any], response_body: Any,
                    prefix: str = "[PostDemo]") -> None:
    """Log response summary at INFO level."""
    logger.info("%s Response — Headers: %s | Body: %.200s", prefix,
                list(response_headers.keys()), str(response_body))


def _log_response_metrics(response_headers: Dict[str, Any], response_body: Any,
                          threshold: int = 1048576) -> None:
    """Log response size metrics; warn if above threshold."""
    content_length = response_headers.get("Content-Length")
    if content_length is not None:
        try:
            content_length = int(content_length)
        except (ValueError, TypeError):
            content_length = None
    if content_length is None and response_body is not None:
        content_length = len(str(response_body).encode("utf-8"))
    if content_length is not None:
        logger.info("Response metrics — Content-Length: %d bytes", content_length)
        if content_length > threshold:
            logger.warning("Response body size %d exceeds threshold %d", content_length, threshold)
    else:
        logger.info("Response metrics — Content-Length: unknown")
'''


# ============================================================================
# Template: _config.py (environment selector)
# ============================================================================

_CONFIG_TEMPLATE = '''"""Environment selector — change ENV to switch between environments.

Available environments: {env_names}
"""
ENV = "{default_env}"  # {env_names_str}

if ENV == "{first_env}":
    from _env_{first_env} import APPS  # noqa: E402, F401
'''


# ============================================================================
# Template: _ff_compat.py (lightweight compatibility stubs)
# ============================================================================

_FF_COMPAT_TEMPLATE = '''"""Minimal compatibility stubs for Flow Forge processors.

Provides PreProcessor / PostProcessor base classes and ProcessorError so that
custom processor modules can run without the Flow Forge framework.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple


class ProcessorError(Exception):
    """Controlled error from a processor."""

    def __init__(self, message: str, processor_name: str = ""):
        super().__init__(message)
        self.processor_name = processor_name


class PreProcessor(ABC):
    """Minimal pre-processor base class."""

    name: str = ""

    @abstractmethod
    def process(
        self,
        headers: Dict[str, Any],
        body: Dict[str, Any],
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        ...


class PostProcessor(ABC):
    """Minimal post-processor base class."""

    name: str = ""

    @abstractmethod
    def process(
        self,
        request_headers: Dict[str, Any],
        request_body: Dict[str, Any],
        response_headers: Dict[str, Any],
        response_body: Any,
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> None:
        ...
'''


# ============================================================================
# Template: test_single_cases.py header
# ============================================================================

_SINGLE_HEADER = '''"""Auto-generated single API test cases — standalone pytest.

Generated by Flow Forge converter.  Run with::

    python -m pytest test_single_cases.py -v

Edit the CASE_* constants to adjust request parameters.
"""

import logging
import json
import pytest
import requests

logger = logging.getLogger(__name__)

'''

# ============================================================================
# Template: test_biz_flows.py header
# ============================================================================

_BIZ_HEADER = '''"""Auto-generated business flow test cases — standalone pytest.

Generated by Flow Forge converter.  Run with::

    python -m pytest test_biz_flows.py -v

Each class represents one business flow; each method is one step.
"""

import logging
import json
import pytest
import requests

logger = logging.getLogger(__name__)

'''


# ============================================================================
# Internal helpers
# ============================================================================

def _read_yaml_dir(dir_path: Optional[str]) -> List[Dict[str, Any]]:
    """Read all YAML files from a directory, returning parsed dicts."""
    if not dir_path:
        return []
    p = Path(dir_path)
    if not p.is_dir():
        logger.warning("Directory not found, skipping: %s", dir_path)
        return []
    results: List[Dict[str, Any]] = []
    for f in sorted(p.glob("*.yaml")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if isinstance(data, dict):
                data.pop("case_type", None)
                results.append(data)
        except Exception:
            logger.warning("Failed to read YAML file: %s", f, exc_info=True)
    return results


def _read_yaml_flows(dir_path: Optional[str]) -> List[Dict[str, Any]]:
    """Read biz flow YAML files (expecting 'steps' key)."""
    raw = _read_yaml_dir(dir_path)
    return [d for d in raw if "steps" in d and isinstance(d["steps"], list)]


_VAR_RE = re.compile(r"#\{([^}]+)\}")

_PREPROC_DISPATCH: Dict[str, str] = {
    "timestamp": "_apply_timestamp",
    "hmac-sign": "_apply_hmac_sign",
    "print-demo": "_print_request",
}

_POSTPROC_DISPATCH: Dict[str, str] = {
    "hmac-verify": "_verify_hmac",
    "response-time": "_log_response_metrics",
    "print-demo-post": "_print_response",
}


def _generate_preprocessor_calls(preprocessors: list) -> str:
    """Generate preprocessor dispatch code."""
    if not preprocessors:
        return ""
    lines = ["    # --- PreProcessors ---"]
    for pp in preprocessors:
        name = pp.get("name", "")
        func = _PREPROC_DISPATCH.get(name)
        config = json.dumps(pp.get("config", {}) or {})
        if func:
            if name == "hmac-sign":
                lines.append(f"    {func}(headers, body, {config})")
            elif name == "print-demo":
                prefix = (pp.get("config") or {}).get("prefix", "[PreDemo]")
                lines.append(f"    {func}(headers, body, prefix={json.dumps(prefix)})")
            else:
                lines.append(f"    {func}(headers, {config})")
        elif name == "path-param-restore":
            lines.append(f"    # path-param-restore: standalone mode keeps body fields by default, "
                         f"no restore needed")
        else:
            # Custom processor — try to import from _custom_processors
            lines.append(f"    # Custom processor '{name}' — "
                         f"check _custom_processors/ for implementation")
            lines.append(f"    # from _custom_processors.{name.replace('-', '_')} "
                         f"import process; process(headers, body, {config}, {{}})")
    lines.append("")
    return "\n".join(lines) + "\n"


def _generate_postprocessor_calls(postprocessors: list) -> str:
    """Generate postprocessor dispatch code."""
    if not postprocessors:
        return ""
    lines = ["    # --- PostProcessors ---"]
    for pp in postprocessors:
        name = pp.get("name", "")
        func = _POSTPROC_DISPATCH.get(name)
        config = json.dumps(pp.get("config", {}) or {})
        if func:
            if name == "response-time":
                threshold = (pp.get("config") or {}).get("warn_threshold_bytes", 1048576)
                lines.append(f"    {func}(resp.headers, data, threshold={threshold})")
            elif name == "print-demo-post":
                prefix = (pp.get("config") or {}).get("prefix", "[PostDemo]")
                lines.append(f"    {func}(resp.headers, data, prefix={json.dumps(prefix)})")
            else:
                lines.append(f"    {func}(resp.headers, data, {config})")
        else:
            lines.append(f"    # Custom postprocessor '{name}'")
    lines.append("")
    return "\n".join(lines) + "\n"


def _sanitize_name(name: str) -> str:
    """Sanitize a string for use as a Python identifier / filename."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", str(name))


def _indent_lines(text: str, spaces: int) -> str:
    """Add extra indentation to every non-empty line of *text*."""
    if not text:
        return text
    prefix = " " * spaces
    result = []
    for line in text.splitlines(True):
        if line.strip():
            result.append(prefix + line)
        else:
            result.append(line)
    return "".join(result)


def _generate_single_test(case: Dict[str, Any], index: int) -> str:
    """Generate a single test function for a single API case."""
    test_id = _sanitize_name(case.get("test_id", f"case_{index}"))
    method = case.get("method", "GET").upper()
    url = case.get("url", "/")
    status_code = case.get("status_code", 200)
    app_name = case.get("app_name") or ""
    headers = case.get("request_head") or {}
    body = case.get("request_body") or {}
    assert_dict = case.get("assert_dict") or {}
    assert_rules = case.get("assert_rules") or []
    preprocessors = case.get("preprocessors") or []
    postprocessors = case.get("postprocessors") or []

    # Build the data constant
    case_data: Dict[str, Any] = {
        "test_id": case.get("test_id", f"case_{index}"),
        "method": method,
        "url": url,
        "headers": headers,
        "body": body,
        "expected_status": status_code,
        "assertions": assert_dict,
        "assert_rules": assert_rules,
    }
    if app_name:
        case_data["app_name"] = app_name

    data_block = json.dumps(case_data, indent=4, ensure_ascii=False)

    pre_calls = _generate_preprocessor_calls(preprocessors)
    post_calls = _generate_postprocessor_calls(postprocessors)

    token_line = ""
    if app_name:
        token_line = f'\n    headers = _resolve_token(headers, "{app_name}")'

    source = f'''
# ============================================================
# Test Data
# ============================================================
CASE_{test_id} = {data_block}


def test_{test_id}(base_url):
    case = CASE_{test_id}
    url = _resolve_url(base_url + case["url"], case["body"])
    headers = dict(case["headers"])
    body = dict(case["body"])
{token_line}
{pre_calls}
    # --- HTTP Request ---
    resp = requests.request(
        case["method"], url, headers=headers,
        json=body if body else None, timeout=30)

    assert resp.status_code == case["expected_status"], \\
        f"Expected {{case['expected_status']}}, got {{resp.status_code}}: {{resp.text[:200]}}"

    data = resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else resp.text

    # --- Field Assertions ---
    for path, expected in case["assertions"].items():
        ok = _assert_field(data, path, expected)
        actual = _resolve_path(data, path)
        assert ok, f"[{{path}}] expected={{expected!r}}, actual={{actual!r}}"

    # --- Rule Assertions ---
    rule_results = _assert_rules(data, case.get("assert_rules", []))
    for r in rule_results:
        assert r["passed"], f"Rule failed: {{r['field']}} (expected={{r['expected']}}, actual={{r['actual']}})"
{post_calls}
'''
    return source


def _generate_biz_flow_class(flow: Dict[str, Any], index: int) -> str:
    """Generate a test class for a business flow (multi-step)."""
    sheet_name = _sanitize_name(flow.get("sheet_name", f"flow_{index}"))
    steps: List[Dict[str, Any]] = flow.get("steps", [])
    if not steps:
        return ""

    class_name = f"TestBizFlow_{sheet_name}"
    methods = []

    # Flow-level constants
    flow_vars: Dict[str, Any] = {}

    for si, step in enumerate(steps):
        step_id = _sanitize_name(step.get("step_id", f"step_{si}"))
        method_name = f"test_step_{si:02d}_{step_id}"
        method = (step.get("method") or "GET").upper()
        url = step.get("url", "/")
        status_code = step.get("status_code", 200)
        app_name = step.get("app_name") or ""
        headers = step.get("request_head") or {}
        body = step.get("request_body") or {}
        assert_dict = step.get("assert_dict") or {}
        assert_rules = step.get("assert_rules") or []
        preprocessors = step.get("preprocessors") or []
        postprocessors = step.get("postprocessors") or []
        inherit = step.get("inherit") or {}

        case_data: Dict[str, Any] = {
            "step_id": step.get("step_id", f"step_{si}"),
            "method": method,
            "url": url,
            "headers": headers,
            "body": body,
            "expected_status": status_code,
            "assertions": assert_dict,
            "assert_rules": assert_rules,
        }
        if app_name:
            case_data["app_name"] = app_name

        data_block = json.dumps(case_data, indent=8, ensure_ascii=False)

        # Inherit resolution (step variable passing)
        inherit_lines = ""
        if inherit:
            inherit_lines = "        # --- Inherit (step variable passing) ---\n"
            for var, expr in inherit.items():
                inherit_lines += (
                    f"        step_data[\"body\"][\"{var}\"] = "
                    f"_resolve_path(self._flow_data, \"{expr}\")\n"
                )

        pre_calls = _indent_lines(_generate_preprocessor_calls(preprocessors), 8)
        post_calls = _indent_lines(_generate_postprocessor_calls(postprocessors), 8)

        token_line = ""
        if app_name:
            token_line = f'\n        headers = _resolve_token(headers, "{app_name}")'

        source = f'''
    STEP_{step_id} = {data_block}

    def {method_name}(self, base_url):
        step_data = self.STEP_{step_id}
        url = _resolve_url(base_url + step_data["url"], step_data["body"])
        headers = dict(step_data["headers"])
        body = dict(step_data["body"])
{token_line}
{inherit_lines}
{pre_calls}        # --- HTTP Request ---
        resp = requests.request(
            step_data["method"], url, headers=headers,
            json=body if body else None, timeout=30)

        assert resp.status_code == step_data["expected_status"], \\
            f"Expected {{step_data['expected_status']}}, got {{resp.status_code}}"

        data = resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else resp.text

        # Store response for downstream steps
        self._flow_data = data

        # --- Field Assertions ---
        for path, expected in step_data["assertions"].items():
            ok = _assert_field(data, path, expected)
            actual = _resolve_path(data, path)
            assert ok, f"[{{path}}] expected={{expected!r}}, actual={{actual!r}}"

        # --- Rule Assertions ---
        rule_results = _assert_rules(data, step_data.get("assert_rules", []))
        for r in rule_results:
            assert r["passed"], f"Rule failed: {{r['field']}} (expected={{r['expected']}}, actual={{r['actual']}})"
{post_calls}
'''
        methods.append(source)

    methods_str = "".join(methods)

    class_source = f'''
class {class_name}:
    """Business flow: {flow.get("sheet_name", f"flow_{index}")}"""

    def setup_method(self):
        self._flow_data = None
{methods_str}
'''
    return class_source


# ============================================================================
# File generators
# ============================================================================

def _write_conftest(output_dir: str) -> None:
    """Write conftest.py to the output directory."""
    path = Path(output_dir) / "conftest.py"
    path.write_text(_CONFTEST_TEMPLATE, encoding="utf-8")
    logger.info("Wrote conftest.py → %s", path)


def _write_ff_compat(output_dir: str) -> None:
    """Write _ff_compat.py to the output directory."""
    path = Path(output_dir) / "_ff_compat.py"
    path.write_text(_FF_COMPAT_TEMPLATE, encoding="utf-8")
    logger.info("Wrote _ff_compat.py → %s", path)


def _write_env_configs(output_dir: str, config_dir: str) -> None:
    """Read env-*.yml files and generate _config.py + _env_*.py."""
    config_path = Path(config_dir)
    env_files = sorted(config_path.glob("env-*.yml"))
    if not env_files:
        logger.debug("No env-*.yml files found in %s", config_dir)
        # Generate a minimal _config.py with empty APPS
        minimal = '''"""Environment selector."""
ENV = "local"
APPS = {}
'''
        (Path(output_dir) / "_config.py").write_text(minimal, encoding="utf-8")
        return

    env_names = []
    for f in env_files:
        name = f.stem.replace("env-", "")  # env-local.yml → local
        env_names.append(name)
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except Exception:
            logger.warning("Failed to read env file: %s", f, exc_info=True)
            data = {}

        # Write _env_{name}.py
        env_py = f'''"""Auto-generated app configurations for '{name}' environment."""
APPS = {json.dumps(data, indent=4, ensure_ascii=False)}
'''
        out_path = Path(output_dir) / f"_env_{name}.py"
        out_path.write_text(env_py, encoding="utf-8")
        logger.info("Wrote _env_%s.py → %s", name, out_path)

    # Write _config.py with environment selector
    first_env = env_names[0] if env_names else "local"
    config_lines = [
        '"""Environment selector — change ENV to switch between environments.',
        '',
        f'Available environments: {env_names}',
        '"""',
        f'ENV = "{first_env}"  # {" | ".join(env_names)}',
        '',
    ]
    for env in env_names:
        config_lines.append(f"if ENV == \"{env}\":")
        config_lines.append(f"    from _env_{env} import APPS  # noqa: E402, F401")

    config_py = "\n".join(config_lines) + "\n"
    (Path(output_dir) / "_config.py").write_text(config_py, encoding="utf-8")
    logger.info("Wrote _config.py → %s", Path(output_dir) / "_config.py")


def _write_single_tests(cases: List[Dict[str, Any]], output_dir: str) -> int:
    """Generate test_single_cases.py."""
    if not cases:
        return 0
    parts = [_SINGLE_HEADER]
    for i, case in enumerate(cases):
        parts.append(_generate_single_test(case, i))
    path = Path(output_dir) / "test_single_cases.py"
    path.write_text("".join(parts), encoding="utf-8")
    logger.info("Wrote test_single_cases.py with %d test(s) → %s", len(cases), path)
    return len(cases)


def _write_biz_flow_tests(flows: List[Dict[str, Any]], output_dir: str) -> int:
    """Generate test_biz_flows.py."""
    if not flows:
        return 0
    parts = [_BIZ_HEADER]
    for i, flow in enumerate(flows):
        src = _generate_biz_flow_class(flow, i)
        if src:
            parts.append(src)
    path = Path(output_dir) / "test_biz_flows.py"
    path.write_text("".join(parts), encoding="utf-8")
    step_count = sum(len(f.get("steps", [])) for f in flows)
    logger.info("Wrote test_biz_flows.py with %d flow(s), %d step(s) → %s",
                len(flows), step_count, path)
    return len(flows)


def _bundle_custom_processors(processors_dir: Optional[str], output_dir: str) -> int:
    """Copy custom processor .py files from *processors_dir*.

    Skips internal modules (base, loader, runner) and built-ins.
    Replaces 'from processors.base import ...' → 'from _ff_compat import ...'.
    """
    if not processors_dir:
        return 0
    src = Path(processors_dir)
    if not src.is_dir():
        return 0

    dest = Path(output_dir) / "_custom_processors"
    internal = {"base", "loader", "runner", "__init__"}
    builtin_names = {"hmac_sign", "hmac_verify", "path_param_restore",
                     "print_demo", "response_time", "timestamp_sign"}
    count = 0
    for py_file in sorted(src.glob("*.py")):
        stem = py_file.stem
        if stem.startswith("_") or stem in internal or stem in builtin_names:
            continue
        content = py_file.read_text(encoding="utf-8")
        # Replace Flow Forge imports with compatibility stubs
        content = content.replace(
            "from processors.base import", "from _ff_compat import"
        )
        content = content.replace(
            "from processors.base import PreProcessor, ProcessorError",
            "from _ff_compat import PreProcessor, ProcessorError",
        )
        content = content.replace(
            "from processors.base import PostProcessor, ProcessorError",
            "from _ff_compat import PostProcessor, ProcessorError",
        )
        # Generic pattern for any combination
        for base_import in [
            "from processors.base import PreProcessor",
            "from processors.base import PostProcessor",
            "from processors.base import ProcessorError",
        ]:
            pass  # handled by the generic 'from processors.base import' replacement

        dest.mkdir(parents=True, exist_ok=True)
        (dest / py_file.name).write_text(content, encoding="utf-8")
        logger.info("Bundled custom processor: %s", py_file.name)
        count += 1

    return count


# ============================================================================
# Public API
# ============================================================================

def yaml_to_pytest(
    output_dir: str,
    *,
    interfaces_dir: Optional[str] = None,
    single_cases_dir: Optional[str] = None,
    biz_flows_dir: Optional[str] = None,
    config_dir: Optional[str] = None,
    processors_dir: Optional[str] = None,
) -> Dict[str, int]:
    """Convert YAML case directories to standalone pytest files.

    All three directories are optional. At least one must be provided.

    Returns:
        ``{"single_cases": N, "biz_flows": N, "custom_processors": N}``
    """
    if not any([interfaces_dir, single_cases_dir, biz_flows_dir]):
        raise ValueError(
            "At least one of --interfaces, --single-cases, or --biz-flows must be provided."
        )

    os.makedirs(output_dir, exist_ok=True)
    config_src = config_dir or "."

    # Always write shared support files
    _write_conftest(output_dir)
    _write_ff_compat(output_dir)
    _write_env_configs(output_dir, config_src)

    # Bundle custom processors
    n_custom = _bundle_custom_processors(processors_dir, output_dir)

    # Read and generate test files
    single_cases = _read_yaml_dir(single_cases_dir) if single_cases_dir else []
    biz_flows = _read_yaml_flows(biz_flows_dir) if biz_flows_dir else []

    n_single = _write_single_tests(single_cases, output_dir)
    n_biz = _write_biz_flow_tests(biz_flows, output_dir)

    return {"single_cases": n_single, "biz_flows": n_biz, "custom_processors": n_custom}


def excel_to_pytest(
    input_path: str,
    output_dir: str,
    *,
    config_dir: Optional[str] = None,
    processors_dir: Optional[str] = None,
) -> Dict[str, int]:
    """Convert Excel workbook to standalone pytest files.

    Auto-detects sheets: "API Definitions" → skipped (no HTTP), "Single Cases"
    → test_single_cases.py, other sheets → test_biz_flows.py.

    Returns:
        ``{"single_cases": N, "biz_flows": N, "custom_processors": N}``
    """
    from .excel_reader import read_excel

    logger.info("Converting Excel → pytest: %s → %s", input_path, output_dir)
    data = read_excel(input_path)

    os.makedirs(output_dir, exist_ok=True)
    config_src = config_dir or "."

    _write_conftest(output_dir)
    _write_ff_compat(output_dir)
    _write_env_configs(output_dir, config_src)

    n_custom = _bundle_custom_processors(processors_dir, output_dir)

    single_cases = data.get("single_cases", [])
    biz_flows = data.get("biz_flows", [])

    n_single = _write_single_tests(single_cases, output_dir)
    n_biz = _write_biz_flow_tests(biz_flows, output_dir)

    return {"single_cases": n_single, "biz_flows": n_biz, "custom_processors": n_custom}
