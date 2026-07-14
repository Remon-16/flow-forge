"""MQ 处理器基类 — 提供连接管理、消息发布/消费、自动注册。
MQ processor base — connection management, message publish/consume, auto-registration.

基于 Kombu 实现多 MQ 抽象（类似 SQLAlchemy 对数据库的作用），
一个 ``mq_url`` 连接字符串即可切换 RabbitMQ / Redis / Amazon SQS / MongoDB 等。

Built on Kombu for multi-MQ abstraction (like SQLAlchemy for databases).
A single ``mq_url`` connection string switches between RabbitMQ, Redis, SQS, MongoDB, etc.

用户只需继承 ``BaseMQPlugin``，实现 ``before_request`` / ``after_response``。
Users extend ``BaseMQPlugin``, implement ``before_request`` / ``after_response``.

支持的协议 / Supported protocols:
- ``amqp://`` — RabbitMQ
- ``redis://`` — Redis (as broker)
- ``sqs://`` — Amazon SQS
- ``mongodb://`` — MongoDB
- ``memory://`` — 测试用 / for testing (no external service needed)
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
# Kombu 延迟导入 / Lazy import — only when an MQ processor is triggered
# ============================================================================
_KOMBU_AVAILABLE = False
_kombu_module = None


def _ensure_kombu():
    """确保 Kombu 可用，否则给出友好错误提示。
    Ensure Kombu is importable; raise with install hint otherwise."""
    global _KOMBU_AVAILABLE, _kombu_module
    if _KOMBU_AVAILABLE:
        return
    try:
        import kombu as _k
        _kombu_module = _k
        _KOMBU_AVAILABLE = True
    except ImportError:
        raise ProcessorError(
            "Kombu is required for MQ processors. "
            "Install it with: pip install kombu\n"
            "Kombu supports RabbitMQ, Redis, Amazon SQS, MongoDB, and more.",
            processor_name="mq",
        )


# ============================================================================
# 自定义异常 / Custom exceptions
# ============================================================================

class MQConnectionError(ProcessorError):
    """MQ 连接失败。MQ connection failure."""


class MQPublishError(ProcessorError):
    """MQ 消息发布失败。MQ message publish failure."""


# ============================================================================
# MQ 连接管理器 — 单例、懒加载、按 mq_url 缓存 / Connection manager
# ============================================================================

class _MQConnectionManager:
    """MQ 连接管理器（线程安全）。
    MQ connection manager (thread-safe).

    相同 ``mq_url`` 的多个处理器共享同一个 kombu.Connection。
    Multiple processors with the same ``mq_url`` share one kombu.Connection.
    """

    _connections: Dict[str, Any] = {}
    _lock = threading.Lock()

    @classmethod
    def get_connection(cls, mq_url: str):
        """获取或创建 kombu.Connection。Get or create a kombu.Connection for the given URL.

        懒加载：首次调用时才创建连接。
        Lazy: Connection is created on first access.
        """
        _ensure_kombu()
        with cls._lock:
            if mq_url not in cls._connections:
                cls._connections[mq_url] = _kombu_module.Connection(mq_url)
                safe_url = _mask_password(mq_url)
                logger.info("MQ Connection created for: %s", safe_url)
        return cls._connections[mq_url]


# ============================================================================
# MQ 插件注册表 / MQ plugin registry
# ============================================================================

_MQ_PLUGIN_REGISTRY: Dict[str, Type["BaseMQPlugin"]] = {}
"""name → BaseMQPlugin 子类映射。name → BaseMQPlugin subclass mapping."""


def _register_mq_plugin(cls: Type["BaseMQPlugin"]) -> None:
    """注册 BaseMQPlugin 子类并自动创建 Pre/Post 包装类。
    Register a BaseMQPlugin subclass and auto-create Pre/Post wrapper classes.
    """
    _create_external_plugin_wrappers(cls, _MQ_PLUGIN_REGISTRY)


# ============================================================================
# BaseMQPlugin — 用户继承的基类 / Base class for user implementations
# ============================================================================

class BaseMQPlugin(ABC):
    """MQ 操作基类 — 管理连接，暴露 before_request / after_response 扩展点。
    MQ operation base — manages connections, exposes before/after extension points.

    用户只需定义 ``name`` 类属性，实现 ``before_request`` / ``after_response``。
    ``__init_subclass__`` 自动创建并注册 PreProcessor / PostProcessor 包装类。

    Users only need to define ``name`` and implement ``before_request`` /
    ``after_response``. ``__init_subclass__`` auto-creates and registers
    PreProcessor / PostProcessor wrappers.

    用法示例 / Usage::

        class OrderPublishPlugin(BaseMQPlugin):
            name = "order-publish"

            def before_request(self, headers, body, case_config, global_config):
                self._publish("order.create", body, global_config)
                return headers, body

            def after_response(self, request_headers, request_body,
                               response_headers, response_body, case_config,
                               global_config):
                msg = self._get_message("order.create", timeout=5, global_config=global_config)
                if msg:
                    print("Consumed:", msg)

    用例 YAML / Test case YAML::

        preprocessors:
          - name: order-publish
            config: {}
        postprocessors:
          - name: order-publish
            config: {}
    """

    name: str  # 子类必须定义 / Must be defined on each subclass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _register_mq_plugin(cls)

    # ── 连接管理 / Connection management ─────────────────────────────────

    def _get_connection(self, global_config: Dict[str, Any]):
        """获取 MQ 连接。Get an MQ connection.

        配置读取路径 / Config read path:
        ``global_config["processor_configs"][self.name]["mq_url"]``

        返回的 Connection 自带连接池，线程安全。
        The returned Connection has built-in pooling, thread-safe.
        """
        proc_configs = global_config.get("processor_configs", {})
        if not isinstance(proc_configs, dict):
            raise MQConnectionError(
                "global_config['processor_configs'] is missing or not a dict",
                processor_name=self.name,
            )
        processor_cfg = proc_configs.get(self.name, {})
        if not isinstance(processor_cfg, dict):
            raise MQConnectionError(
                f"processor_configs['{self.name}'] is missing or not a dict",
                processor_name=self.name,
            )
        mq_url = processor_cfg.get("mq_url", "")
        if not mq_url:
            raise MQConnectionError(
                f"processor_configs['{self.name}'].mq_url is not set. "
                "Please configure the MQ connection URL in env.yml, e.g.:\n"
                f"processor_configs:\n  {self.name}:\n"
                '    mq_url: "amqp://guest:guest@localhost:5672//"\n'
                "Supported protocols: amqp:// (RabbitMQ), redis:// (Redis), "
                "sqs:// (Amazon SQS), mongodb:// (MongoDB), memory:// (testing)",
                processor_name=self.name,
            )

        return _MQConnectionManager.get_connection(mq_url)

    # ── 便捷方法 / Convenience methods ────────────────────────────────────

    def _publish(
        self,
        queue_name: str,
        body: Any,
        routing_key: str = "",
        exchange_name: str = "",
        global_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """发布消息到指定队列。Publish a message to the specified queue.

        Args:
            queue_name: 队列名称 / Queue name.
            body: 消息体（自动 JSON 序列化）/ Message body (auto JSON serialized).
            routing_key: 路由键（默认使用 queue_name）/ Routing key (defaults to queue_name).
            exchange_name: 交换机名称（空字符串 = 默认交换机）/ Exchange name (empty = default exchange).
            global_config: 全局配置（用于获取连接）/ Global config (for getting connection).
        """
        if global_config is None:
            raise MQPublishError(
                "global_config is required for _publish()",
                processor_name=self.name,
            )
        conn = self._get_connection(global_config)
        routing_key = routing_key or queue_name

        with _kombu_module.Producer(conn) as producer:
            producer.publish(
                body,
                exchange=exchange_name or "",
                routing_key=routing_key,
                serializer="json",
                declare=[_kombu_module.Queue(
                    queue_name,
                    exchange=_kombu_module.Exchange(exchange_name or "", "direct"),
                    routing_key=routing_key,
                )],
            )

    def _get_message(
        self,
        queue_name: str,
        timeout: float = 5.0,
        global_config: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """从指定队列获取消息。Get a message from the specified queue.

        Args:
            queue_name: 队列名称 / Queue name.
            timeout: 等待超时（秒）/ Wait timeout in seconds.
            global_config: 全局配置 / Global config.

        Returns:
            消息体（已 JSON 反序列化），超时返回 None。
            Message body (JSON deserialized), or None on timeout.
        """
        if global_config is None:
            raise MQConnectionError(
                "global_config is required for _get_message()",
                processor_name=self.name,
            )
        conn = self._get_connection(global_config)

        try:
            queue = conn.SimpleQueue(queue_name)
            message = queue.get(block=True, timeout=timeout)
            message.ack()
            return message.payload
        except Exception:
            return None

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
        """请求前 MQ 操作（前置处理器）。
        Pre-request MQ operation (pre-processor).

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
        """响应后 MQ 操作（后置处理器）。
        Post-response MQ operation (post-processor).

        默认 no-op。子类按需覆写。
        Default: no-op. Override as needed.
        """
        pass
