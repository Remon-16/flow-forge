"""Tests for processors.db — BaseDBPlugin, _EngineManager, auto-registration."""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from processors.base import (
    PreProcessor,
    PostProcessor,
    ProcessorError,
    _PRE_PROCESSOR_REGISTRY,
    _POST_PROCESSOR_REGISTRY,
)
from processors.db import (
    BaseDBPlugin,
    DBConnectionError,
    DBQueryError,
    _DB_PLUGIN_REGISTRY,
    _EngineManager,
    _mask_password,
    _ensure_sqlalchemy,
)


# ---------------------------------------------------------------------------
# helpers: clean registries before each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_registries():
    """清理所有注册表，确保测试隔离。Clean all registries for test isolation."""
    _PRE_PROCESSOR_REGISTRY.clear()
    _POST_PROCESSOR_REGISTRY.clear()
    _DB_PLUGIN_REGISTRY.clear()
    yield
    _PRE_PROCESSOR_REGISTRY.clear()
    _POST_PROCESSOR_REGISTRY.clear()
    _DB_PLUGIN_REGISTRY.clear()


# ============================================================================
# TestPasswordMasking — 密码掩码
# ============================================================================

class TestPasswordMasking:
    """验证 db_url 密码掩码功能。Verify password masking in db_url."""

    def test_masks_mysql_url(self):
        url = "mysql+pymysql://root:secret123@localhost:3306/testdb"
        masked = _mask_password(url)
        assert "secret123" not in masked
        assert "***" in masked
        assert "root" in masked
        assert "localhost" in masked

    def test_masks_postgresql_url(self):
        url = "postgresql+psycopg2://user:pass@host:5432/db"
        masked = _mask_password(url)
        assert "pass" not in masked
        assert "***" in masked

    def test_no_password_unchanged(self):
        url = "sqlite:///test.db"
        masked = _mask_password(url)
        assert masked == url

    def test_no_at_symbol_unchanged(self):
        url = "mysql+pymysql://localhost:3306/testdb"
        masked = _mask_password(url)
        assert masked == url


# ============================================================================
# TestBaseDBPluginRegistration — 注册机制
# ============================================================================

class TestBaseDBPluginRegistration:
    """验证 BaseDBPlugin 子类的自动注册。Verify auto-registration of BaseDBPlugin subclasses."""

    def test_registers_in_db_plugin_registry(self):
        """__init_subclass__ 自动注册到 _DB_PLUGIN_REGISTRY。"""
        class MyPlugin(BaseDBPlugin):
            name = "my-db-plugin"

        assert "my-db-plugin" in _DB_PLUGIN_REGISTRY
        assert _DB_PLUGIN_REGISTRY["my-db-plugin"] is MyPlugin

    def test_raises_type_error_when_name_missing(self):
        """未定义 name 时抛出 TypeError。"""
        with pytest.raises(TypeError, match="must define a 'name' class attribute"):
            class BadPlugin(BaseDBPlugin):  # noqa: F841
                pass

    def test_auto_creates_pre_processor_wrapper(self):
        """自动创建 PreProcessor 包装类并注册。"""
        class MyPlugin(BaseDBPlugin):
            name = "auto-pre-test"

        assert "auto-pre-test" in _PRE_PROCESSOR_REGISTRY
        wrapper_cls = _PRE_PROCESSOR_REGISTRY["auto-pre-test"]
        assert issubclass(wrapper_cls, PreProcessor)

    def test_auto_creates_post_processor_wrapper(self):
        """自动创建 PostProcessor 包装类并注册。"""
        class MyPlugin(BaseDBPlugin):
            name = "auto-post-test"

        assert "auto-post-test" in _POST_PROCESSOR_REGISTRY
        wrapper_cls = _POST_PROCESSOR_REGISTRY["auto-post-test"]
        assert issubclass(wrapper_cls, PostProcessor)

    def test_multiple_plugins_independent(self):
        """多个插件独立注册，互不干扰。"""
        class PluginA(BaseDBPlugin):
            name = "plugin-a"

        class PluginB(BaseDBPlugin):
            name = "plugin-b"

        assert "plugin-a" in _PRE_PROCESSOR_REGISTRY
        assert "plugin-b" in _PRE_PROCESSOR_REGISTRY
        assert _DB_PLUGIN_REGISTRY["plugin-a"] is PluginA
        assert _DB_PLUGIN_REGISTRY["plugin-b"] is PluginB


# ============================================================================
# TestWrapperDelegation — 包装器委托
# ============================================================================

class TestWrapperDelegation:
    """验证 PreProcessor/PostProcessor 包装器正确委托到 BaseDBPlugin。"""

    def test_pre_wrapper_delegates_to_before_request(self):
        """PreProcessor 包装器委托到 before_request()。"""
        call_args = {}

        class MyPlugin(BaseDBPlugin):
            name = "delegate-pre"

            def before_request(self, headers, body, case_config, global_config):
                call_args["headers"] = headers
                call_args["body"] = body
                body["injected"] = "from_db"
                return headers, body

        pre_cls = _PRE_PROCESSOR_REGISTRY["delegate-pre"]
        instance = pre_cls()
        h, b = instance.process(
            {"Content-Type": "json"}, {"key": "val"}, {}, {"processor_configs": {}}
        )

        assert b["injected"] == "from_db"
        assert call_args["headers"] == {"Content-Type": "json"}

    def test_post_wrapper_delegates_to_after_response(self):
        """PostProcessor 包装器委托到 after_response()。"""
        call_args = {}

        class MyPlugin(BaseDBPlugin):
            name = "delegate-post"

            def after_response(self, req_h, req_b, resp_h, resp_b, cc, gc):
                call_args["resp_body"] = resp_b
                call_args["req_body"] = req_b

        post_cls = _POST_PROCESSOR_REGISTRY["delegate-post"]
        instance = post_cls()
        instance.process(
            {"h": "1"}, {"b": "2"}, {"rh": "3"}, {"result": "ok"}, {}, {"processor_configs": {}}
        )

        assert call_args["resp_body"] == {"result": "ok"}
        assert call_args["req_body"] == {"b": "2"}

    def test_can_process_delegates(self):
        """PreProcessor can_process 委托到 BaseDBPlugin.can_process()。"""
        class SkippingPlugin(BaseDBPlugin):
            name = "skip-test"

            def can_process(self, case):
                return case.get("skip_me", False) is False

        pre_cls = _PRE_PROCESSOR_REGISTRY["skip-test"]
        instance = pre_cls()
        assert instance.can_process({}) is True
        assert instance.can_process({"skip_me": False}) is True
        assert instance.can_process({"skip_me": True}) is False


# ============================================================================
# TestBaseDBPluginDefaults — 默认行为
# ============================================================================

class TestBaseDBPluginDefaults:
    """验证 before_request / after_response 默认 no-op 行为。"""

    def test_before_request_default_is_noop(self):
        """before_request 默认直接返回 headers, body 不修改。"""
        class Plugin(BaseDBPlugin):
            name = "noop-pre"

        pre_cls = _PRE_PROCESSOR_REGISTRY["noop-pre"]
        instance = pre_cls()
        h, b = instance.process(
            {"h": "val"}, {"b": "val"}, {}, {"processor_configs": {}}
        )
        assert h == {"h": "val"}
        assert b == {"b": "val"}

    def test_after_response_default_is_noop(self):
        """after_response 默认不抛异常。"""
        class Plugin(BaseDBPlugin):
            name = "noop-post"

        post_cls = _POST_PROCESSOR_REGISTRY["noop-post"]
        instance = post_cls()
        # Should not raise
        instance.process({}, {}, {}, None, {}, {"processor_configs": {}})


# ============================================================================
# TestEngineManager — 连接池管理
# ============================================================================

class TestEngineManager:
    """验证 _EngineManager 的懒加载、缓存、线程安全。"""

    def test_requires_sqlalchemy_installed(self):
        """SQLAlchemy 未安装时抛出友好错误。"""
        # 直接让 _ensure_sqlalchemy 抛出 ProcessorError
        # Make _ensure_sqlalchemy raise ProcessorError directly
        with patch("processors.db._ensure_sqlalchemy", side_effect=ProcessorError(
            "SQLAlchemy is required", processor_name="db"
        )):
            with pytest.raises(ProcessorError, match="SQLAlchemy is required"):
                _EngineManager.get_engine("mysql+pymysql://localhost/db")

    def test_caches_engine_by_url(self):
        """相同 db_url 返回同一个 Engine。"""
        _EngineManager._engines.clear()
        # side_effect 为每个 URL 创建独立 MagicMock / side_effect creates unique mock per URL
        with patch("processors.db._ensure_sqlalchemy"), \
             patch("processors.db._create_engine", side_effect=lambda *a, **kw: MagicMock()) as mock_create:
            e1 = _EngineManager.get_engine("mysql+pymysql://u:p@h/db1")
            e2 = _EngineManager.get_engine("mysql+pymysql://u:p@h/db1")
            e3 = _EngineManager.get_engine("mysql+pymysql://u:p@h/db2")

            assert e1 is e2  # 同 URL 复用 / Same URL reused
            assert e1 is not e3  # 不同 URL 新建 / Different URL creates new
            assert mock_create.call_count == 2

    def test_lazy_init(self):
        """不调用 get_engine 时不创建 Engine。"""
        with patch("processors.db._ensure_sqlalchemy"), \
             patch("processors.db._create_engine") as mock_create:
            _EngineManager._engines.clear()
            # Don't call get_engine — mock_create should not be called
            mock_create.assert_not_called()

    def test_thread_safety(self):
        """多线程并发调用 get_engine 无竞争。"""
        mock_engine = MagicMock()
        results = []
        errors = []

        def worker():
            try:
                e = _EngineManager.get_engine("mysql+pymysql://t:1@h/t")
                results.append(e)
            except Exception as exc:
                errors.append(exc)

        with patch("processors.db._ensure_sqlalchemy"), \
             patch("processors.db._create_engine", return_value=mock_engine):
            _EngineManager._engines.clear()
            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert len(errors) == 0
        # 所有线程应获得同一个 Engine
        # All threads should get the same Engine
        assert len(set(id(r) for r in results)) == 1


# ============================================================================
# TestDBConnectionConfig — 连接配置验证
# ============================================================================

class TestDBConnectionConfig:
    """验证 _get_connection 的配置读取和错误处理。"""

    def test_missing_processor_configs_raises(self):
        """processor_configs 缺失时抛出 DBConnectionError。"""
        class Plugin(BaseDBPlugin):
            name = "missing-config"

        plugin = Plugin()
        with pytest.raises(DBConnectionError, match="processor_configs"):
            plugin._get_connection({})

    def test_missing_processor_entry_raises(self):
        """processor_configs 中没有对应处理器时抛出 DBConnectionError。"""
        class Plugin(BaseDBPlugin):
            name = "no-entry"

        plugin = Plugin()
        with pytest.raises(DBConnectionError, match="no-entry"):
            plugin._get_connection({"processor_configs": {}})

    def test_empty_db_url_raises(self):
        """db_url 未设置时抛出 DBConnectionError。"""
        class Plugin(BaseDBPlugin):
            name = "no-url"

        plugin = Plugin()
        with pytest.raises(DBConnectionError, match="db_url"):
            plugin._get_connection({"processor_configs": {"no-url": {}}})

    def test_connects_with_valid_url(self):
        """有效 db_url 调用 _EngineManager.get_engine 并返回连接。"""
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value = mock_conn

        class Plugin(BaseDBPlugin):
            name = "valid-url"

        with patch("processors.db._SA_AVAILABLE", True), \
             patch("processors.db._EngineManager.get_engine", return_value=mock_engine):
            plugin = Plugin()
            conn = plugin._get_connection({
                "processor_configs": {
                    "valid-url": {"db_url": "mysql+pymysql://u:p@h/db"}
                }
            })
            mock_engine.connect.assert_called_once()
            assert conn is mock_conn


# ============================================================================
# TestErrorWrapping — 异常包装
# ============================================================================

class TestErrorWrapping:
    """验证 DBQueryError 正确包装为 ProcessorError。"""

    def test_db_query_error_is_processor_error(self):
        """DBQueryError 是 ProcessorError 的子类。"""
        err = DBQueryError("test error", processor_name="test-db")
        assert isinstance(err, ProcessorError)
        assert err.processor_name == "test-db"

    def test_db_connection_error_is_processor_error(self):
        """DBConnectionError 是 ProcessorError 的子类。"""
        err = DBConnectionError("conn failed", processor_name="test-db")
        assert isinstance(err, ProcessorError)
        assert err.processor_name == "test-db"


# ============================================================================
# TestReturnOrderDBPlugin — 示例插件集成测试
# ============================================================================

class TestReturnOrderDBPlugin:
    """验证 ReturnOrderDBPlugin 的前置/后置处理逻辑（mock DB）。"""

    @pytest.fixture
    def global_config(self):
        return {
            "processor_configs": {
                "return-order-db": {
                    "db_url": "mysql+pymysql://test:test@localhost/foli_mall",
                    "test_buyer_id": 1,
                    "test_store_id": 1,
                    "test_product_id": 100,
                }
            }
        }

    @pytest.fixture
    def _mock_sqlalchemy(self):
        """Mock sqlalchemy.text 使 from sqlalchemy import text 可用。"""
        mock_sa = MagicMock()
        mock_sa.text = MagicMock(return_value="MOCKED_SQL")
        with patch.dict("sys.modules", {"sqlalchemy": mock_sa}):
            yield mock_sa

    def test_before_request_inserts_order_and_injects_id(self, global_config, _mock_sqlalchemy):
        """before_request 模拟 INSERT 后注入 order_id 到 body。"""
        mock_conn = MagicMock()
        # MagicMock.__enter__() 默认返回新 Mock，需要让它返回自己
        # MagicMock.__enter__() returns new mock by default, make it return self
        mock_conn.__enter__.return_value = mock_conn
        # Mock: conn.execute(...).fetchall() returns product query result
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("Test Product", "img.png", 99.99)
        ]
        mock_conn.execute.return_value = mock_result

        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            from processors.builtin.db.return_order import ReturnOrderDBPlugin
            plugin = ReturnOrderDBPlugin()
            headers = {"Content-Type": "application/json"}
            body = {"reason": "defective item"}

            h, b = plugin.before_request(headers, body, {}, global_config)

        # 验证 order_id 已注入 / Verify order_id injected
        assert "order_id" in b
        assert isinstance(b["order_id"], int)
        assert b["reason"] == "defective item"
        assert h == headers
        # 验证 execute 被调用 / Verify execute was called
        assert mock_conn.execute.call_count >= 2  # SELECT product + INSERT order + INSERT item
        # 验证事务上下文被使用 / Verify transaction context was used
        mock_conn.begin.assert_called_once()

    def test_after_response_prints_return_record(self, global_config, _mock_sqlalchemy):
        """after_response 查询退货记录并 print（不抛异常）。"""
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (1, "RF2024001", 999, 1, 1, "defective", 1, 99.99, 0, "2024-01-01")
        ]
        mock_conn.execute.return_value = mock_result

        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            from processors.builtin.db.return_order import ReturnOrderDBPlugin
            plugin = ReturnOrderDBPlugin()
            # 不应抛异常 / Should not raise
            plugin.after_response(
                {}, {"order_id": 999}, {}, {"code": "100000", "msg": "success"}, {}, global_config
            )

        mock_conn.execute.assert_called_once()

    def test_after_response_no_order_id_skips(self, global_config, _mock_sqlalchemy):
        """after_response 无 order_id 时跳过。"""
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn

        with patch.object(BaseDBPlugin, "_get_connection", return_value=mock_conn):
            from processors.builtin.db.return_order import ReturnOrderDBPlugin
            plugin = ReturnOrderDBPlugin()
            plugin.after_response({}, {}, {}, {}, {}, global_config)

        mock_conn.execute.assert_not_called()
