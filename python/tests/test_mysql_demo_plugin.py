"""Tests for the built-in MySQL demo processor (processors/builtin/db/mysql_demo.py)."""

from unittest.mock import MagicMock, patch

import pytest

from i18n import get_lang, set_lang
from processors.base import ProcessorError
from processors.db import DBQueryError


@pytest.fixture(autouse=True)
def _use_zh_cn():
    """用例断言依赖中文文案，临时切换到 zh_CN 并在结束后恢复。
    Assertions rely on Chinese messages; switch to zh_CN and restore afterward."""
    old_lang = get_lang()
    set_lang("zh_CN")
    yield
    set_lang(old_lang)


class TestMysqlDemoPlugin:
    """验证 mysql-demo 前置写入与后置读取/清理逻辑。
    Verify the mysql-demo pre-write and post-read/cleanup logic."""

    @staticmethod
    def _make_conn(execute_results):
        conn = MagicMock()
        # SQLAlchemy Connection 的 __enter__ 返回自身；mock 需要显式配置
        # Real SQLAlchemy Connection.__enter__ returns itself; configure the mock explicitly
        conn.__enter__.return_value = conn
        conn.execute.side_effect = execute_results
        return conn

    def should_inject_key_and_insert_row_on_before_request(self):
        from processors.builtin.db.mysql_demo import MysqlDemoPlugin

        plugin = MysqlDemoPlugin()
        conn = MagicMock()
        conn.__enter__.return_value = conn
        with patch.object(plugin, "_get_connection", return_value=conn):
            headers, body = plugin.before_request(
                {"Content-Type": "application/json"},
                {"username": "admin"},
                {},
                {"processor_configs": {"mysql-demo": {"db_url": "mysql://x"}}},
            )

        assert headers == {"Content-Type": "application/json"}
        assert "mysql_demo_key" in body
        assert isinstance(body["mysql_demo_key"], int)
        # CREATE TABLE 与 INSERT 各执行一次 / one CREATE TABLE plus one INSERT
        assert conn.execute.call_count == 2
        insert_sql = str(conn.execute.call_args_list[1][0][0])
        assert "INSERT INTO ff_plugin_demo" in insert_sql
        assert conn.begin.called

    def should_raise_db_query_error_when_write_fails(self):
        from processors.builtin.db.mysql_demo import MysqlDemoPlugin

        plugin = MysqlDemoPlugin()
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.execute.side_effect = RuntimeError("boom")
        with patch.object(plugin, "_get_connection", return_value=conn):
            with pytest.raises(DBQueryError, match="写入失败"):
                plugin.before_request(
                    {}, {}, {},
                    {"processor_configs": {"mysql-demo": {"db_url": "mysql://x"}}},
                )

    def should_read_print_and_delete_on_after_response(self, capsys):
        from processors.builtin.db.mysql_demo import MysqlDemoPlugin

        plugin = MysqlDemoPlugin()
        select_result = MagicMock()
        select_result.fetchall.return_value = [("payload-x",)]
        delete_result = MagicMock()
        delete_result.rowcount = 1
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        conn = self._make_conn([select_result, delete_result, count_result])

        with patch.object(plugin, "_get_connection", return_value=conn):
            plugin.after_response(
                {}, {"mysql_demo_key": 123}, {}, {},
                {}, {"processor_configs": {"mysql-demo": {"db_url": "mysql://x"}}},
            )

        calls = [str(c[0][0]) for c in conn.execute.call_args_list]
        assert any("SELECT payload" in s for s in calls)
        assert any("DELETE FROM ff_plugin_demo" in s for s in calls)
        assert any("SELECT COUNT(*)" in s for s in calls)
        out = capsys.readouterr().out
        assert "123" in out

    def should_raise_when_row_not_readable(self):
        from processors.builtin.db.mysql_demo import MysqlDemoPlugin

        plugin = MysqlDemoPlugin()
        select_result = MagicMock()
        select_result.fetchall.return_value = []
        conn = self._make_conn([select_result])

        with patch.object(plugin, "_get_connection", return_value=conn):
            with pytest.raises(ProcessorError, match="找不到"):
                plugin.after_response(
                    {}, {"mysql_demo_key": 123}, {}, {},
                    {}, {"processor_configs": {"mysql-demo": {"db_url": "mysql://x"}}},
                )

    def should_raise_when_delete_leaves_rows(self):
        from processors.builtin.db.mysql_demo import MysqlDemoPlugin

        plugin = MysqlDemoPlugin()
        select_result = MagicMock()
        select_result.fetchall.return_value = [("payload-x",)]
        delete_result = MagicMock()
        delete_result.rowcount = 1
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        conn = self._make_conn([select_result, delete_result, count_result])

        with patch.object(plugin, "_get_connection", return_value=conn):
            with pytest.raises(ProcessorError, match="删除失败"):
                plugin.after_response(
                    {}, {"mysql_demo_key": 123}, {}, {},
                    {}, {"processor_configs": {"mysql-demo": {"db_url": "mysql://x"}}},
                )

    def should_skip_cleanup_when_key_missing(self):
        from processors.builtin.db.mysql_demo import MysqlDemoPlugin

        plugin = MysqlDemoPlugin()
        with patch.object(plugin, "_get_connection") as mock_get:
            plugin.after_response(
                {}, {}, {}, {},
                {}, {"processor_configs": {"mysql-demo": {"db_url": "mysql://x"}}},
            )
        mock_get.assert_not_called()
