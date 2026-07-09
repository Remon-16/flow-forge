"""pytest 测试函数/类代码生成器。
   pytest test function/class code generators."""

from __future__ import annotations

import json
from typing import Any

from ..common.utils import sanitize_name, indent_lines
from ..common.export_utils import PREPROC_DISPATCH, POSTPROC_DISPATCH


def generate_preprocessor_calls(preprocessors: list) -> str:
    """生成前置处理器调度代码（插入到测试函数体中）。
       Generate preprocessor dispatch code for a test function body."""
    if not preprocessors:
        return ""
    lines = ["    # --- PreProcessors ---"]
    for pp in preprocessors:
        name = pp.get("name", "")
        func = PREPROC_DISPATCH.get(name)
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
            lines.append(f"    # Custom processor '{name}' — "
                         f"check _custom_processors/ for implementation")
            lines.append(f"    # from _custom_processors.{name.replace('-', '_')} "
                         f"import process; process(headers, body, {config}, {{}})")
    lines.append("")
    return "\n".join(lines) + "\n"


def generate_postprocessor_calls(postprocessors: list) -> str:
    """生成后置处理器调度代码（插入到测试函数体中）。
       Generate postprocessor dispatch code for a test function body."""
    if not postprocessors:
        return ""
    lines = ["    # --- PostProcessors ---"]
    for pp in postprocessors:
        name = pp.get("name", "")
        func = POSTPROC_DISPATCH.get(name)
        config = json.dumps(pp.get("config", {}) or {})
        if func:
            if name == "response-time":
                threshold = (pp.get("config") or {}).get("warn_threshold_bytes", 1048576)
                lines.append(f"    {func}(resp.headers, data, threshold={threshold})")
            elif name == "print-demo-post":
                prefix = (pp.get("config") or {}).get("prefix", "[PostDemo]")
                lines.append(f"    {func}(resp.headers, data, prefix={json.dumps(prefix)})")
            elif name == "hmac-verify":
                lines.append(f"    {func}(resp.headers, data, {config})")
            else:
                lines.append(f"    {func}(resp.headers, data, {config})")
        else:
            lines.append(f"    # Custom postprocessor '{name}'")
    lines.append("")
    return "\n".join(lines) + "\n"


def generate_single_test(case: dict[str, Any], index: int) -> str:
    """生成单个 def test_xxx(base_url): 测试函数。
       Generate a single pytest test function."""
    test_id = sanitize_name(case.get("test_id", f"case_{index}"))
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

    # 构建数据常量（Build the data constant）
    case_data: dict[str, Any] = {
        "test_id": case.get("test_id", f"case_{index}"),
        "method": method,
        "url": url,
        "headers": headers,
        "body": body,
        "expected_status": int(status_code),
        "assertions": assert_dict,
        "assert_rules": assert_rules,
    }
    if app_name:
        case_data["app_name"] = app_name

    data_block = json.dumps(case_data, indent=4, ensure_ascii=False)

    pre_calls = generate_preprocessor_calls(preprocessors)
    post_calls = generate_postprocessor_calls(postprocessors)

    token_line = ""
    if app_name:
        token_line = f'\n    headers = _resolve_token(headers, "{app_name}")'

    return f'''
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


def generate_biz_flow_class(flow: dict[str, Any], index: int) -> str:
    """生成 class TestBizFlow_xxx: 测试类及步骤方法。
       Generate a pytest test class for a business flow."""
    sheet_name = sanitize_name(flow.get("sheet_name", f"flow_{index}"))
    steps: list[dict[str, Any]] = flow.get("steps", [])
    if not steps:
        return ""

    class_name = f"TestBizFlow_{sheet_name}"
    methods = []

    for si, step in enumerate(steps):
        step_id = sanitize_name(step.get("step_id", f"step_{si}"))
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
        # 归一化 inherit：Excel 中为 JSON 字符串，需转为 dict
        # Normalize inherit: stored as JSON string in Excel, convert to dict
        if isinstance(inherit, str):
            try:
                inherit = json.loads(inherit)
            except (json.JSONDecodeError, ValueError):
                inherit = {}

        case_data: dict[str, Any] = {
            "step_id": step.get("step_id", f"step_{si}"),
            "method": method,
            "url": url,
            "headers": headers,
            "body": body,
            "expected_status": int(status_code),
            "assertions": assert_dict,
            "assert_rules": assert_rules,
        }
        if app_name:
            case_data["app_name"] = app_name

        data_block = json.dumps(case_data, indent=8, ensure_ascii=False)

        # 步骤间变量传递（Step variable inheritance）
        inherit_lines = ""
        if inherit:
            inherit_lines = "        # --- Inherit (step variable passing) ---\n"
            for var, expr in inherit.items():
                inherit_lines += (
                    f"        step_data[\"body\"][\"{var}\"] = "
                    f"_resolve_path(self._flow_data, \"{expr}\")\n"
                )

        pre_calls = indent_lines(generate_preprocessor_calls(preprocessors), 8)
        post_calls = indent_lines(generate_postprocessor_calls(postprocessors), 8)

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

    return f'''
class {class_name}:
    """Business flow: {flow.get("sheet_name", f"flow_{index}")}"""

    def setup_method(self):
        self._flow_data = None
{methods_str}
'''
