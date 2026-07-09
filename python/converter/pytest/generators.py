"""pytest 测试函数/类代码生成器。
   pytest test function/class code generators."""

from __future__ import annotations

import json
from typing import Any

from ..common.utils import sanitize_name, indent_lines
from ..common.export_utils import PREPROC_DISPATCH, POSTPROC_DISPATCH


def _normalize_processor_list(value: Any) -> list[dict[str, Any]]:
    """规范化处理器列表为 [{"name": ..., "config": {}}, ...] 格式。
       Normalize processor list to list-of-dicts format.

       支持格式 / Supported formats：
       - None / [] → []
       - "print-demo" → [{"name": "print-demo", "config": {}}]
       - ["print-demo", "hmac-sign"] → [{"name": "print-demo", ...}, ...]
       - [{"name": "print-demo", "config": {...}}] → 原样返回 / pass-through
    """
    if not value:
        return []
    if isinstance(value, list):
        result: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                result.append(item)
            elif isinstance(item, str):
                result.append({"name": item.strip(), "config": {}})
        return result
    if isinstance(value, str):
        # 逗号分隔的多个处理器 / comma-separated processor names
        names = [n.strip() for n in value.split(",") if n.strip()]
        return [{"name": n, "config": {}} for n in names]
    return []


def generate_preprocessor_calls(preprocessors: list) -> str:
    """生成前置处理器调度代码（插入到测试函数体中）。
       Generate preprocessor dispatch code for a test function body."""
    preprocessors = _normalize_processor_list(preprocessors)
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
    postprocessors = _normalize_processor_list(postprocessors)
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


def test_{test_id}():
    case = CASE_{test_id}
    url = _resolve_url(_get_base_url(case.get("app_name")) + case["url"], case["body"])
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
    """生成 class TestBizFlow_xxx: 测试类，所有步骤在单个 test 方法中顺序执行。
       Generate a pytest test class with all steps in a single sequential test method."""
    sheet_name = sanitize_name(flow.get("sheet_name", f"flow_{index}"))
    steps: list[dict[str, Any]] = flow.get("steps", [])
    if not steps:
        return ""

    class_name = f"TestBizFlow_{sheet_name}"
    constants_parts: list[str] = []
    step_bodies: list[str] = []

    for si, step in enumerate(steps):
        step_id = sanitize_name(step.get("step_id", f"step_{si}"))
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

        # 构建 STEP 数据常量（Build STEP data constant）
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
        constants_parts.append(f"    STEP_{step_id} = {data_block}")

        # ==== 构建步骤体 / Build step body ====
        is_first = (si == 0)
        body_lines: list[str] = []

        # 步骤标题 / Step header
        body_lines.append(f"        # ===== Step {si}: {step_id} =====")
        body_lines.append(f"        step_data = self.STEP_{step_id}")
        body_lines.append(
            "        url = _resolve_url(_get_base_url(step_data.get(\"app_name\"))"
            " + step_data[\"url\"], step_data[\"body\"])"
        )
        body_lines.append("        headers = dict(step_data[\"headers\"])")
        body_lines.append("        body = dict(step_data[\"body\"])")
        body_lines.append("")

        # 从上游步骤响应中解析流程变量 / resolve flow variables from previous steps
        if not is_first and inherit:
            body_lines.append(
                "        # 从上游步骤响应中解析流程变量 / "
                "resolve #{var} from flow_data"
            )
            for var, expr in inherit.items():
                safe_var = sanitize_name(var)
                body_lines.append(
                    f"        _fv_{safe_var} = _resolve_path(_flow_data, \"{expr}\")"
                )
                body_lines.append(
                    f"        if not isinstance(_fv_{safe_var}, _Missing):"
                )
                body_lines.append(
                    f"            for _hk in list(headers.keys()):"
                )
                body_lines.append(
                    f"                _hv = headers[_hk]"
                )
                body_lines.append(
                    f"                if isinstance(_hv, str):"
                )
                body_lines.append(
                    f"                    headers[_hk] = _hv.replace("
                    f"\"#{{{var}}}\", str(_fv_{safe_var}))"
                )
            body_lines.append("")

        # Token 解析 / token resolution (剩余的用户凭证占位符)
        if app_name:
            body_lines.append(
                f"        headers = _resolve_token(headers, \"{app_name}\")"
            )
            body_lines.append("")

        # 步骤间变量传递（body 字段继承）/ Inherit: copy flow_data values to body
        if inherit:
            body_lines.append(
                "        # --- Inherit (step variable passing) ---"
            )
            for var, expr in inherit.items():
                body_lines.append(
                    f"        body[\"{var}\"] = "
                    f"_resolve_path(_flow_data, \"{expr}\")"
                )
            body_lines.append("")

        # 前置处理器 / PreProcessors
        pre_calls = generate_preprocessor_calls(preprocessors)
        if pre_calls:
            body_lines.append(indent_lines(pre_calls, 4).rstrip())
            body_lines.append("")

        # HTTP 请求 / HTTP Request
        body_lines.append("        # --- HTTP Request ---")
        body_lines.append("        resp = requests.request(")
        body_lines.append(
            "            step_data[\"method\"], url, headers=headers,"
        )
        body_lines.append(
            "            json=body if body else None, timeout=30)"
        )
        body_lines.append("")
        body_lines.append(
            "        assert resp.status_code == step_data[\"expected_status\"], \\"
        )
        body_lines.append(
            "            f\"Expected {step_data['expected_status']}, "
            "got {resp.status_code}\""
        )
        body_lines.append("")
        body_lines.append(
            "        data = resp.json() if resp.headers.get(\"Content-Type\", \"\")"
            ".startswith(\"application/json\") else resp.text"
        )
        body_lines.append("")

        # 存储响应供下游步骤使用 / store response for downstream steps
        body_lines.append(
            f"        # 存储响应供下游步骤使用 / store for downstream"
        )
        body_lines.append(f"        _flow_data[\"{step_id}\"] = data")
        body_lines.append("")

        # 字段断言 / Field Assertions
        body_lines.append("        # --- Field Assertions ---")
        body_lines.append(
            "        for path, expected in step_data[\"assertions\"].items():"
        )
        body_lines.append(
            "            ok = _assert_field(data, path, expected)"
        )
        body_lines.append(
            "            actual = _resolve_path(data, path)"
        )
        body_lines.append(
            "            assert ok, f\"[{path}] expected={expected!r},"
            " actual={actual!r}\""
        )
        body_lines.append("")

        # 规则断言 / Rule Assertions
        body_lines.append("        # --- Rule Assertions ---")
        body_lines.append(
            "        rule_results = _assert_rules("
            "data, step_data.get(\"assert_rules\", []))"
        )
        body_lines.append("        for r in rule_results:")
        body_lines.append(
            "            assert r[\"passed\"], "
            "f\"Rule failed: {r['field']} (expected={r['expected']},"
            " actual={r['actual']})\""
        )

        # 后置处理器 / PostProcessors
        post_calls = generate_postprocessor_calls(postprocessors)
        if post_calls:
            body_lines.append("")
            body_lines.append(indent_lines(post_calls, 4).rstrip())

        step_bodies.append("\n".join(body_lines))

    constants_str = "\n".join(constants_parts)
    bodies_str = "\n\n".join(step_bodies)

    return f'''
class {class_name}:
    """Business flow: {flow.get("sheet_name", f"flow_{index}")}"""

{constants_str}

    def test_biz_flow(self):
        """执行完整业务链路 / Execute the full business flow."""
        _flow_data = {{}}

{bodies_str}
'''
