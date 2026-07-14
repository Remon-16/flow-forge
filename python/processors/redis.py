"""Redis 处理器基类 — 提供连接池管理、Redis 操作、自动注册。
Redis processor base — connection pool, Redis operations, auto-registration.

用户只需继承 ``BaseRedisPlugin``，实现 ``before_request`` / ``after_response``，
框架自动为其创建 PreProcessor / PostProcessor 包装类并注册到全局注册表。

Users extend ``BaseRedisPlugin``, implement ``before_request`` / ``after_response``,
and the framework auto-creates PreProcessor / PostProcessor wrappers registered
in the global registries.
"""

import logging
import threading
from abc import ABC
from typing import Any, Dict, Optional, Tuple, Type

from processors.base import (
    ProcessorError,
    _create_external_plugin_wrappers,
    _mask_password,
)

logger = logging.getLogger(__name__)

# ============================================================================
# redis-py 延迟导入 / Lazy import — only when a Redis processor is triggered
# ============================================================================
_REDIS_AVAILABLE = False
_redis_module = None


def _ensure_redis():
    """确保 redis-py 可用，否则给出友好错误提示。
    Ensure redis-py is importable; raise with install hint otherwise."""
    global _REDIS_AVAILABLE, _redis_module
    if _REDIS_AVAILABLE:
        return
    try:
        import redis as _r
        _redis_module = _r
        _REDIS_AVAILABLE = True
    except ImportError:
        raise ProcessorError(
            "redis-py is required for Redis processors. "
            "Install it with: pip install redis",
            processor_name="redis",
        )


# ============================================================================
# 自定义异常 / Custom exceptions
# ============================================================================

class RedisConnectionError(ProcessorError):
    """Redis 连接失败。Redis connection failure."""


# ============================================================================
# Redis 连接管理器 — 单例、懒加载、按 redis_url 缓存 / Connection manager
# ============================================================================

class _RedisConnectionManager:
    """Redis 连接池管理器（线程安全）。
    Redis connection pool manager (thread-safe).

    相同 ``redis_url`` 的多个处理器共享同一个 Redis 客户端。
    Multiple processors with the same ``redis_url`` share one Redis client.
    """

    _clients: Dict[str, Any] = {}
    _lock = threading.Lock()

    @classmethod
    def get_client(cls, redis_url: str):
        """获取或创建 Redis 客户端。Get or create a Redis client for the given URL.

        懒加载：首次调用时才创建 ConnectionPool 和客户端。
        Lazy: ConnectionPool and client are created on first access.

        返回的客户端附带内置连接池，线程安全，不需要手动归还。
        The returned client has built-in connection pooling, thread-safe.
        """
        _ensure_redis()
        with cls._lock:
            if redis_url not in cls._clients:
                pool = _redis_module.ConnectionPool.from_url(redis_url)
                cls._clients[redis_url] = _redis_module.Redis(connection_pool=pool)
                safe_url = _mask_password(redis_url)
                logger.info("Redis client created for: %s", safe_url)
        return cls._clients[redis_url]


# ============================================================================
# Redis 插件注册表 / Redis plugin registry
# ============================================================================

_REDIS_PLUGIN_REGISTRY: Dict[str, Type["BaseRedisPlugin"]] = {}
"""name → BaseRedisPlugin 子类映射。name → BaseRedisPlugin subclass mapping."""


def _register_redis_plugin(cls: Type["BaseRedisPlugin"]) -> None:
    """注册 BaseRedisPlugin 子类并自动创建 Pre/Post 包装类。
    Register a BaseRedisPlugin subclass and auto-create Pre/Post wrapper classes.
    """
    _create_external_plugin_wrappers(cls, _REDIS_PLUGIN_REGISTRY)


# ============================================================================
# BaseRedisPlugin — 用户继承的基类 / Base class for user implementations
# ============================================================================

class BaseRedisPlugin(ABC):
    """Redis 操作基类 — 管理连接，暴露 before_request / after_response 扩展点。
    Redis operation base — manages connections, exposes before/after extension points.

    用户只需定义 ``name`` 类属性，实现 ``before_request`` / ``after_response``。
    ``__init_subclass__`` 自动创建并注册 PreProcessor / PostProcessor 包装类。

    Users only need to define ``name`` and implement ``before_request`` /
    ``after_response``. ``__init_subclass__`` auto-creates and registers
    PreProcessor / PostProcessor wrappers.

    用法示例 / Usage::

        class CacheHandlerPlugin(BaseRedisPlugin):
            name = "cache-handler"

            def before_request(self, headers, body, case_config, global_config):
                client = self._get_client(global_config)
                client.set("test:key", "value", ex=3600)
                return headers, body

            def after_response(self, request_headers, request_body,
                               response_headers, response_body, case_config,
                               global_config):
                client = self._get_client(global_config)
                client.delete("test:key")

    用例 YAML / Test case YAML::

        preprocessors:
          - name: cache-handler
            config: {}
        postprocessors:
          - name: cache-handler
            config: {}
    """

    name: str  # 子类必须定义 / Must be defined on each subclass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _register_redis_plugin(cls)

    # ── 连接管理 / Connection management ─────────────────────────────────

    def _get_client(self, global_config: Dict[str, Any]):
        """获取 Redis 客户端（从连接池中）。
        Get a Redis client from the connection pool.

        配置读取路径 / Config read path:
        ``global_config["processor_configs"][self.name]["redis_url"]``

        redis-py 客户端自带连接池，线程安全，不需要手动归还。
        redis-py client has built-in connection pooling, thread-safe, no manual return needed.
        """
        proc_configs = global_config.get("processor_configs", {})
        if not isinstance(proc_configs, dict):
            raise RedisConnectionError(
                "global_config['processor_configs'] is missing or not a dict",
                processor_name=self.name,
            )
        processor_cfg = proc_configs.get(self.name, {})
        if not isinstance(processor_cfg, dict):
            raise RedisConnectionError(
                f"processor_configs['{self.name}'] is missing or not a dict",
                processor_name=self.name,
            )
        redis_url = processor_cfg.get("redis_url", "")
        if not redis_url:
            raise RedisConnectionError(
                f"processor_configs['{self.name}'].redis_url is not set. "
                "Please configure the Redis connection URL in env.yml, e.g.:\n"
                f"processor_configs:\n  {self.name}:\n"
                '    redis_url: "redis://localhost:6379/0"',
                processor_name=self.name,
            )

        return _RedisConnectionManager.get_client(redis_url)

    # ── 扩展点 / Extension points ────────────────────────────────────────

    def can_process(self, case: Dict[str, Any]) -> bool:
        """是否对当前用例执行处理器。默认总是执行。
        Whether to process this case. Default: always True.
        子类可覆写以按条件跳过。Subclasses may override for conditional skip."""
        return True

    def before_request(
        self,
        headers: Dict[str, Any],
        body: Dict[str, Any],
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """请求前 Redis 操作（前置处理器）。
        Pre-request Redis operation (pre-processor).

        默认直接返回 headers, body 不做修改。子类按需覆写。
        Default: return headers, body unchanged. Override as needed.
        """
        return headers, body

    def after_response(
        self,
        request_headers: Dict[str, Any],
        request_body: Dict[str, Any],
        response_headers: Dict[str, Any],
        response_body: Any,
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> None:
        """响应后 Redis 操作（后置处理器）。
        Post-response Redis operation (post-processor).

        默认 no-op。子类按需覆写。
        Default: no-op. Override as needed.
        """
        pass
