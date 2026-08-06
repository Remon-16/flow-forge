"""Tests for processors.redis — BaseRedisPlugin, _RedisConnectionManager, auto-registration."""

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
from processors.redis import (
    BaseRedisPlugin,
    RedisConnectionError,
    _REDIS_PLUGIN_REGISTRY,
    _RedisConnectionManager,
)


# ---------------------------------------------------------------------------
# helpers: clean registries before each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_registries():
    """清理所有注册表，确保测试隔离。Clean all registries for test isolation."""
    _PRE_PROCESSOR_REGISTRY.clear()
    _POST_PROCESSOR_REGISTRY.clear()
    _REDIS_PLUGIN_REGISTRY.clear()
    _RedisConnectionManager._clients.clear()
    yield
    _PRE_PROCESSOR_REGISTRY.clear()
    _POST_PROCESSOR_REGISTRY.clear()
    _REDIS_PLUGIN_REGISTRY.clear()
    _RedisConnectionManager._clients.clear()


# ============================================================================
# TestBaseRedisPluginRegistration — 注册机制
# ============================================================================

class TestBaseRedisPluginRegistration:
    """验证 BaseRedisPlugin 子类的自动注册。"""

    def test_registers_in_redis_plugin_registry(self):
        """__init_subclass__ 自动注册到 _REDIS_PLUGIN_REGISTRY。"""
        class MyPlugin(BaseRedisPlugin):
            name = "my-redis-plugin"

        assert "my-redis-plugin" in _REDIS_PLUGIN_REGISTRY
        assert _REDIS_PLUGIN_REGISTRY["my-redis-plugin"] is MyPlugin

    def test_auto_creates_pre_processor_wrapper(self):
        """自动创建 PreProcessor 包装类并注册。"""
        class MyPlugin(BaseRedisPlugin):
            name = "redis-pre-test"

        assert "redis-pre-test" in _PRE_PROCESSOR_REGISTRY
        wrapper_cls = _PRE_PROCESSOR_REGISTRY["redis-pre-test"]
        assert issubclass(wrapper_cls, PreProcessor)

    def test_auto_creates_post_processor_wrapper(self):
        """自动创建 PostProcessor 包装类并注册。"""
        class MyPlugin(BaseRedisPlugin):
            name = "redis-post-test"

        assert "redis-post-test" in _POST_PROCESSOR_REGISTRY
        wrapper_cls = _POST_PROCESSOR_REGISTRY["redis-post-test"]
        assert issubclass(wrapper_cls, PostProcessor)

    def test_raises_type_error_when_name_missing(self):
        """未定义 name 时抛出 TypeError。"""
        with pytest.raises(TypeError, match="must define a 'name'"):
            class BadPlugin(BaseRedisPlugin):  # noqa: F841
                pass


# ============================================================================
# TestWrapperDelegation — 包装器委托
# ============================================================================

class TestWrapperDelegation:
    """验证 Pre/PostProcessor 包装器正确委托到 BaseRedisPlugin。"""

    def test_pre_wrapper_delegates_to_before_request(self):
        """PreProcessor 包装器委托到 before_request()。"""
        class MyPlugin(BaseRedisPlugin):
            name = "redis-delegate-pre"

            def before_request(self, headers, body, case_config, global_config):
                body["redis_injected"] = True
                return headers, body

        pre_cls = _PRE_PROCESSOR_REGISTRY["redis-delegate-pre"]
        instance = pre_cls()
        h, b = instance.process(
            {"h": "val"}, {"key": "val"}, {}, {"processor_configs": {}}
        )
        assert b["redis_injected"] is True

    def test_post_wrapper_delegates_to_after_response(self):
        """PostProcessor 包装器委托到 after_response()。"""
        call_log = {}

        class MyPlugin(BaseRedisPlugin):
            name = "redis-delegate-post"

            def after_response(self, request_headers, request_body,
                               response_headers, response_body,
                               case_config, global_config):
                call_log["resp"] = response_body

        post_cls = _POST_PROCESSOR_REGISTRY["redis-delegate-post"]
        instance = post_cls()
        instance.process({}, {}, {}, {"data": "ok"}, {}, {"processor_configs": {}})
        assert call_log["resp"] == {"data": "ok"}


# ============================================================================
# TestBaseRedisPluginDefaults — 默认行为
# ============================================================================

class TestBaseRedisPluginDefaults:
    """验证 before_request / after_response 默认 no-op 行为。"""

    def test_before_request_default_is_noop(self):
        class Plugin(BaseRedisPlugin):
            name = "redis-noop-pre"

        pre_cls = _PRE_PROCESSOR_REGISTRY["redis-noop-pre"]
        instance = pre_cls()
        h, b = instance.process(
            {"h": "val"}, {"b": "val"}, {}, {"processor_configs": {}}
        )
        assert h == {"h": "val"}
        assert b == {"b": "val"}

    def test_after_response_default_is_noop(self):
        class Plugin(BaseRedisPlugin):
            name = "redis-noop-post"

        post_cls = _POST_PROCESSOR_REGISTRY["redis-noop-post"]
        instance = post_cls()
        instance.process({}, {}, {}, None, {}, {"processor_configs": {}})


# ============================================================================
# TestRedisConnectionManager — 连接池管理
# ============================================================================

class TestRedisConnectionManager:
    """验证 _RedisConnectionManager 的懒加载、缓存、线程安全。"""

    def test_requires_redis_installed(self):
        """redis-py 未安装时抛出友好错误。"""
        with patch("processors.redis._ensure_redis", side_effect=ProcessorError(
            "redis-py is required", processor_name="redis"
        )):
            with pytest.raises(ProcessorError, match="redis-py is required"):
                _RedisConnectionManager.get_client("redis://localhost/0")

    def test_caches_client_by_url(self):
        """相同 URL 返回同一客户端，不同 URL 返回不同客户端。"""
        _RedisConnectionManager._clients.clear()
        mock_pool = MagicMock()
        mock_client_1 = MagicMock()
        mock_client_2 = MagicMock()

        with patch("processors.redis._REDIS_AVAILABLE", True), \
             patch("processors.redis._redis_module") as mock_mod:
            mock_mod.ConnectionPool.from_url.return_value = mock_pool
            mock_mod.Redis.side_effect = [mock_client_1, mock_client_2]

            c1 = _RedisConnectionManager.get_client("redis://h1/0")
            c2 = _RedisConnectionManager.get_client("redis://h1/0")  # cached
            c3 = _RedisConnectionManager.get_client("redis://h2/0")  # new URL

            assert c1 is c2  # Same URL → same client (cached)
            assert c1 is not c3  # Different URL → different client
            assert mock_mod.ConnectionPool.from_url.call_count == 2

    def test_uses_default_protocol_when_ping_succeeds(self):
        """ping 成功时不降级，保持 redis-py 默认协议（新版 RESP3）。
        No fallback when ping succeeds; keep the redis-py default protocol (RESP3 in recent versions)."""
        _RedisConnectionManager._clients.clear()
        mock_pool = MagicMock()

        with patch("processors.redis._REDIS_AVAILABLE", True), \
             patch("processors.redis._redis_module") as mock_mod:
            mock_mod.ConnectionPool.from_url.return_value = mock_pool
            mock_mod.Redis.return_value = MagicMock()
            _RedisConnectionManager.get_client("redis://localhost:6379/0")

        mock_mod.ConnectionPool.from_url.assert_called_once_with("redis://localhost:6379/0")

    def test_falls_back_to_resp2_on_protocol_error(self):
        """旧版 Redis（如 5.x，不支持 HELLO/RESP3）时自动降级为 RESP2。
        Automatically fall back to RESP2 for legacy Redis (e.g. 5.x without HELLO/RESP3)."""
        _RedisConnectionManager._clients.clear()

        from redis.exceptions import ResponseError

        class _FakePool:
            pass

        with patch("processors.redis._REDIS_AVAILABLE", True), \
             patch("processors.redis._redis_module") as mock_mod:
            mock_mod.ConnectionPool.from_url.side_effect = [
                _FakePool(),  # 第一次默认协议 / first, default protocol
                _FakePool(),  # 第二次 RESP2 / second, RESP2
            ]
            first_client = MagicMock()
            second_client = MagicMock()
            first_client.ping.side_effect = ResponseError("unknown command `HELLO`")
            mock_mod.Redis.side_effect = [first_client, second_client]

            client = _RedisConnectionManager.get_client("redis://localhost:6379/0")

        assert client is second_client
        calls = mock_mod.ConnectionPool.from_url.call_args_list
        assert len(calls) == 2
        assert calls[0] == (("redis://localhost:6379/0",), {})
        assert calls[1] == (("redis://localhost:6379/0",), {"protocol": 2})
        second_client.ping.assert_called_once()

    def test_raises_connection_error_on_non_protocol_failure(self):
        """非协议类连接失败应原样抛出 RedisConnectionError，不降级。
        Non-protocol connection failures raise RedisConnectionError without fallback."""
        _RedisConnectionManager._clients.clear()

        with patch("processors.redis._REDIS_AVAILABLE", True), \
             patch("processors.redis._redis_module") as mock_mod:
            mock_mod.ConnectionPool.from_url.return_value = MagicMock()
            mock_client = MagicMock()
            mock_client.ping.side_effect = ConnectionError("connection refused")
            mock_mod.Redis.return_value = mock_client

            with pytest.raises(RedisConnectionError):
                _RedisConnectionManager.get_client("redis://localhost:6379/0")

        mock_mod.ConnectionPool.from_url.assert_called_once()

    def test_thread_safety(self):
        """多线程并发调用 get_client 无竞争。"""
        mock_pool = MagicMock()
        mock_redis = MagicMock()
        results = []
        errors = []

        def worker():
            try:
                c = _RedisConnectionManager.get_client("redis://t:6379/0")
                results.append(c)
            except Exception as exc:
                errors.append(exc)

        with patch("processors.redis._REDIS_AVAILABLE", True), \
             patch("processors.redis._redis_module") as mock_mod:
            mock_mod.ConnectionPool.from_url.return_value = mock_pool
            mock_mod.Redis.return_value = mock_redis
            _RedisConnectionManager._clients.clear()

            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert len(errors) == 0
        assert len(set(id(r) for r in results)) == 1


# ============================================================================
# TestRedisConnectionConfig — 连接配置验证
# ============================================================================

class TestRedisConnectionConfig:
    """验证 _get_client 的配置读取和错误处理。"""

    def test_missing_processor_configs_raises(self):
        class Plugin(BaseRedisPlugin):
            name = "redis-missing-cfg"

        plugin = Plugin()
        with pytest.raises(RedisConnectionError, match="processor_configs"):
            plugin._get_client({})

    def test_missing_processor_entry_raises(self):
        class Plugin(BaseRedisPlugin):
            name = "redis-no-entry"

        plugin = Plugin()
        with pytest.raises(RedisConnectionError, match="redis-no-entry"):
            plugin._get_client({"processor_configs": {}})

    def test_empty_redis_url_raises(self):
        class Plugin(BaseRedisPlugin):
            name = "redis-no-url"

        plugin = Plugin()
        with pytest.raises(RedisConnectionError, match="redis_url"):
            plugin._get_client({"processor_configs": {"redis-no-url": {}}})

    def test_connects_with_valid_url(self):
        mock_client = MagicMock()

        class Plugin(BaseRedisPlugin):
            name = "redis-valid-url"

        with patch("processors.redis._REDIS_AVAILABLE", True), \
             patch("processors.redis._RedisConnectionManager.get_client",
                   return_value=mock_client):
            plugin = Plugin()
            client = plugin._get_client({
                "processor_configs": {
                    "redis-valid-url": {"redis_url": "redis://u:p@h/0"}
                }
            })
            assert client is mock_client
