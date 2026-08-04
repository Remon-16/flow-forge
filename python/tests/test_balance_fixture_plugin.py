"""Tests for processors.builtin.db.balance_fixture — BalanceFixturePlugin.
验证 balance-fixture 设置余额与错误路径（mock DB）。"""

from unittest.mock import MagicMock, patch

import pytest

from processors.base import ProcessorError
from processors.builtin.db.balance_fixture import BalanceFixturePlugin
from processors.db import BaseDBPlugin, DBQueryError


@pytest.fixture
def global_config():
    """包含 db_url 与静态测试账号的全局配置。"""
    return {
        "processor_configs": {
            "balance-fixture": {
                "db_url": "h2://sa:@localhost:9092/mem:foli_mall",
                "test_buyer_id": 7,
            }
        }
    }


@pytest.fixture
def _mock_sqlalchemy():
    """Mock sqlalchemy.text。"""
    mock_sa = MagicMock()
    mock_sa.text = MagicMock(return_value="MOCKED_SQL")
    with patch.dict("sys.modules", {"sqlalchemy": mock_sa}):
        yield mock_sa


@pytest.fixture(autouse=True)
def _no_current_user():
    """默认无登录用户，走静态配置。"""
    with patch(
        "processors.builtin.db.balance_fixture.LoginManager.get_current_user",
        return_value=None,
    ):
        yield


def _mock_conn(fetch_rows=None):
    """构造连接 Mock，可选指定 SELECT 结果。"""
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_result = MagicMock()
    if fetch_rows is not None:
        mock_result.fetchall.return_value = fetch_rows
    mock_conn.execute.return_value = mock_result
    return mock_conn


class TestBalanceFixture:
    """验证余额设置与错误路径。"""

    def test_sets_balance(self, global_config, _mock_sqlalchemy):
        """SELECT 原余额后 UPDATE 新余额。"""
        mock_conn = _mock_conn(fetch_rows=[(10000.0,)])
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = BalanceFixturePlugin()
            h, b = plugin.before_request(
                {}, {}, {"balance": 0.01}, global_config
            )
        update_params = mock_conn.execute.call_args_list[1][0][1]
        assert float(update_params["bal"]) == 0.01
        assert update_params["uid"] == 7
        assert b == {}

    def test_user_not_found_raises(self, global_config, _mock_sqlalchemy):
        """用户不存在时抛出 ProcessorError。"""
        mock_conn = _mock_conn(fetch_rows=[])
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = BalanceFixturePlugin()
            with pytest.raises(ProcessorError):
                plugin.before_request({}, {}, {"balance": 1.0}, global_config)

    def test_db_error_wrapped(self, global_config, _mock_sqlalchemy):
        """数据库异常包装为 DBQueryError。"""
        mock_conn = _mock_conn(fetch_rows=[(10000.0,)])
        mock_conn.execute.side_effect = RuntimeError("boom")
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = BalanceFixturePlugin()
            with pytest.raises(DBQueryError):
                plugin.before_request({}, {}, {"balance": 1.0}, global_config)
