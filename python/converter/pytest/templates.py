"""pytest 专属代码模板 — conftest.py 和测试文件头部。
   pytest-specific code templates — conftest.py and test file headers."""

# ============================================================================
# conftest.py 模板（conftest.py template）
# ============================================================================

CONFTEST_TEMPLATE = r'''"""Shared fixtures and helpers — no Flow Forge dependency."""
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

def _get_base_url(app_name=None):
    """从 app 配置或环境变量中获取 base URL。
       Resolve base URL from app config or environment variable."""
    # 环境变量优先 / env var takes precedence
    base = os.environ.get("BASE_URL")
    if base:
        return base.rstrip("/")
    if app_name:
        try:
            from _config import APPS  # noqa: F401
            return APPS[app_name]["baseURL"].rstrip("/")
        except (ImportError, KeyError, TypeError):
            pass
    return "http://localhost:8000"


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


# ============================================================
# 导出列表 — 供测试文件 from conftest import * 使用
# Export list — for test files to use "from conftest import *"
# ============================================================

__all__ = [
    "_Missing",
    "_get_base_url",
    "_resolve_path",
    "_resolve_url",
    "_assert_field",
    "_assert_rules",
    "_resolve_token",
    "_apply_timestamp",
    "_apply_hmac_sign",
    "_print_request",
    "_verify_hmac",
    "_log_response_metrics",
    "_print_response",
]
'''


# ============================================================================
# 测试文件头部模板（Test file header templates）
# ============================================================================

SINGLE_HEADER = '''"""Auto-generated single API test cases — standalone pytest.

Generated by Flow Forge converter.  Run with::

    python -m pytest test_single_cases.py -v

Edit the CASE_* constants to adjust request parameters.
"""

import logging
import json
import pytest
import requests

# conftest 辅助函数 / conftest helper functions
from conftest import *  # noqa: F403, E402

logger = logging.getLogger(__name__)

'''


BIZ_HEADER = '''"""Auto-generated business flow test cases — standalone pytest.

Generated by Flow Forge converter.  Run with::

    python -m pytest test_biz_flows.py -v

Each class represents one business flow; each method is one step.
"""

import logging
import json
import pytest
import requests

# conftest 辅助函数 / conftest helper functions
from conftest import *  # noqa: F403, E402

logger = logging.getLogger(__name__)

'''
