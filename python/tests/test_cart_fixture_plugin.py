"""Tests for processors.builtin.db.cart_fixture — CartFixturePlugin.
验证 cart-fixture 的 add / clear / ensure 模式（mock DB）。"""

from unittest.mock import MagicMock, patch

import pytest

from processors.base import ProcessorError
from processors.builtin.db.cart_fixture import CartFixturePlugin
from processors.db import BaseDBPlugin, DBQueryError


@pytest.fixture
def global_config():
    """包含 db_url 与静态测试账号的全局配置。"""
    return {
        "processor_configs": {
            "cart-fixture": {
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
        "processors.builtin.db.cart_fixture.LoginManager.get_current_user",
        return_value=None,
    ):
        yield


def _mock_conn(fetch_rows=None, scalar_value=None, rowcount=0):
    """构造可配置返回结果的连接 Mock。"""
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_result = MagicMock()
    if fetch_rows is not None:
        mock_result.fetchall.return_value = fetch_rows
    if scalar_value is not None:
        mock_result.scalar.return_value = scalar_value
    mock_result.rowcount = rowcount
    mock_conn.execute.return_value = mock_result
    return mock_conn


class TestCartFixture:
    """验证三种模式与错误路径。"""

    def test_add_existing_updates_quantity(self, global_config, _mock_sqlalchemy):
        """同商品已存在时累加数量（遵循 foli-mall 语义）。"""
        mock_conn = _mock_conn(fetch_rows=[(11, 2)])
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = CartFixturePlugin()
            h, b = plugin.before_request(
                {}, {}, {"mode": "add", "quantity": 3, "selected": 1}, global_config
            )
        update_params = mock_conn.execute.call_args_list[1][0][1]
        assert update_params["qty"] == 5  # 2 + 3
        assert update_params["id"] == 11
        assert b == {}

    def test_add_new_inserts(self, global_config, _mock_sqlalchemy):
        """商品不在购物车时插入新购物车项。"""
        mock_conn = _mock_conn(fetch_rows=[])
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = CartFixturePlugin()
            h, b = plugin.before_request(
                {}, {}, {"mode": "add", "inject_cart_item_id": True}, global_config
            )
        insert_params = mock_conn.execute.call_args_list[1][0][1]
        assert insert_params["qty"] == 1
        assert insert_params["sel"] == 1
        assert "cartItemId" in b

    def test_clear_deletes(self, global_config, _mock_sqlalchemy):
        """clear 模式删除指定用户的购物车。"""
        mock_conn = _mock_conn(rowcount=3)
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = CartFixturePlugin()
            plugin.before_request({}, {}, {"mode": "clear"}, global_config)
        delete_params = mock_conn.execute.call_args_list[0][0][1]
        assert delete_params["uid"] == 7

    def test_ensure_skips_when_selected_exists(self, global_config, _mock_sqlalchemy):
        """已存在选中项时不做插入。"""
        mock_conn = _mock_conn(scalar_value=1)
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = CartFixturePlugin()
            h, b = plugin.before_request(
                {}, {}, {"mode": "ensure", "inject_selected_count": True}, global_config
            )
        assert b["cartSelectedCount"] == 1
        assert mock_conn.execute.call_count == 1  # 只有 COUNT

    def test_ensure_inserts_when_empty(self, global_config, _mock_sqlalchemy):
        """无选中项时插入默认商品。"""
        mock_conn = _mock_conn(scalar_value=0)
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = CartFixturePlugin()
            h, b = plugin.before_request(
                {}, {}, {"mode": "ensure", "inject_selected_count": True}, global_config
            )
        assert b["cartSelectedCount"] == 1
        assert mock_conn.execute.call_count == 2  # COUNT + INSERT

    def test_invalid_mode_raises(self, global_config, _mock_sqlalchemy):
        """未知模式抛出 ProcessorError。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = CartFixturePlugin()
            with pytest.raises(ProcessorError):
                plugin.before_request({}, {}, {"mode": "reset"}, global_config)

    def test_db_error_wrapped(self, global_config, _mock_sqlalchemy):
        """数据库异常包装为 DBQueryError。"""
        mock_conn = _mock_conn()
        mock_conn.execute.side_effect = RuntimeError("boom")
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = CartFixturePlugin()
            with pytest.raises(DBQueryError):
                plugin.before_request({}, {}, {"mode": "clear"}, global_config)
