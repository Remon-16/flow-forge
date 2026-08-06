"""Tests for processors.builtin.db.return_fixture — ReturnFixturePlugin.
验证 return-fixture 造退货记录、注入 returnId 与后置清理（mock DB）。"""

from unittest.mock import MagicMock, patch

import pytest

from processors.base import ProcessorError
from processors.builtin.db.return_fixture import (
    ReturnFixturePlugin,
    _ORDER_ID_KEY,
    _RETURN_ID_KEY,
)
from processors.db import BaseDBPlugin, DBQueryError


@pytest.fixture
def global_config():
    """包含 db_url 与静态测试账号的全局配置。"""
    return {
        "processor_configs": {
            "return-fixture": {
                "db_url": "h2://sa:@localhost:9092/mem:foli_mall",
                "test_buyer_id": 7,
                "test_store_id": 1,
                "test_product_id": 100,
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
        "processors.builtin.db.return_fixture.LoginManager.get_current_user",
        return_value=None,
    ):
        yield


def _mock_conn():
    """构造返回商品快照与无残留结果的连接 Mock。"""
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [("Test Product", "img.png", 99.99)]
    mock_result.scalar.return_value = 0
    mock_conn.execute.return_value = mock_result
    return mock_conn


class TestReturnFixtureBefore:
    """验证 before_request 造退货与注入。"""

    def test_creates_completed_order_and_return(self, global_config, _mock_sqlalchemy):
        """默认创建 COMPLETED 订单 + 指定状态退货，注入 returnId。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = ReturnFixturePlugin()
            h, b = plugin.before_request(
                {}, {}, {"return_status": 2}, global_config
            )

        assert "returnId" in b
        assert isinstance(b["returnId"], int)
        # call 0=SELECT product, 1=INSERT fm_order, 2=INSERT fm_order_item, 3=INSERT fm_return_refund
        order_params = mock_conn.execute.call_args_list[1][0][1]
        assert order_params["status"] == 4
        return_params = mock_conn.execute.call_args_list[3][0][1]
        assert return_params["status"] == 2
        assert return_params["return_type"] == 1

    def test_uses_existing_order_when_create_order_false(self, global_config, _mock_sqlalchemy):
        """create_order=false 时使用指定订单，不新建。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = ReturnFixturePlugin()
            h, b = plugin.before_request(
                {},
                {},
                {"create_order": False, "order_id": 12345, "refund_amount": 88.5},
                global_config,
            )
        # 只有一次 INSERT（退货记录）
        assert mock_conn.execute.call_count == 1
        return_params = mock_conn.execute.call_args_list[0][0][1]
        assert return_params["order_id"] == 12345
        assert float(return_params["refund_amount"]) == 88.5

    def test_create_order_false_without_order_id_raises(self, global_config, _mock_sqlalchemy):
        """create_order=false 但缺少 order_id 时抛出 ProcessorError。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = ReturnFixturePlugin()
            with pytest.raises(ProcessorError):
                plugin.before_request(
                    {}, {}, {"create_order": False}, global_config
                )

    def test_cleanup_injects_metadata(self, global_config, _mock_sqlalchemy):
        """cleanup=true 时注入内部元数据键供后置删除。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = ReturnFixturePlugin()
            h, b = plugin.before_request(
                {}, {}, {"cleanup": True}, global_config
            )
        assert b[_RETURN_ID_KEY] == b["returnId"]
        assert _ORDER_ID_KEY in b

    def test_fixed_ids_predelete_and_inject(self, global_config, _mock_sqlalchemy):
        """固定 return_id / order_id 时先删除旧记录，body 注入字面 ID。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = ReturnFixturePlugin()
            h, b = plugin.before_request(
                {},
                {},
                {"return_id": 9000000000000000009, "order_id": 9000000000000000001},
                global_config,
            )
        # 前三次调用为 DELETE：退货、订单明细、订单
        assert mock_conn.execute.call_args_list[0][0][1]["rid"] == 9000000000000000009
        assert mock_conn.execute.call_args_list[1][0][1]["oid"] == 9000000000000000001
        assert mock_conn.execute.call_args_list[2][0][1]["oid"] == 9000000000000000001
        # 最后一次调用为 INSERT 退货记录
        return_params = mock_conn.execute.call_args_list[-1][0][1]
        assert return_params["id"] == 9000000000000000009
        assert b["returnId"] == 9000000000000000009


class TestReturnFixtureAfter:
    """验证 after_response 清理逻辑。"""

    def test_skips_without_cleanup(self, global_config, _mock_sqlalchemy):
        """cleanup 未开启时不执行 SQL。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = ReturnFixturePlugin()
            plugin.after_response({}, {"returnId": 1}, {}, {}, {}, global_config)
        mock_conn.execute.assert_not_called()

    def test_cleanup_deletes_return_and_order(self, global_config, _mock_sqlalchemy):
        """开启清理时删除退货与订单。"""
        mock_conn = _mock_conn()
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = ReturnFixturePlugin()
            plugin.after_response(
                {},
                {_RETURN_ID_KEY: 11, _ORDER_ID_KEY: 22},
                {},
                {},
                {"cleanup": True},
                global_config,
            )
        assert mock_conn.execute.call_count >= 3

    def test_db_error_wrapped(self, global_config, _mock_sqlalchemy):
        """清理异常包装为 DBQueryError。"""
        mock_conn = _mock_conn()
        mock_conn.execute.side_effect = RuntimeError("boom")
        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            plugin = ReturnFixturePlugin()
            with pytest.raises(DBQueryError):
                plugin.after_response(
                    {},
                    {_RETURN_ID_KEY: 11},
                    {},
                    {},
                    {"cleanup": True},
                    global_config,
                )
