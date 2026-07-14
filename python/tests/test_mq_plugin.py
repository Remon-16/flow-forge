"""Tests for processors.mq — BaseMQPlugin, _MQConnectionManager, auto-registration."""

import threading
from unittest.mock import MagicMock, patch

import pytest

from processors.base import (
    PreProcessor,
    PostProcessor,
    ProcessorError,
    _PRE_PROCESSOR_REGISTRY,
    _POST_PROCESSOR_REGISTRY,
)
from processors.mq import (
    BaseMQPlugin,
    MQConnectionError,
    MQPublishError,
    _MQ_PLUGIN_REGISTRY,
    _MQConnectionManager,
)


# ---------------------------------------------------------------------------
# helpers: clean registries before each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_registries():
    """清理所有注册表，确保测试隔离。Clean all registries for test isolation."""
    _PRE_PROCESSOR_REGISTRY.clear()
    _POST_PROCESSOR_REGISTRY.clear()
    _MQ_PLUGIN_REGISTRY.clear()
    _MQConnectionManager._connections.clear()
    yield
    _PRE_PROCESSOR_REGISTRY.clear()
    _POST_PROCESSOR_REGISTRY.clear()
    _MQ_PLUGIN_REGISTRY.clear()
    _MQConnectionManager._connections.clear()


# ============================================================================
# TestBaseMQPluginRegistration — 注册机制
# ============================================================================

class TestBaseMQPluginRegistration:
    """验证 BaseMQPlugin 子类的自动注册。"""

    def test_registers_in_mq_plugin_registry(self):
        class MyPlugin(BaseMQPlugin):
            name = "my-mq-plugin"

        assert "my-mq-plugin" in _MQ_PLUGIN_REGISTRY

    def test_auto_creates_pre_processor_wrapper(self):
        class MyPlugin(BaseMQPlugin):
            name = "mq-pre-test"

        assert "mq-pre-test" in _PRE_PROCESSOR_REGISTRY
        assert issubclass(_PRE_PROCESSOR_REGISTRY["mq-pre-test"], PreProcessor)

    def test_auto_creates_post_processor_wrapper(self):
        class MyPlugin(BaseMQPlugin):
            name = "mq-post-test"

        assert "mq-post-test" in _POST_PROCESSOR_REGISTRY
        assert issubclass(_POST_PROCESSOR_REGISTRY["mq-post-test"], PostProcessor)

    def test_raises_type_error_when_name_missing(self):
        with pytest.raises(TypeError, match="must define a 'name'"):
            class BadPlugin(BaseMQPlugin):  # noqa: F841
                pass


# ============================================================================
# TestWrapperDelegation — 包装器委托
# ============================================================================

class TestWrapperDelegation:
    """验证 Pre/PostProcessor 包装器正确委托到 BaseMQPlugin。"""

    def test_pre_wrapper_delegates_to_before_request(self):
        class MyPlugin(BaseMQPlugin):
            name = "mq-delegate-pre"

            def before_request(self, headers, body, case_config, global_config):
                body["mq_injected"] = True
                return headers, body

        pre_cls = _PRE_PROCESSOR_REGISTRY["mq-delegate-pre"]
        instance = pre_cls()
        h, b = instance.process({}, {"key": "val"}, {}, {"processor_configs": {}})
        assert b["mq_injected"] is True

    def test_post_wrapper_delegates_to_after_response(self):
        call_log = {}

        class MyPlugin(BaseMQPlugin):
            name = "mq-delegate-post"

            def after_response(self, rh, rb, rsh, rsb, cc, gc):
                call_log["resp"] = rsb

        post_cls = _POST_PROCESSOR_REGISTRY["mq-delegate-post"]
        instance = post_cls()
        instance.process({}, {}, {}, {"data": "ok"}, {}, {"processor_configs": {}})
        assert call_log["resp"] == {"data": "ok"}


# ============================================================================
# TestMQConnectionManager — 连接管理
# ============================================================================

class TestMQConnectionManager:
    """验证 _MQConnectionManager 的缓存、线程安全。"""

    def test_requires_kombu_installed(self):
        with patch("processors.mq._ensure_kombu", side_effect=ProcessorError(
            "Kombu is required", processor_name="mq"
        )):
            with pytest.raises(ProcessorError, match="Kombu is required"):
                _MQConnectionManager.get_connection("amqp://localhost//")

    def test_caches_connection_by_url(self):
        _MQConnectionManager._connections.clear()
        mock_conn = MagicMock()

        with patch("processors.mq._KOMBU_AVAILABLE", True), \
             patch("processors.mq._kombu_module") as mock_mod:
            mock_mod.Connection.side_effect = lambda url: MagicMock() if url == "amqp://u1//" else MagicMock()

            c1 = _MQConnectionManager.get_connection("amqp://u1//")
            c2 = _MQConnectionManager.get_connection("amqp://u1//")
            c3 = _MQConnectionManager.get_connection("amqp://u2//")

            assert c1 is c2
            assert c1 is not c3
            assert mock_mod.Connection.call_count == 2

    def test_thread_safety(self):
        mock_conn = MagicMock()
        results = []
        errors = []

        def worker():
            try:
                c = _MQConnectionManager.get_connection("amqp://t:5672//")
                results.append(c)
            except Exception as exc:
                errors.append(exc)

        with patch("processors.mq._KOMBU_AVAILABLE", True), \
             patch("processors.mq._kombu_module") as mock_mod:
            mock_mod.Connection.return_value = mock_conn
            _MQConnectionManager._connections.clear()

            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert len(errors) == 0
        assert len(set(id(r) for r in results)) == 1


# ============================================================================
# TestMQConnectionConfig — 连接配置验证
# ============================================================================

class TestMQConnectionConfig:
    """验证 _get_connection 的配置读取和错误处理。"""

    def test_missing_processor_configs_raises(self):
        class Plugin(BaseMQPlugin):
            name = "mq-missing-cfg"

        plugin = Plugin()
        with pytest.raises(MQConnectionError, match="processor_configs"):
            plugin._get_connection({})

    def test_empty_mq_url_raises(self):
        class Plugin(BaseMQPlugin):
            name = "mq-no-url"

        plugin = Plugin()
        with pytest.raises(MQConnectionError, match="mq_url"):
            plugin._get_connection({"processor_configs": {"mq-no-url": {}}})

    def test_connects_with_valid_url(self):
        mock_conn = MagicMock()

        class Plugin(BaseMQPlugin):
            name = "mq-valid-url"

        with patch("processors.mq._KOMBU_AVAILABLE", True), \
             patch("processors.mq._MQConnectionManager.get_connection",
                   return_value=mock_conn):
            plugin = Plugin()
            conn = plugin._get_connection({
                "processor_configs": {
                    "mq-valid-url": {"mq_url": "amqp://guest:guest@localhost//"}
                }
            })
            assert conn is mock_conn
