"""pytest 专属代码模板 — conftest.py 和测试文件头部。
   pytest-specific code templates — conftest.py and test file headers."""

# ============================================================================
# conftest.py 模板（conftest.py template）
# ============================================================================

CONFTEST_TEMPLATE = r'''"""Shared fixtures and helpers — no Flow Forge dependency."""
import importlib
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import pytest
import requests

# 配置根日志记录器，使 print-demo 等处理器的 logger.info() 可见
# Configure root logger so print-demo processor output is visible
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


def pytest_configure(config):
    """配置 pytest 日志输出到 CLI，使 print-demo 处理器默认可见。
       Enable log_cli so print-demo processor output is visible by default."""
    config.option.log_cli = True
    config.option.log_cli_level = "INFO"
    config.option.log_cli_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    config.option.log_cli_date_format = "%H:%M:%S"


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
# 处理器调度（Processor dispatch）
# ============================================================

# 从 _config 中加载 processor_configs，供处理器使用
# Load processor_configs from _config for use by processors
try:
    from _config import APPS as _APPS
    _GLOBAL_CONFIG = {"processor_configs": _APPS.get("processor_configs", {})}
except ImportError:
    _GLOBAL_CONFIG = {}


# 处理器类缓存：processor_name → class
# Processor class cache: processor_name → class
_PROCESSOR_CACHE: Dict[str, Any] = {}


def _build_processor_cache():
    """扫描 _processors/ 目录（含子目录），建立处理器名 → 类的缓存。
       Scan _processors/ directory (including subdirs) and build name → class cache."""
    if _PROCESSOR_CACHE:
        return
    try:
        import pkgutil
        import _processors as pkg
        for _importer, mod_name, _is_pkg in pkgutil.walk_packages(
            pkg.__path__, pkg.__name__ + "."
        ):
            try:
                mod = importlib.import_module(mod_name)
            except ImportError:
                continue
            for attr_name in dir(mod):
                obj = getattr(mod, attr_name)
                if isinstance(obj, type) and hasattr(obj, 'name'):
                    pname = getattr(obj, 'name', None)
                    if pname:
                        _PROCESSOR_CACHE[pname] = obj
    except ImportError:
        pass


def _get_processor_class(processor_name: str):
    """从 _processors 缓存中获取处理器类。
       Get processor class from _processors cache."""
    _build_processor_cache()
    cls = _PROCESSOR_CACHE.get(processor_name)
    if cls is not None:
        return cls
    raise ImportError(
        f"No processor class found for '{processor_name}'. "
        f"Available: {list(_PROCESSOR_CACHE.keys())}"
    )


def _run_preprocessor(name: str, headers: Dict[str, Any], body: Dict[str, Any],
                      config: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """动态加载并执行前置处理器。
       Dynamically load and execute a preprocessor by name.

       Returns (modified_headers, modified_body).
    """
    cls = _get_processor_class(name)
    instance = cls()
    return instance.process(headers, body, config or {}, _GLOBAL_CONFIG)


def _run_postprocessor(name: str, req_headers: Dict[str, Any], req_body: Dict[str, Any],
                       resp_headers: Dict[str, Any], resp_body: Any,
                       config: Optional[Dict[str, Any]] = None) -> None:
    """动态加载并执行后置处理器。
       Dynamically load and execute a postprocessor by name."""
    cls = _get_processor_class(name)
    instance = cls()
    instance.process(req_headers, req_body, resp_headers, resp_body, config or {}, _GLOBAL_CONFIG)


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
    "_run_preprocessor",
    "_run_postprocessor",
    "_get_processor_class",
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
