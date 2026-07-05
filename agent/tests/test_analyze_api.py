"""测试 _print_uncertainties 和 _get_item_issues / Tests for _print_uncertainties and _get_item_issues.

No real LLM calls. Uses caplog to verify log output.
"""

import logging

import pytest

from graph.nodes.analyze_api import _get_item_issues, _print_uncertainties


class TestGetItemIssues:
    """Tests for _get_item_issues()."""

    def should_return_critical_auth_when_unknown(self):
        """auth_type 为 UNKNOWN 时返回对应问题。
        When auth_type is UNKNOWN, return the corresponding issue.
        """
        item = {
            "method": "GET",
            "api_path": "/api/test",
            "auth_type": "UNKNOWN",
            "need_token": False,
            "description": "test endpoint",
        }
        issues = _get_item_issues(item)
        assert len(issues) == 1
        assert "auth_type" in issues[0]

    def should_return_critical_token_when_none(self):
        """need_token 为 None 时返回对应问题。
        When need_token is None, return the corresponding issue.
        """
        item = {
            "method": "GET",
            "api_path": "/api/test",
            "auth_type": "none",
            "need_token": None,
            "description": "test endpoint",
        }
        issues = _get_item_issues(item)
        assert len(issues) == 1
        assert "token" in issues[0]

    def should_return_critical_description_when_missing(self):
        """description 缺失时返回对应问题。
        When description is missing, return the corresponding issue.
        """
        item = {
            "method": "GET",
            "api_path": "/api/test",
            "auth_type": "none",
            "need_token": False,
            "description": "",
        }
        issues = _get_item_issues(item)
        assert len(issues) == 1
        assert "描述" in issues[0] or "description" in issues[0]

    def should_return_critical_description_when_unknown(self):
        """description 为 UNKNOWN 时返回对应问题。
        When description is UNKNOWN, return the corresponding issue.
        """
        item = {
            "method": "GET",
            "api_path": "/api/test",
            "auth_type": "none",
            "need_token": False,
            "description": "UNKNOWN",
        }
        issues = _get_item_issues(item)
        assert len(issues) == 1
        assert "描述" in issues[0] or "description" in issues[0]

    def should_return_uncertainties_string_as_item(self):
        """uncertainties 为字符串时纳入 issue 列表。
        When uncertainties is a string, include it in the issue list.
        """
        item = {
            "method": "POST",
            "api_path": "/api/orders",
            "auth_type": "none",
            "need_token": False,
            "description": "test",
            "uncertainties": "接口描述缺失",
        }
        issues = _get_item_issues(item)
        assert "接口描述缺失" in issues

    def should_return_uncertainties_list_as_items(self):
        """uncertainties 为列表时纳入 issue 列表。
        When uncertainties is a list, include them in the issue list.
        """
        item = {
            "method": "GET",
            "api_path": "/api/users",
            "auth_type": "none",
            "need_token": False,
            "description": "test",
            "uncertainties": ["问题一", "问题二"],
        }
        issues = _get_item_issues(item)
        assert "问题一" in issues
        assert "问题二" in issues

    def should_return_empty_for_clean_item(self):
        """所有字段正常时返回空列表。
        When all fields are normal, return an empty list.
        """
        item = {
            "method": "DELETE",
            "api_path": "/api/items/{id}",
            "auth_type": "bearer",
            "need_token": True,
            "description": "Delete an item",
        }
        issues = _get_item_issues(item)
        assert issues == []

    def should_return_multiple_critical_issues(self):
        """多个 critical 字段有问题时，全部返回。
        When multiple critical fields have issues, return all.
        """
        item = {
            "method": "PUT",
            "api_path": "/api/config",
            "auth_type": "UNKNOWN",
            "need_token": None,
            "description": "",
        }
        issues = _get_item_issues(item)
        assert len(issues) == 3

    def should_combine_critical_and_uncertainties(self):
        """同时有 critical 问题和 uncertainties 时，全部返回。
        When both critical issues and uncertainties exist, return all.
        """
        item = {
            "method": "POST",
            "api_path": "/api/items",
            "auth_type": "UNKNOWN",
            "need_token": None,
            "description": "UNKNOWN",
            "uncertainties": ["额外问题"],
        }
        issues = _get_item_issues(item)
        assert len(issues) == 4
        assert "额外问题" in issues


class TestPrintUncertainties:
    """Tests for _print_uncertainties()."""

    def should_print_string_uncertainties_as_single_item(self, caplog):
        """LLM 返回字符串时，应打印为一行而非逐字打印。
        When uncertainties is a string, log it as one line, not char by char.
        """
        summary = [{
            "method": "POST",
            "api_path": "/api/orders",
            "auth_type": "none",
            "need_token": False,
            "description": "test",
            "uncertainties": "接口描述缺失",
        }]

        with caplog.at_level(logging.INFO):
            _print_uncertainties(summary)

        # header + 1 uncertainty item
        assert len(caplog.records) == 2
        assert "[POST /api/orders]" in caplog.records[0].message
        assert "接口描述缺失" in caplog.records[1].message

    def should_print_list_uncertainties_as_multiple_items(self, caplog):
        """LLM 返回列表时，每项各占一行。
        When uncertainties is a list, log each item on its own line.
        """
        summary = [{
            "method": "GET",
            "api_path": "/api/users",
            "auth_type": "none",
            "need_token": False,
            "description": "test",
            "uncertainties": [
                "是否需要 admin 权限？",
                "分页参数是否必填？",
            ],
        }]

        with caplog.at_level(logging.INFO):
            _print_uncertainties(summary)

        # header + 2 items
        assert len(caplog.records) == 3
        assert "[GET /api/users]" in caplog.records[0].message
        assert "是否需要 admin 权限？" in caplog.records[1].message
        assert "分页参数是否必填？" in caplog.records[2].message

    @pytest.mark.parametrize("value", ["", [], None])
    def should_skip_empty_uncertainties_when_no_critical(self, caplog, value):
        """空 uncertainties 且无 critical 问题时，不产生日志。
        Empty uncertainties with no critical issues produce no log output.
        """
        summary = [{
            "method": "PUT",
            "api_path": "/api/items",
            "auth_type": "none",
            "need_token": False,
            "description": "test",
            "uncertainties": value,
        }]

        with caplog.at_level(logging.INFO):
            _print_uncertainties(summary)

        assert len(caplog.records) == 0

    def should_skip_missing_uncertainties_field_when_no_critical(self, caplog):
        """缺少 uncertainties 字段且无 critical 问题时，不输出。
        Missing uncertainties field with no critical issues produces no log.
        """
        summary = [{
            "method": "DELETE",
            "api_path": "/api/items/{id}",
            "auth_type": "none",
            "need_token": False,
            "description": "test",
        }]

        with caplog.at_level(logging.INFO):
            _print_uncertainties(summary)

        assert len(caplog.records) == 0

    def should_log_endpoint_header_before_items(self, caplog):
        """每个有不确定项的接口先打印 header 再打印条目。
        Endpoint header is logged before items.
        """
        summary = [{
            "method": "PATCH",
            "api_path": "/api/config",
            "auth_type": "none",
            "need_token": False,
            "description": "test",
            "uncertainties": "配置项 schema 未定义",
        }]

        with caplog.at_level(logging.INFO):
            _print_uncertainties(summary)

        assert len(caplog.records) == 2
        assert "[PATCH /api/config]" in caplog.records[0].message
        assert "配置项 schema 未定义" in caplog.records[1].message

    def should_handle_mixed_sources(self, caplog):
        """混合：有的有 uncertainties，有的没有，有的为空字符串。
        Mixed: some with uncertainties, some without, some with empty string.
        """
        summary = [
            {
                "method": "GET",
                "api_path": "/api/a",
                "auth_type": "none",
                "need_token": False,
                "description": "test",
                "uncertainties": "需要确认 auth 方式",
            },
            {
                "method": "POST",
                "api_path": "/api/b",
                "auth_type": "none",
                "need_token": False,
                "description": "test",
            },
            {
                "method": "PUT",
                "api_path": "/api/c",
                "auth_type": "none",
                "need_token": False,
                "description": "test",
                "uncertainties": ["问题一", "问题二"],
            },
            {
                "method": "DELETE",
                "api_path": "/api/d",
                "auth_type": "none",
                "need_token": False,
                "description": "test",
                "uncertainties": "",
            },
        ]

        with caplog.at_level(logging.INFO):
            _print_uncertainties(summary)

        # /api/a: header + 1 item = 2 records
        # /api/b: skipped (no issues)
        # /api/c: header + 2 items = 3 records
        # /api/d: empty string skipped
        # Total: 5 records
        assert len(caplog.records) == 5

        messages = [r.message for r in caplog.records]
        assert "[GET /api/a]" in messages[0]
        assert "需要确认 auth 方式" in messages[1]
        assert "[PUT /api/c]" in messages[2]
        assert "问题一" in messages[3]
        assert "问题二" in messages[4]

    def should_print_critical_fields_when_uncertainties_empty(self, caplog):
        """uncertainties 为空但 critical 字段有问题时，仍打印 critical 信息。
        When uncertainties is empty but critical fields have issues, print critical info.
        """
        summary = [{
            "method": "POST",
            "api_path": "/api/orders",
            "auth_type": "UNKNOWN",
            "need_token": None,
            "description": "",
            "uncertainties": "",
        }]

        with caplog.at_level(logging.INFO):
            _print_uncertainties(summary)

        # header + 3 critical items
        assert len(caplog.records) == 4
        assert "[POST /api/orders]" in caplog.records[0].message
        messages = [r.message for r in caplog.records]
        assert any("auth_type" in m for m in messages)
        assert any("token" in m for m in messages)
        assert any("描述" in m or "description" in m for m in messages)

    def should_print_both_critical_and_uncertainties(self, caplog):
        """同时有 critical 字段问题和 uncertainties 时，全部打印。
        When both critical fields and uncertainties exist, print all.
        """
        summary = [{
            "method": "GET",
            "api_path": "/api/users",
            "auth_type": "UNKNOWN",
            "need_token": False,
            "description": "test",
            "uncertainties": "需要确认权限",
        }]

        with caplog.at_level(logging.INFO):
            _print_uncertainties(summary)

        # header + 1 critical + 1 uncertainty = 3 records
        assert len(caplog.records) == 3
        assert "[GET /api/users]" in caplog.records[0].message
        messages = [r.message for r in caplog.records]
        assert any("auth_type" in m for m in messages)
        assert any("需要确认权限" in m for m in messages)
