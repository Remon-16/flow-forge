"""Tests for processors.pulsar — BasePulsarPlugin, _PulsarClientManager, auto-registration."""

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
from processors.pulsar import (
    BasePulsarPlugin,
    PulsarConnectionError,
    _PULSAR_PLUGIN_REGISTRY,
    _PulsarClientManager,
)


# ---------------------------------------------------------------------------
# helpers: clean registries before each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_registries():
    """清理所有注册表，确保测试隔离。Clean all registries for test isolation."""
    _PRE_PROCESSOR_REGISTRY.clear()
    _POST_PROCESSOR_REGISTRY.clear()
    _PULSAR_PLUGIN_REGISTRY.clear()
    _PulsarClientManager._clients.clear()
    yield
    _PRE_PROCESSOR_REGISTRY.clear()
    _POST_PROCESSOR_REGISTRY.clear()
    _PULSAR_PLUGIN_REGISTRY.clear()
    _PulsarClientManager._clients.clear()


# ============================================================================
# TestBasePulsarPluginRegistration — 注册机制
# ============================================================================

class TestBasePulsarPluginRegistration:
    """验证 BasePulsarPlugin 子类的自动注册。"""

    def test_registers_in_pulsar_plugin_registry(self):
        """__init_subclass__ 自动注册到 _PULSAR_PLUGIN_REGISTRY。"""
        class MyPlugin(BasePulsarPlugin):
            name = "my-pulsar-plugin"

        assert "my-pulsar-plugin" in _PULSAR_PLUGIN_REGISTRY
        assert _PULSAR_PLUGIN_REGISTRY["my-pulsar-plugin"] is MyPlugin

    def test_auto_creates_pre_processor_wrapper(self):
        """自动创建 PreProcessor 包装类并注册。"""
        class MyPlugin(BasePulsarPlugin):
            name = "pulsar-pre-test"

        assert "pulsar-pre-test" in _PRE_PROCESSOR_REGISTRY
        wrapper_cls = _PRE_PROCESSOR_REGISTRY["pulsar-pre-test"]
        assert issubclass(wrapper_cls, PreProcessor)

    def test_auto_creates_post_processor_wrapper(self):
        """自动创建 PostProcessor 包装类并注册。"""
        class MyPlugin(BasePulsarPlugin):
            name = "pulsar-post-test"

        assert "pulsar-post-test" in _POST_PROCESSOR_REGISTRY
        wrapper_cls = _POST_PROCESSOR_REGISTRY["pulsar-post-test"]
        assert issubclass(wrapper_cls, PostProcessor)

    def test_raises_type_error_when_name_missing(self):
        """未定义 name 时抛出 TypeError。"""
        with pytest.raises(TypeError, match="must define a 'name'"):
            class BadPlugin(BasePulsarPlugin):  # noqa: F841
                pass


# ============================================================================
# TestWrapperDelegation — 包装器委托
# ============================================================================

class TestWrapperDelegation:
    """验证 Pre/PostProcessor 包装器正确委托到 BasePulsarPlugin。"""

    def test_pre_wrapper_delegates_to_before_request(self):
        """PreProcessor 包装器委托到 before_request()。"""
        class MyPlugin(BasePulsarPlugin):
            name = "pulsar-delegate-pre"

            def before_request(self, headers, body, case_config, global_config):
                body["pulsar_injected"] = True
                return headers, body

        pre_cls = _PRE_PROCESSOR_REGISTRY["pulsar-delegate-pre"]
        instance = pre_cls()
        h, b = instance.process({}, {"key": "val"}, {}, {"processor_configs": {}})
        assert b["pulsar_injected"] is True

    def test_post_wrapper_delegates_to_after_response(self):
        """PostProcessor 包装器委托到 after_response()。"""
        call_log = {}

        class MyPlugin(BasePulsarPlugin):
            name = "pulsar-delegate-post"

            def after_response(self, rh, rb, rsh, rsb, cc, gc):
                call_log["resp"] = rsb

        post_cls = _POST_PROCESSOR_REGISTRY["pulsar-delegate-post"]
        instance = post_cls()
        instance.process({}, {}, {}, {"data": "ok"}, {}, {"processor_configs": {}})
        assert call_log["resp"] == {"data": "ok"}


# ============================================================================
# TestPulsarClientManager — Client 管理
# ============================================================================

class TestPulsarClientManager:
    """验证 _PulsarClientManager 的缓存、线程安全。"""

    def test_requires_pulsar_client_installed(self):
        """pulsar-client 未安装时抛出友好错误。"""
        with patch("processors.pulsar._ensure_pulsar_client", side_effect=ProcessorError(
            "pulsar-client is required", processor_name="pulsar"
        )):
            with pytest.raises(ProcessorError, match="pulsar-client"):
                _PulsarClientManager.get_client("pulsar://localhost:6650")

    def test_caches_client_by_service_url(self):
        """相同 service_url 返回同一 Client，不同则不同。"""
        _PulsarClientManager._clients.clear()

        with patch("processors.pulsar._PULSAR_AVAILABLE", True), \
             patch("processors.pulsar._pulsar_module") as mock_mod:
            mock_mod.Client.side_effect = lambda url: MagicMock()

            c1 = _PulsarClientManager.get_client("pulsar://srv1:6650")
            c2 = _PulsarClientManager.get_client("pulsar://srv1:6650")
            c3 = _PulsarClientManager.get_client("pulsar://srv2:6650")

            assert c1 is c2  # Same URL → same Client
            assert c1 is not c3  # Different URL → different Client
            assert mock_mod.Client.call_count == 2

    def test_thread_safety(self):
        """多线程并发调用 get_client 无竞争。"""
        mock_client = MagicMock()
        results = []
        errors = []

        def worker():
            try:
                c = _PulsarClientManager.get_client("pulsar://t:6650")
                results.append(c)
            except Exception as exc:
                errors.append(exc)

        with patch("processors.pulsar._PULSAR_AVAILABLE", True), \
             patch("processors.pulsar._pulsar_module") as mock_mod:
            mock_mod.Client.return_value = mock_client
            _PulsarClientManager._clients.clear()

            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert len(errors) == 0
        assert len(set(id(r) for r in results)) == 1


# ============================================================================
# TestPulsarConnectionConfig — 连接配置验证
# ============================================================================

class TestPulsarConnectionConfig:
    """验证 _get_client 的配置读取和错误处理。"""

    def test_missing_processor_configs_raises(self):
        """缺少 processor_configs 时抛出 PulsarConnectionError。"""
        class Plugin(BasePulsarPlugin):
            name = "pulsar-missing-cfg"

        plugin = Plugin()
        with pytest.raises(PulsarConnectionError, match="processor_configs"):
            plugin._get_client({})

    def test_empty_service_url_raises(self):
        """service_url 为空时抛出 PulsarConnectionError。"""
        class Plugin(BasePulsarPlugin):
            name = "pulsar-no-url"

        plugin = Plugin()
        with pytest.raises(PulsarConnectionError, match="service_url"):
            plugin._get_client({"processor_configs": {"pulsar-no-url": {}}})

    def test_connects_with_valid_config(self):
        """有效配置下获取 Client。"""
        mock_client = MagicMock()

        class Plugin(BasePulsarPlugin):
            name = "pulsar-valid"

        with patch("processors.pulsar._PULSAR_AVAILABLE", True), \
             patch("processors.pulsar._PulsarClientManager.get_client",
                   return_value=mock_client):
            plugin = Plugin()
            client = plugin._get_client({
                "processor_configs": {
                    "pulsar-valid": {
                        "service_url": "pulsar://localhost:6650",
                        "topic": "order-topic",
                    }
                }
            })
            assert client is mock_client
