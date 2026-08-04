"""Tests for processors.builtin.db.order_fixture — OrderFixturePlugin.
验证 order-fixture 前置造单、注入与后置清理逻辑（mock DB，不触真实库）。"""

from unittest.mock import MagicMock, patch

import pytest

from processors.base import ProcessorError
from processors.builtin.db.order_fixture import OrderFixturePlugin, _ORDER_ID_KEY
from processors.db import BaseDBPlugin, DBQueryError


@pytest.fixture
def global_config():
    """包含 db_url 与静态测试账号的全局配置。"""
    return {
        "processor_configs": {
            "order-fixture": {
                "db_url": "h2://sa:@localhost:9092/mem:foli_mall",
                "test_buyer_id": 7,
                "test_store_id": 1,
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


@pytest.fixture(autouse=True)
def _no_current_user():
    """默认无登录用户，走静态配置。"""
    with patch(
        "processors.builtin.db.order_fixture.LoginManager.get_current_user",
        return_value=None,
    ):
        yield


def _mock_conn(product_exists=True):
    """构造返回商品快照的连接 Mock。"""
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_result = MagicMock()
    mock_result.fetchall.return_value = (
        [("Test Product", "img.png", 99.99)] if product_exists else []
    )
    mock_result.scalar.return_value = 0
    mock_conn.execute.return_value = mock_result
    return mock_conn


class TestOrderFixtureBefore:
    """验证 before_request 造单与注入。"""

    def test_injects_order_id_and_default_status_4(self, global_config, _mock_sqlalchemy):
        """默认状态应为 4（COMPLETED），并把 orderId 注入请求体。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = OrderFixturePlugin()
            headers = {"Content-Type": "application/json"}
            body = {"reason": "defective"}
            h, b = plugin.before_request(headers, body, {}, global_config)

        assert "orderId" in b
        assert isinstance(b["orderId"], int)
        assert h == headers
        # call 0 = SELECT product, call 1 = INSERT fm_order
        insert_params = mock_conn.execute.call_args_list[1][0][1]
        assert insert_params["status"] == 4
        # 默认不注入内部元数据键 / No internal metadata by default
        assert _ORDER_ID_KEY not in b

    def test_honors_custom_status_and_cleanup(self, global_config, _mock_sqlalchemy):
        """case 配置可覆盖状态并开启清理元数据。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = OrderFixturePlugin()
            h, b = plugin.before_request(
                {}, {}, {"order_status": 2, "cleanup": True}, global_config
            )

        insert_params = mock_conn.execute.call_args_list[1][0][1]
        assert insert_params["status"] == 2
        assert b[_ORDER_ID_KEY] == b["orderId"]

    def test_fixed_order_id_predeletes_and_uses_literal(self, global_config, _mock_sqlalchemy):
        """固定 order_id 时先删除旧记录再插入，body 注入同一 ID。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = OrderFixturePlugin()
            h, b = plugin.before_request(
                {}, {}, {"order_id": 9000000000000000001}, global_config
            )
        # 前两次调用为 DELETE（明细 + 订单），且使用固定 ID
        assert mock_conn.execute.call_args_list[0][0][1]["oid"] == 9000000000000000001
        assert mock_conn.execute.call_args_list[1][0][1]["oid"] == 9000000000000000001
        insert_params = mock_conn.execute.call_args_list[3][0][1]
        assert insert_params["id"] == 9000000000000000001
        assert b["orderId"] == 9000000000000000001

    def test_wraps_db_error(self, global_config, _mock_sqlalchemy):
        """数据库异常应包装为 DBQueryError。"""
        mock_conn = _mock_conn()
        mock_conn.execute.side_effect = RuntimeError("boom")
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = OrderFixturePlugin()
            with pytest.raises(DBQueryError):
                plugin.before_request({}, {}, {}, global_config)


class TestOrderFixtureAfter:
    """验证 after_response 清理逻辑。"""

    def test_skips_without_cleanup(self, global_config, _mock_sqlalchemy):
        """cleanup 未开启时不执行任何 SQL。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = OrderFixturePlugin()
            plugin.after_response({}, {"orderId": 1}, {}, {}, {}, global_config)
        mock_conn.execute.assert_not_called()

    def test_skips_without_metadata_key(self, global_config, _mock_sqlalchemy):
        """开启清理但缺少内部元数据键时跳过。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = OrderFixturePlugin()
            plugin.after_response(
                {}, {"orderId": 1}, {}, {}, {"cleanup": True}, global_config
            )
        mock_conn.execute.assert_not_called()

    def test_cleanup_deletes_order(self, global_config, _mock_sqlalchemy):
        """开启清理时删除订单并校验无残留。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = OrderFixturePlugin()
            plugin.after_response(
                {},
                {_ORDER_ID_KEY: 42, "orderId": 42},
                {},
                {},
                {"cleanup": True},
                global_config,
            )
        # DELETE fm_order_item + DELETE fm_order + SELECT COUNT
        assert mock_conn.execute.call_count >= 3

    def test_cleanup_residual_raises(self, global_config, _mock_sqlalchemy):
        """残留行存在时抛出 ProcessorError。"""
        mock_conn = _mock_conn()
        mock_conn.execute.return_value.scalar.return_value = 1
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = OrderFixturePlugin()
            with pytest.raises(ProcessorError):
                plugin.after_response(
                    {},
                    {_ORDER_ID_KEY: 42},
                    {},
                    {},
                    {"cleanup": True},
                    global_config,
                )
