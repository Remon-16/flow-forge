"""Tests for processors.kafka — BaseKafkaPlugin, _KafkaProducerManager, auto-registration."""

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
from processors.kafka import (
    BaseKafkaPlugin,
    KafkaConnectionError,
    _KAFKA_PLUGIN_REGISTRY,
    _KafkaProducerManager,
)


# ---------------------------------------------------------------------------
# helpers: clean registries before each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_registries():
    """清理所有注册表，确保测试隔离。Clean all registries for test isolation."""
    _PRE_PROCESSOR_REGISTRY.clear()
    _POST_PROCESSOR_REGISTRY.clear()
    _KAFKA_PLUGIN_REGISTRY.clear()
    _KafkaProducerManager._producers.clear()
    yield
    _PRE_PROCESSOR_REGISTRY.clear()
    _POST_PROCESSOR_REGISTRY.clear()
    _KAFKA_PLUGIN_REGISTRY.clear()
    _KafkaProducerManager._producers.clear()


# ============================================================================
# TestBaseKafkaPluginRegistration — 注册机制
# ============================================================================

class TestBaseKafkaPluginRegistration:
    """验证 BaseKafkaPlugin 子类的自动注册。"""

    def test_registers_in_kafka_plugin_registry(self):
        """__init_subclass__ 自动注册到 _KAFKA_PLUGIN_REGISTRY。"""
        class MyPlugin(BaseKafkaPlugin):
            name = "my-kafka-plugin"

        assert "my-kafka-plugin" in _KAFKA_PLUGIN_REGISTRY
        assert _KAFKA_PLUGIN_REGISTRY["my-kafka-plugin"] is MyPlugin

    def test_auto_creates_pre_processor_wrapper(self):
        """自动创建 PreProcessor 包装类并注册。"""
        class MyPlugin(BaseKafkaPlugin):
            name = "kafka-pre-test"

        assert "kafka-pre-test" in _PRE_PROCESSOR_REGISTRY
        wrapper_cls = _PRE_PROCESSOR_REGISTRY["kafka-pre-test"]
        assert issubclass(wrapper_cls, PreProcessor)

    def test_auto_creates_post_processor_wrapper(self):
        """自动创建 PostProcessor 包装类并注册。"""
        class MyPlugin(BaseKafkaPlugin):
            name = "kafka-post-test"

        assert "kafka-post-test" in _POST_PROCESSOR_REGISTRY
        wrapper_cls = _POST_PROCESSOR_REGISTRY["kafka-post-test"]
        assert issubclass(wrapper_cls, PostProcessor)

    def test_raises_type_error_when_name_missing(self):
        """未定义 name 时抛出 TypeError。"""
        with pytest.raises(TypeError, match="must define a 'name'"):
            class BadPlugin(BaseKafkaPlugin):  # noqa: F841
                pass


# ============================================================================
# TestWrapperDelegation — 包装器委托
# ============================================================================

class TestWrapperDelegation:
    """验证 Pre/PostProcessor 包装器正确委托到 BaseKafkaPlugin。"""

    def test_pre_wrapper_delegates_to_before_request(self):
        """PreProcessor 包装器委托到 before_request()。"""
        class MyPlugin(BaseKafkaPlugin):
            name = "kafka-delegate-pre"

            def before_request(self, headers, body, case_config, global_config):
                body["kafka_injected"] = True
                return headers, body

        pre_cls = _PRE_PROCESSOR_REGISTRY["kafka-delegate-pre"]
        instance = pre_cls()
        h, b = instance.process({}, {"key": "val"}, {}, {"processor_configs": {}})
        assert b["kafka_injected"] is True

    def test_post_wrapper_delegates_to_after_response(self):
        """PostProcessor 包装器委托到 after_response()。"""
        call_log = {}

        class MyPlugin(BaseKafkaPlugin):
            name = "kafka-delegate-post"

            def after_response(self, rh, rb, rsh, rsb, cc, gc):
                call_log["resp"] = rsb

        post_cls = _POST_PROCESSOR_REGISTRY["kafka-delegate-post"]
        instance = post_cls()
        instance.process({}, {}, {}, {"data": "ok"}, {}, {"processor_configs": {}})
        assert call_log["resp"] == {"data": "ok"}


# ============================================================================
# TestKafkaProducerManager — Producer 管理
# ============================================================================

class TestKafkaProducerManager:
    """验证 _KafkaProducerManager 的缓存、线程安全。"""

    def test_requires_confluent_kafka_installed(self):
        """confluent-kafka 未安装时抛出友好错误。"""
        with patch("processors.kafka._ensure_confluent_kafka", side_effect=ProcessorError(
            "confluent-kafka is required", processor_name="kafka"
        )):
            with pytest.raises(ProcessorError, match="confluent-kafka"):
                _KafkaProducerManager.get_producer("localhost:9092")

    def test_caches_producer_by_bootstrap_servers(self):
        """相同 bootstrap_servers 返回同一 Producer，不同则不同。"""
        _KafkaProducerManager._producers.clear()

        with patch("processors.kafka._KAFKA_AVAILABLE", True), \
             patch("processors.kafka._confluent_kafka_module") as mock_mod:
            mock_mod.Producer.side_effect = lambda config: MagicMock()

            p1 = _KafkaProducerManager.get_producer("srv1:9092", "c1")
            p2 = _KafkaProducerManager.get_producer("srv1:9092", "c1")
            p3 = _KafkaProducerManager.get_producer("srv2:9092", "c1")

            assert p1 is p2  # Same (servers, client_id) → same Producer
            assert p1 is not p3  # Different servers → different Producer
            assert mock_mod.Producer.call_count == 2

    def test_thread_safety(self):
        """多线程并发调用 get_producer 无竞争。"""
        mock_producer = MagicMock()
        results = []
        errors = []

        def worker():
            try:
                p = _KafkaProducerManager.get_producer("t:9092", "tg")
                results.append(p)
            except Exception as exc:
                errors.append(exc)

        with patch("processors.kafka._KAFKA_AVAILABLE", True), \
             patch("processors.kafka._confluent_kafka_module") as mock_mod:
            mock_mod.Producer.return_value = mock_producer
            _KafkaProducerManager._producers.clear()

            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert len(errors) == 0
        assert len(set(id(r) for r in results)) == 1


# ============================================================================
# TestKafkaConnectionConfig — 连接配置验证
# ============================================================================

class TestKafkaConnectionConfig:
    """验证 _get_producer 的配置读取和错误处理。"""

    def test_missing_processor_configs_raises(self):
        """缺少 processor_configs 时抛出 KafkaConnectionError。"""
        class Plugin(BaseKafkaPlugin):
            name = "kafka-missing-cfg"

        plugin = Plugin()
        with pytest.raises(KafkaConnectionError, match="processor_configs"):
            plugin._get_producer({})

    def test_empty_bootstrap_servers_raises(self):
        """bootstrap_servers 为空时抛出 KafkaConnectionError。"""
        class Plugin(BaseKafkaPlugin):
            name = "kafka-no-bs"

        plugin = Plugin()
        with pytest.raises(KafkaConnectionError, match="bootstrap_servers"):
            plugin._get_producer({"processor_configs": {"kafka-no-bs": {}}})

    def test_connects_with_valid_config(self):
        """有效配置下获取 Producer。"""
        mock_producer = MagicMock()

        class Plugin(BaseKafkaPlugin):
            name = "kafka-valid"

        with patch("processors.kafka._KAFKA_AVAILABLE", True), \
             patch("processors.kafka._KafkaProducerManager.get_producer",
                   return_value=mock_producer):
            plugin = Plugin()
            producer = plugin._get_producer({
                "processor_configs": {
                    "kafka-valid": {
                        "bootstrap_servers": "localhost:9092",
                        "topic": "order-topic",
                    }
                }
            })
            assert producer is mock_producer
