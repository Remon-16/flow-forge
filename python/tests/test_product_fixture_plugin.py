"""Tests for processors.builtin.db.product_fixture — ProductFixturePlugin.
验证 product-fixture 的 set_stock / set_status / set_deleted 与恢复逻辑
（mock DB，不触真实库、不调 LLM）。"""

from unittest.mock import MagicMock, patch

import pytest

from processors.base import ProcessorError
from processors.builtin.db.product_fixture import (
    ProductFixturePlugin,
    _ORIGINAL_KEY,
    _PRODUCT_ID_KEY,
)
from processors.db import BaseDBPlugin, DBQueryError


@pytest.fixture
def global_config():
    """包含 db_url 的全局配置。"""
    return {
        "processor_configs": {
            "product-fixture": {
                "db_url": "h2://sa:@localhost:9092/mem:foli_mall",
                "test_product_id": 100,
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


def _mock_conn(fetch_rows=None):
    """构造可配置返回结果的连接 Mock。"""
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_result = MagicMock()
    if fetch_rows is not None:
        mock_result.fetchall.return_value = fetch_rows
    mock_conn.execute.return_value = mock_result
    return mock_conn


class TestProductFixtureBefore:
    """验证 before_request 的三种模式。"""

    def test_set_stock_updates(self, global_config, _mock_sqlalchemy):
        """set_stock 更新库存。"""
        mock_conn = _mock_conn(fetch_rows=[(50, 2, 0)])
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = ProductFixturePlugin()
            h, b = plugin.before_request(
                {}, {}, {"mode": "set_stock", "stock": 0}, global_config
            )
        update_params = mock_conn.execute.call_args_list[1][0][1]
        assert update_params["stock"] == 0
        assert update_params["pid"] == 100

    def test_set_status_updates(self, global_config, _mock_sqlalchemy):
        """set_status 更新商品状态（默认下架 4）。"""
        mock_conn = _mock_conn(fetch_rows=[(50, 2, 0)])
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = ProductFixturePlugin()
            h, b = plugin.before_request(
                {}, {}, {"mode": "set_status"}, global_config
            )
        update_params = mock_conn.execute.call_args_list[1][0][1]
        assert update_params["status"] == 4

    def test_set_deleted_updates(self, global_config, _mock_sqlalchemy):
        """set_deleted 逻辑删除商品（is_delete=1）。"""
        mock_conn = _mock_conn(fetch_rows=[(50, 2, 0)])
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = ProductFixturePlugin()
            h, b = plugin.before_request(
                {}, {}, {"mode": "set_deleted"}, global_config
            )
        update_params = mock_conn.execute.call_args_list[1][0][1]
        assert update_params["pid"] == 100

    def test_cleanup_records_original(self, global_config, _mock_sqlalchemy):
        """cleanup 时记录商品 ID 与原值供后置恢复。"""
        mock_conn = _mock_conn(fetch_rows=[(50, 2, 0)])
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = ProductFixturePlugin()
            h, b = plugin.before_request(
                {}, {}, {"mode": "set_stock", "stock": 0, "cleanup": True}, global_config
            )
        assert b[_PRODUCT_ID_KEY] == 100
        assert b[_ORIGINAL_KEY] == (50, 2, 0)

    def test_missing_product_raises(self, global_config, _mock_sqlalchemy):
        """商品不存在时报 ProcessorError。"""
        mock_conn = _mock_conn(fetch_rows=[])
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = ProductFixturePlugin()
            with pytest.raises(ProcessorError):
                plugin.before_request(
                    {}, {}, {"mode": "set_stock", "stock": 0}, global_config
                )

    def test_invalid_mode_raises(self, global_config, _mock_sqlalchemy):
        """未知模式报 ProcessorError。"""
        mock_conn = _mock_conn(fetch_rows=[(50, 2, 0)])
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = ProductFixturePlugin()
            with pytest.raises(ProcessorError):
                plugin.before_request(
                    {}, {}, {"mode": "boom"}, global_config
                )

    def test_wraps_db_error(self, global_config, _mock_sqlalchemy):
        """数据库异常应包装为 DBQueryError。"""
        mock_conn = _mock_conn()
        mock_conn.execute.side_effect = RuntimeError("boom")
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = ProductFixturePlugin()
            with pytest.raises(DBQueryError):
                plugin.before_request(
                    {}, {}, {"mode": "set_stock", "stock": 0}, global_config
                )


class TestProductFixtureAfter:
    """验证 after_response 恢复逻辑。"""

    def test_cleanup_restores_original(self, global_config, _mock_sqlalchemy):
        """cleanup 恢复原 stock / status / is_delete。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = ProductFixturePlugin()
            plugin.after_response(
                {},
                {_PRODUCT_ID_KEY: 100, _ORIGINAL_KEY: (50, 2, 0)},
                {},
                None,
                {"cleanup": True},
                global_config,
            )
        update_params = mock_conn.execute.call_args_list[0][0][1]
        assert update_params["stock"] == 50
        assert update_params["status"] == 2
        assert update_params["deleted"] == 0

    def test_cleanup_skip_without_flag(self, global_config, _mock_sqlalchemy):
        """cleanup=false 时不执行恢复。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = ProductFixturePlugin()
            plugin.after_response(
                {},
                {_PRODUCT_ID_KEY: 100, _ORIGINAL_KEY: (50, 2, 0)},
                {},
                None,
                {"cleanup": False},
                global_config,
            )
        mock_conn.execute.assert_not_called()
