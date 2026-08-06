"""转换器往返与整包打包测试。
   Round-trip and whole-package bundling tests for the converter.

覆盖 yaml→excel→yaml 字段守恒、带连字符环境名的 _config.py 生成，
以及 yaml2pytest 整包打包（_processors/_auth/_resolvers）与处理器扫描。
Covers yaml→excel→yaml field preservation, _config.py generation for env
names with hyphens, and whole-package bundling (with processor scanning).
"""

import json
import os
import subprocess
import sys
import tempfile

import yaml

from converter.converter import excel_to_yaml, yaml_to_excel
from converter.pytest_writer import yaml_to_pytest


def _write_case(dir_path: str, name: str, case: dict) -> str:
    """写入单个用例 YAML 并返回路径。Write one case YAML and return its path."""
    os.makedirs(dir_path, exist_ok=True)
    path = os.path.join(dir_path, f"{name}.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(case, f, allow_unicode=True, sort_keys=False)
    return path


def _read_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _normalize(case: dict) -> dict:
    """去掉 case_type 后规范化，用于往返对比。
       Drop case_type before comparison (added back by excel2yaml)."""
    out = {k: v for k, v in case.items() if k != "case_type"}
    return out


class TestYamlExcelYamlRoundTrip:
    """yaml → excel → yaml 往返应保持全部字段。
       yaml → excel → yaml must preserve all case fields."""

    def should_preserve_login_case_fields(self):
        d = tempfile.mkdtemp()
        cases_dir = os.path.join(d, "single_cases")
        case = {
            "case_type": "single",
            "test_id": "TC_ROUNDTRIP_001",
            "relevance_id": "API_002",
            "tag": "P0",
            "api_name": "login-roundtrip",
            "app_name": "foliMail",
            "method": "POST",
            "url": "/api/auth/login",
            "request_head": {"Content-Type": "application/json"},
            "request_body": {"username": "admin", "password": "admin123"},
            "status_code": 200,
            "preprocessors": [
                {"name": "print-demo", "config": {"prefix": "[RoundTrip]"}},
                {"name": "timestamp", "config": {}},
            ],
            "postprocessors": [{"name": "response-time", "config": {}}],
            "assert_dict": {"code": "100000", "message": "成功"},
            "assert_rules": [
                "$.data.token is_not_null",
                "$.data.username is_not_null",
            ],
        }
        _write_case(cases_dir, "roundtrip", case)

        xlsx = os.path.join(d, "cases.xlsx")
        yaml_to_excel(xlsx, single_cases_dir=cases_dir)
        out_dir = os.path.join(d, "yaml_out")
        excel_to_yaml(xlsx, out_dir)

        generated = _read_yaml(os.path.join(out_dir, "single_cases", "TC_ROUNDTRIP_001.yaml"))
        assert _normalize(generated) == _normalize(case)

    def should_preserve_token_placeholder_and_db_config(self):
        """含 #{buyer01} 占位符、中文断言与处理器 config 的用例应原样保留。
           Cases with #{buyer01} placeholder, Chinese assertions and processor
           config must survive the round trip unchanged."""
        d = tempfile.mkdtemp()
        cases_dir = os.path.join(d, "single_cases")
        case = {
            "case_type": "single",
            "test_id": "TC_RETURN_ROUNDTRIP_001",
            "relevance_id": "E2E",
            "tag": "P0",
            "api_name": "return-roundtrip",
            "app_name": "foliMail",
            "method": "POST",
            "url": "/api/returns",
            "request_head": {
                "Content-Type": "application/json",
                "Authorization": "Bearer #{buyer01}",
            },
            "request_body": {"returnReason": "e2e-test-return", "returnType": 1},
            "status_code": 200,
            "preprocessors": [
                {"name": "return-order-db", "config": {"order_status": 4}}
            ],
            "postprocessors": [{"name": "return-order-db", "config": {}}],
            "assert_dict": {"code": "100000"},
            "assert_rules": ["$.data.returnNo is_not_null"],
        }
        _write_case(cases_dir, "return_roundtrip", case)

        xlsx = os.path.join(d, "cases.xlsx")
        yaml_to_excel(xlsx, single_cases_dir=cases_dir)
        out_dir = os.path.join(d, "yaml_out")
        excel_to_yaml(xlsx, out_dir)

        generated = _read_yaml(
            os.path.join(out_dir, "single_cases", "TC_RETURN_ROUNDTRIP_001.yaml")
        )
        assert _normalize(generated) == _normalize(case)


class TestWholePackageBundling:
    """yaml2pytest 应整包复制处理器及其框架依赖。
       yaml2pytest must bundle the whole processors package and framework deps."""

    def _generate(self):
        d = tempfile.mkdtemp()
        cases_dir = os.path.join(d, "single_cases")
        _write_case(cases_dir, "bundle_case", {
            "case_type": "single",
            "test_id": "TC_BUNDLE_001",
            "method": "GET",
            "url": "/api/ping",
            "request_head": {},
            "request_body": {},
            "status_code": 200,
            "assert_dict": {},
            "assert_rules": [],
            "preprocessors": [{"name": "cache-handler", "config": {}}],
            "postprocessors": [],
        })
        # 环境名带连字符，验证 _config.py 模块名被清洗。
        # Env name contains a hyphen; verify the generated module name is sanitized.
        config_dir = os.path.join(d, "config")
        os.makedirs(config_dir)
        with open(os.path.join(config_dir, "env-plugin-test.yml"), "w", encoding="utf-8") as f:
            yaml.safe_dump({
                "foliMail": {"baseURL": "http://localhost:8080"},
                "processor_configs": {
                    "cache-handler": {"redis_url": "redis://localhost:6379/0"}
                },
            }, f)

        out = os.path.join(d, "output")
        yaml_to_pytest(
            output_dir=out,
            single_cases_dir=cases_dir,
            config_dir=config_dir,
        )
        return out

    def should_bundle_processors_and_framework_deps(self):
        out = self._generate()
        expected = [
            "_processors/base.py",
            "_processors/redis.py",
            "_processors/db.py",
            "_processors/rocketmq.py",
            "_processors/builtin/redis/cache_handler.py",
            "_processors/builtin/db/return_order.py",
            "_auth/login_manager.py",
            "_resolvers/path_resolver.py",
            "_ff_compat.py",
        ]
        for rel in expected:
            assert os.path.isfile(os.path.join(out, rel)), f"missing {rel}"

    def should_sanitize_env_module_name(self):
        out = self._generate()
        config_py = open(os.path.join(out, "_config.py"), encoding="utf-8").read()
        assert "ENV = \"plugin-test\"" in config_py
        assert "from _env_plugin_test import APPS" in config_py
        assert os.path.isfile(os.path.join(out, "_env_plugin_test.py"))

    def should_collect_and_scan_bundled_processors(self):
        """生成代码应可 collect，且能扫描到中间件处理器类。
           Generated code must collect and scan middleware processor classes."""
        out = self._generate()
        collect = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            cwd=out,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        assert collect.returncode == 0, collect.stdout + collect.stderr

        scan = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from conftest import _get_processor_class; "
                    "print(_get_processor_class('cache-handler', 'pre').__name__)"
                ),
            ],
            cwd=out,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        assert scan.returncode == 0, scan.stdout + scan.stderr
        assert "CacheHandlerPluginPreWrapper" in scan.stdout
