"""Tests for processors.rocketmq — BaseRocketMQPlugin, _RocketMQManager, auto-registration."""

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
from processors.rocketmq import (
    BaseRocketMQPlugin,
    RocketMQConnectionError,
    _ROCKETMQ_PLUGIN_REGISTRY,
    _RocketMQManager,
)


# ---------------------------------------------------------------------------
# helpers: clean registries before each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_registries():
    """清理所有注册表，确保测试隔离。Clean all registries for test isolation."""
    _PRE_PROCESSOR_REGISTRY.clear()
    _POST_PROCESSOR_REGISTRY.clear()
    _ROCKETMQ_PLUGIN_REGISTRY.clear()
    _RocketMQManager._producers.clear()
    yield
    _PRE_PROCESSOR_REGISTRY.clear()
    _POST_PROCESSOR_REGISTRY.clear()
    _ROCKETMQ_PLUGIN_REGISTRY.clear()
    _RocketMQManager._producers.clear()


# ============================================================================
# TestBaseRocketMQPluginRegistration — 注册机制
# ============================================================================

class TestBaseRocketMQPluginRegistration:
    """验证 BaseRocketMQPlugin 子类的自动注册。"""

    def test_registers_in_rocketmq_plugin_registry(self):
        class MyPlugin(BaseRocketMQPlugin):
            name = "my-rmq-plugin"

        assert "my-rmq-plugin" in _ROCKETMQ_PLUGIN_REGISTRY

    def test_auto_creates_pre_processor_wrapper(self):
        class MyPlugin(BaseRocketMQPlugin):
            name = "rmq-pre-test"

        assert "rmq-pre-test" in _PRE_PROCESSOR_REGISTRY
        assert issubclass(_PRE_PROCESSOR_REGISTRY["rmq-pre-test"], PreProcessor)

    def test_auto_creates_post_processor_wrapper(self):
        class MyPlugin(BaseRocketMQPlugin):
            name = "rmq-post-test"

        assert "rmq-post-test" in _POST_PROCESSOR_REGISTRY
        assert issubclass(_POST_PROCESSOR_REGISTRY["rmq-post-test"], PostProcessor)

    def test_raises_type_error_when_name_missing(self):
        with pytest.raises(TypeError, match="must define a 'name'"):
            class BadPlugin(BaseRocketMQPlugin):  # noqa: F841
                pass


# ============================================================================
# TestWrapperDelegation — 包装器委托
# ============================================================================

class TestWrapperDelegation:
    """验证 Pre/PostProcessor 包装器正确委托到 BaseRocketMQPlugin。"""

    def test_pre_wrapper_delegates_to_before_request(self):
        class MyPlugin(BaseRocketMQPlugin):
            name = "rmq-delegate-pre"

            def before_request(self, headers, body, case_config, global_config):
                body["rmq_injected"] = True
                return headers, body

        pre_cls = _PRE_PROCESSOR_REGISTRY["rmq-delegate-pre"]
        instance = pre_cls()
        h, b = instance.process({}, {"key": "val"}, {}, {"processor_configs": {}})
        assert b["rmq_injected"] is True

    def test_post_wrapper_delegates_to_after_response(self):
        call_log = {}

        class MyPlugin(BaseRocketMQPlugin):
            name = "rmq-delegate-post"

            def after_response(self, rh, rb, rsh, rsb, cc, gc):
                call_log["resp"] = rsb

        post_cls = _POST_PROCESSOR_REGISTRY["rmq-delegate-post"]
        instance = post_cls()
        instance.process({}, {}, {}, {"data": "ok"}, {}, {"processor_configs": {}})
        assert call_log["resp"] == {"data": "ok"}


# ============================================================================
# TestRocketMQManager — Producer 管理
# ============================================================================

class TestRocketMQManager:
    """验证 _RocketMQManager 的缓存、线程安全。"""

    def test_requires_rocketmq_installed(self):
        with patch("processors.rocketmq._ensure_rocketmq", side_effect=ProcessorError(
            "rocketmq-client-python is required", processor_name="rocketmq"
        )):
            with pytest.raises(ProcessorError, match="rocketmq-client-python"):
                _RocketMQManager.get_producer("localhost:9876", "test-group")

    def test_caches_producer_by_namesrv_and_group(self):
        _RocketMQManager._producers.clear()
        mock_producer = MagicMock()

        with patch("processors.rocketmq._ROCKETMQ_AVAILABLE", True), \
             patch("processors.rocketmq._rocketmq_client") as mock_client:
            mock_client.Producer.side_effect = lambda gid: MagicMock()

            p1 = _RocketMQManager.get_producer("ns1:9876", "g1")
            p2 = _RocketMQManager.get_producer("ns1:9876", "g1")
            p3 = _RocketMQManager.get_producer("ns2:9876", "g1")

            assert p1 is p2
            assert p1 is not p3
            assert mock_client.Producer.call_count == 2

    def test_thread_safety(self):
        mock_producer = MagicMock()
        results = []
        errors = []

        def worker():
            try:
                p = _RocketMQManager.get_producer("t:9876", "tg")
                results.append(p)
            except Exception as exc:
                errors.append(exc)

        with patch("processors.rocketmq._ROCKETMQ_AVAILABLE", True), \
             patch("processors.rocketmq._rocketmq_client") as mock_client:
            mock_client.Producer.return_value = mock_producer
            _RocketMQManager._producers.clear()

            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert len(errors) == 0
        assert len(set(id(r) for r in results)) == 1


# ============================================================================
# TestRocketMQConnectionConfig — 连接配置验证
# ============================================================================

class TestRocketMQConnectionConfig:
    """验证 _get_producer 的配置读取和错误处理。"""

    def test_missing_processor_configs_raises(self):
        class Plugin(BaseRocketMQPlugin):
            name = "rmq-missing-cfg"

        plugin = Plugin()
        with pytest.raises(RocketMQConnectionError, match="processor_configs"):
            plugin._get_producer({})

    def test_empty_namesrv_addr_raises(self):
        class Plugin(BaseRocketMQPlugin):
            name = "rmq-no-ns"

        plugin = Plugin()
        with pytest.raises(RocketMQConnectionError, match="namesrv_addr"):
            plugin._get_producer({"processor_configs": {"rmq-no-ns": {}}})

    def test_empty_group_id_raises(self):
        class Plugin(BaseRocketMQPlugin):
            name = "rmq-no-gid"

        plugin = Plugin()
        with pytest.raises(RocketMQConnectionError, match="group_id"):
            plugin._get_producer({
                "processor_configs": {
                    "rmq-no-gid": {"namesrv_addr": "localhost:9876"}
                }
            })

    def test_connects_with_valid_config(self):
        mock_producer = MagicMock()

        class Plugin(BaseRocketMQPlugin):
            name = "rmq-valid"

        with patch("processors.rocketmq._ROCKETMQ_AVAILABLE", True), \
             patch("processors.rocketmq._RocketMQManager.get_producer",
                   return_value=mock_producer):
            plugin = Plugin()
            producer = plugin._get_producer({
                "processor_configs": {
                    "rmq-valid": {
                        "namesrv_addr": "localhost:9876",
                        "group_id": "test-group",
                    }
                }
            })
            assert producer is mock_producer
