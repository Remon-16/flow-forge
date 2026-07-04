"""测试 _print_uncertainties 日志输出 / Tests for _print_uncertainties logging.

No real LLM calls. Uses caplog to verify log output.
"""

import logging

import pytest

from graph.nodes.analyze_api import _print_uncertainties


class TestPrintUncertainties:
    """Tests for _print_uncertainties()."""

    def should_print_string_uncertainties_as_single_item(self, caplog):
        """LLM 返回字符串时，应打印为一行而非逐字打印。
        When uncertainties is a string, log it as one line, not char by char.
        """
        summary = [{
            "method": "POST",
            "api_path": "/api/orders",
            "uncertainties": "接口描述缺失",
        }]

        with caplog.at_level(logging.INFO):
            _print_uncertainties(summary)

        # 应包含 header + 1 条 uncertainty item（不是逐字打印）
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
    def should_skip_empty_uncertainties(self, caplog, value):
        """空字符串 / 空列表 / None 不产生日志输出。
        Empty uncertainties produce no log output.
        """
        summary = [{
            "method": "PUT",
            "api_path": "/api/items",
            "uncertainties": value,
        }]

        with caplog.at_level(logging.INFO):
            _print_uncertainties(summary)

        assert len(caplog.records) == 0

    def should_skip_missing_uncertainties_field(self, caplog):
        """缺少 uncertainties 字段时不输出。
        Missing uncertainties field produces no log output.
        """
        summary = [{
            "method": "DELETE",
            "api_path": "/api/items/{id}",
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
            "uncertainties": "配置项 schema 未定义",
        }]

        with caplog.at_level(logging.INFO):
            _print_uncertainties(summary)

        assert len(caplog.records) == 2
        assert "[PATCH /api/config]" in caplog.records[0].message
        assert "配置项 schema 未定义" in caplog.records[1].message

    def should_handle_mixed_sources(self, caplog):
        """混合：有的接口有 uncertainties，有的没有，有的为空字符串。
        Mixed: some with uncertainties, some without, some with empty string.
        """
        summary = [
            {
                "method": "GET",
                "api_path": "/api/a",
                "uncertainties": "需要确认 auth 方式",
            },
            {
                "method": "POST",
                "api_path": "/api/b",
                # 无 uncertainties 字段
            },
            {
                "method": "PUT",
                "api_path": "/api/c",
                "uncertainties": ["问题一", "问题二"],
            },
            {
                "method": "DELETE",
                "api_path": "/api/d",
                "uncertainties": "",
            },
        ]

        with caplog.at_level(logging.INFO):
            _print_uncertainties(summary)

        # /api/a: header + 1 item = 2 records
        # /api/b: skipped
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
