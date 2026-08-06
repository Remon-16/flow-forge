"""ff_tool validate 单元测试 — 覆盖 schema 校验与处理器配置警告。

Unit tests for ff_tool validate: schema checks and processor config warnings.
"""

import copy
import logging
from pathlib import Path

import yaml

import ff_tool


def _write(tmp_path: Path, rel: str, data: dict) -> Path:
    """写入 YAML 用例文件。Write a YAML case file."""
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    return p


def _run_validate(tmp_path: Path, cfg_dir: Path | None = None) -> int:
    """运行 validate 子命令。Run the validate subcommand."""
    cfg = cfg_dir or tmp_path / "cfg"
    return ff_tool.main(
        [
            "validate",
            "--yamlDir",
            str(tmp_path),
            "--config-dir",
            str(cfg),
            "--env-name",
            "local",
        ]
    )


VALID_SINGLE = {
    "case_type": "single",
    "test_id": "TC_LOGIN_001",
    "relevance_id": "API_LOGIN",
    "api_name": "用户登录",
    "app_name": "someApp",
    "method": "POST",
    "url": "/api/user/login",
    "request_head": {"Content-Type": "application/json"},
    "request_body": {"username": "admin", "password": "123456"},
    "status_code": 200,
    "assert_dict": {"$.code": 0},
    "assert_rules": ["$.data.token is_not_null"],
    "tag": "P0",
    "remark": "正常登录",
}

VALID_BIZ = {
    "case_type": "biz",
    "sheet_name": "注册登录流程",
    "steps": [
        {
            "step_id": "Step01",
            "relevance_id": "API_SMS",
            "api_name": "发送验证码",
            "method": "POST",
            "url": "/api/sms/send",
            "request_body": {"phone": "13800138000"},
            "status_code": 200,
            "assert_dict": {"$.code": 0},
        },
        {
            "step_id": "Step02",
            "relevance_id": "API_REGISTER",
            "api_name": "注册",
            "method": "POST",
            "url": "/api/user/register",
            "request_body": {"phone": "13800138000", "code": "#{smsCode}"},
            "status_code": 200,
            "inherit": {"smsCode": "Step01.data.code"},
        },
    ],
}

VALID_IFACE = {
    "case_type": "interfaces",
    "test_id": "API_LOGIN",
    "api_name": "用户登录",
    "method": "POST",
    "url": "/api/user/login",
}


def test_valid_single_biz_and_interface(tmp_path):
    """合法用例全部通过。Valid cases pass validation."""
    _write(tmp_path, "interfaces/iface.yaml", VALID_IFACE)
    _write(tmp_path, "single_cases/tc1.yaml", VALID_SINGLE)
    _write(tmp_path, "biz_flows/flow1.yaml", VALID_BIZ)
    assert _run_validate(tmp_path) == 0


def test_missing_required_field(tmp_path):
    """缺少必填字段时报错。Missing required fields are errors."""
    case = copy.deepcopy(VALID_SINGLE)
    del case["test_id"]
    _write(tmp_path, "single_cases/bad1.yaml", case)
    assert _run_validate(tmp_path) == 1


def test_invalid_method_tag_status(tmp_path):
    """非法 method/tag/status_code 报错。Invalid method/tag/status_code error."""
    case = copy.deepcopy(VALID_SINGLE)
    case["method"] = "FETCH"
    case["tag"] = "P9"
    case["status_code"] = "ok"
    _write(tmp_path, "single_cases/bad1.yaml", case)
    assert _run_validate(tmp_path) == 1


def test_invalid_assert_rule_operator(tmp_path):
    """无合法运算符的断言规则报错。Rules without a valid operator error."""
    case = copy.deepcopy(VALID_SINGLE)
    case["assert_rules"] = ["$.data.token approx 100"]
    _write(tmp_path, "single_cases/bad1.yaml", case)
    assert _run_validate(tmp_path) == 1


def test_invalid_assert_rule_typeof(tmp_path):
    """typeof 类型非法时报错。Invalid typeof types error."""
    case = copy.deepcopy(VALID_SINGLE)
    case["assert_rules"] = ["$.data.count typeof integer"]
    _write(tmp_path, "single_cases/bad1.yaml", case)
    assert _run_validate(tmp_path) == 1


def test_assert_rule_valid_operators(tmp_path):
    """多种合法运算符通过。Multiple valid operators pass."""
    case = copy.deepcopy(VALID_SINGLE)
    case["assert_rules"] = [
        "$.data.total > 0",
        "$.data.status in ['PAID', 'PENDING']",
        "$.data.tags contains 'vip'",
        "$.data.time =~ ^\\d{4}-\\d{2}-\\d{2}$",
        "$.data.list.length() == 3",
        "$.data.count typeof int",
    ]
    _write(tmp_path, "single_cases/tc1.yaml", case)
    assert _run_validate(tmp_path) == 0


def test_biz_inherit_unknown_step(tmp_path):
    """inherit 引用不存在的 StepID 报错。Unknown StepID in inherit errors."""
    flow = copy.deepcopy(VALID_BIZ)
    flow["steps"][1]["inherit"] = {"smsCode": "Step99.data.code"}
    _write(tmp_path, "biz_flows/flow1.yaml", flow)
    assert _run_validate(tmp_path) == 1


def test_biz_duplicate_step_id(tmp_path):
    """同一链路内 step_id 重复报错。Duplicate step_id errors."""
    flow = copy.deepcopy(VALID_BIZ)
    flow["steps"][1]["step_id"] = "Step01"
    _write(tmp_path, "biz_flows/flow1.yaml", flow)
    assert _run_validate(tmp_path) == 1


def test_biz_inherit_chinese_characters(tmp_path):
    """inherit 含中文字符报错。Chinese characters in inherit error."""
    flow = copy.deepcopy(VALID_BIZ)
    flow["steps"][1]["inherit"] = {"验证码": "Step01.data.code"}
    _write(tmp_path, "biz_flows/flow1.yaml", flow)
    assert _run_validate(tmp_path) == 1


def test_processor_warning_when_config_missing(tmp_path, tmp_path_factory, caplog):
    """处理器缺少 processor_configs 时给出警告而非错误。

    Missing processor_configs produces a warning, not an error.
    """
    case = copy.deepcopy(VALID_SINGLE)
    case["preprocessors"] = [{"name": "hmac-sign", "config": {}}]
    _write(tmp_path, "single_cases/tc1.yaml", case)
    cfg_dir = tmp_path_factory.mktemp("envcfg")
    with open(cfg_dir / "env.yml", "w", encoding="utf-8") as f:
        f.write("processor_configs: {}\n")
    with caplog.at_level(logging.WARNING):
        assert _run_validate(tmp_path, cfg_dir) == 0
    assert any("hmac-sign" in r.message for r in caplog.records)


def test_no_processor_warning_when_configured(tmp_path, tmp_path_factory, caplog):
    """处理器已配置 processor_configs 时不警告。No warning when configured."""
    case = copy.deepcopy(VALID_SINGLE)
    case["preprocessors"] = [{"name": "hmac-sign", "config": {}}]
    _write(tmp_path, "single_cases/tc1.yaml", case)
    cfg_dir = tmp_path_factory.mktemp("envcfg")
    with open(cfg_dir / "env.yml", "w", encoding="utf-8") as f:
        f.write("processor_configs:\n  hmac-sign:\n    secret_env: SIGN_SECRET\n")
    with caplog.at_level(logging.WARNING):
        assert _run_validate(tmp_path, cfg_dir) == 0
    assert not any("hmac-sign" in r.message for r in caplog.records)


def test_no_config_processor_no_warning(tmp_path, tmp_path_factory, caplog):
    """免配置处理器（timestamp）不警告。Config-free processors do not warn."""
    case = copy.deepcopy(VALID_SINGLE)
    case["preprocessors"] = [{"name": "timestamp", "config": {}}]
    _write(tmp_path, "single_cases/tc1.yaml", case)
    cfg_dir = tmp_path_factory.mktemp("envcfg")
    with open(cfg_dir / "env.yml", "w", encoding="utf-8") as f:
        f.write("processor_configs: {}\n")
    with caplog.at_level(logging.WARNING):
        assert _run_validate(tmp_path, cfg_dir) == 0
    assert not any("timestamp" in r.message for r in caplog.records)


def test_url_placeholder_from_body_passes(tmp_path):
    """URL 占位符由 request_body 提供时通过。Body-sourced placeholders pass."""
    case = copy.deepcopy(VALID_SINGLE)
    case["url"] = "/api/users/#{userId}"
    case["request_body"] = {"userId": 12345}
    _write(tmp_path, "single_cases/tc1.yaml", case)
    assert _run_validate(tmp_path) == 0


def test_url_placeholder_from_inherit_passes(tmp_path):
    """URL 占位符由 inherit 提供时通过。Inherit-sourced placeholders pass."""
    flow = copy.deepcopy(VALID_BIZ)
    flow["steps"][1]["url"] = "/api/users/#{userId}"
    flow["steps"][1]["inherit"] = {"userId": "Step01.data.id"}
    _write(tmp_path, "biz_flows/flow1.yaml", flow)
    assert _run_validate(tmp_path) == 0


def test_url_placeholder_without_source_errors(tmp_path):
    """URL 占位符无来源时报错。Placeholders without a source error."""
    case = copy.deepcopy(VALID_SINGLE)
    case["url"] = "/api/users/#{userId}"
    case["request_body"] = {}
    _write(tmp_path, "single_cases/tc1.yaml", case)
    assert _run_validate(tmp_path) == 1


def test_url_placeholder_duplicated_in_body_errors(tmp_path):
    """URL 占位符与 body 同名占位重复时报错（运行时会产生 # 片段）。

    Duplicating a URL placeholder with a same-named placeholder in the body
    errors (it produces a literal '#' fragment at runtime).
    """
    case = copy.deepcopy(VALID_SINGLE)
    case["url"] = "/api/users/#{userId}"
    case["request_body"] = {"userId": "#{userId}"}
    _write(tmp_path, "single_cases/tc1.yaml", case)
    assert _run_validate(tmp_path) == 1
