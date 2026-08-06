"""Tests for processors.builtin.db.user_fixture — UserFixturePlugin.
验证 user-fixture 的 predelete / create / set_status / delete 与清理逻辑
（mock DB，不触真实库、不调 LLM）。"""

from unittest.mock import MagicMock, patch

import pytest

from processors.base import ProcessorError
from processors.builtin.db.user_fixture import (
    DEFAULT_PASSWORD_HASH,
    UserFixturePlugin,
    _USERNAME_KEY,
)
from processors.db import BaseDBPlugin, DBQueryError


@pytest.fixture
def global_config():
    """包含 db_url 的全局配置。"""
    return {
        "processor_configs": {
            "user-fixture": {
                "db_url": "h2://sa:@localhost:9092/mem:foli_mall",
            }
        }
    }


@pytest.fixture
def _mock_sqlalchemy():
    """Mock sqlalchemy.text，使模块内 from sqlalchemy import text 可用。"""
    mock_sa = MagicMock()
    mock_sa.text = MagicMock(return_value="MOCKED_SQL")
    with patch.dict("sys.modules", {"sqlalchemy": mock_sa}):
        yield mock_sa


def _mock_conn(fetch_rows=None, rowcount=1):
    """构造可配置返回结果的连接 Mock。"""
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_result = MagicMock()
    if fetch_rows is not None:
        mock_result.fetchall.return_value = fetch_rows
    mock_result.rowcount = rowcount
    mock_conn.execute.return_value = mock_result
    return mock_conn


class TestUserFixtureBefore:
    """验证 before_request 的四种模式。"""

    def test_predelete_deletes_by_username(self, global_config, _mock_sqlalchemy):
        """predelete 按 username 物理删除。"""
        mock_conn = _mock_conn(rowcount=1)
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = UserFixturePlugin()
            h, b = plugin.before_request(
                {}, {}, {"mode": "predelete", "username": "e2e_user"}, global_config
            )
        delete_params = mock_conn.execute.call_args_list[0][0][1]
        assert delete_params["name"] == "e2e_user"
        assert b == {}

    def test_create_inserts_with_default_hash(self, global_config, _mock_sqlalchemy):
        """create 幂等插入，密码使用内置 BCrypt 常量。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = UserFixturePlugin()
            h, b = plugin.before_request(
                {},
                {},
                {"mode": "create", "username": "e2e_user", "status": 0},
                global_config,
            )
        # 第一次为 DELETE（同名），第二次为 INSERT
        assert mock_conn.execute.call_args_list[0][0][1]["name"] == "e2e_user"
        insert_params = mock_conn.execute.call_args_list[1][0][1]
        assert insert_params["username"] == "e2e_user"
        assert insert_params["password"] == DEFAULT_PASSWORD_HASH
        assert insert_params["status"] == 0
        assert insert_params["role"] == 0
        assert b == {}

    def test_create_with_cleanup_records_metadata(self, global_config, _mock_sqlalchemy):
        """create + cleanup 时在请求体记录用户标识。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = UserFixturePlugin()
            h, b = plugin.before_request(
                {},
                {},
                {
                    "mode": "create",
                    "username": "e2e_user",
                    "user_id": 9000000000000000101,
                    "cleanup": True,
                },
                global_config,
            )
        assert b[_USERNAME_KEY] == "e2e_user"

    def test_set_status_updates(self, global_config, _mock_sqlalchemy):
        """set_status 读取旧状态后更新为配置状态。"""
        mock_conn = _mock_conn(fetch_rows=[(1,)])
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = UserFixturePlugin()
            h, b = plugin.before_request(
                {},
                {},
                {"mode": "set_status", "username": "e2e_user", "status": 0},
                global_config,
            )
        update_params = mock_conn.execute.call_args_list[1][0][1]
        assert update_params["status"] == 0
        assert update_params["name"] == "e2e_user"

    def test_set_status_missing_user_raises(self, global_config, _mock_sqlalchemy):
        """目标用户不存在时报 ProcessorError。"""
        mock_conn = _mock_conn(fetch_rows=[])
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = UserFixturePlugin()
            with pytest.raises(ProcessorError):
                plugin.before_request(
                    {},
                    {},
                    {"mode": "set_status", "username": "ghost", "status": 0},
                    global_config,
                )

    def test_delete_deletes(self, global_config, _mock_sqlalchemy):
        """delete 按 username 删除。"""
        mock_conn = _mock_conn(rowcount=1)
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = UserFixturePlugin()
            plugin.before_request(
                {}, {}, {"mode": "delete", "username": "e2e_user"}, global_config
            )
        delete_params = mock_conn.execute.call_args_list[0][0][1]
        assert delete_params["name"] == "e2e_user"

    def test_missing_identity_raises(self, global_config, _mock_sqlalchemy):
        """username 与 user_id 都缺失时报 ProcessorError。"""
        plugin = UserFixturePlugin()
        with pytest.raises(ProcessorError):
            plugin.before_request({}, {}, {"mode": "predelete"}, global_config)

    def test_invalid_mode_raises(self, global_config, _mock_sqlalchemy):
        """未知模式报 ProcessorError。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = UserFixturePlugin()
            with pytest.raises(ProcessorError):
                plugin.before_request(
                    {}, {}, {"mode": "boom", "username": "e2e_user"}, global_config
                )

    def test_wraps_db_error(self, global_config, _mock_sqlalchemy):
        """数据库异常应包装为 DBQueryError。"""
        mock_conn = _mock_conn()
        mock_conn.execute.side_effect = RuntimeError("boom")
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = UserFixturePlugin()
            with pytest.raises(DBQueryError):
                plugin.before_request(
                    {}, {}, {"mode": "delete", "username": "e2e_user"}, global_config
                )


class TestUserFixtureAfter:
    """验证 after_response 清理逻辑。"""

    def test_cleanup_deletes(self, global_config, _mock_sqlalchemy):
        """cleanup 按记录的 username 删除用户。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = UserFixturePlugin()
            plugin.after_response(
                {}, {_USERNAME_KEY: "e2e_user"}, {}, None, {"cleanup": True}, global_config
            )
        delete_params = mock_conn.execute.call_args_list[0][0][1]
        assert delete_params["name"] == "e2e_user"

    def test_cleanup_skip_without_flag(self, global_config, _mock_sqlalchemy):
        """cleanup=false 时不做任何删除。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = UserFixturePlugin()
            plugin.after_response(
                {}, {_USERNAME_KEY: "e2e_user"}, {}, None, {"cleanup": False}, global_config
            )
        mock_conn.execute.assert_not_called()
