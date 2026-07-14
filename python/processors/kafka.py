"""Kafka 处理器基类 — 提供连接管理、消息发送、自动注册。
Kafka processor base — connection management, message sending, auto-registration.

Apache Kafka 在国内是主流 MQ，因其协议与 AMQP 不同（Kombu 不支持），
故单独创建此模块。使用 ``confluent-kafka`` 官方客户端。

Apache Kafka is widely used in China. Since its protocol differs from
AMQP (not supported by Kombu), this module is created separately.
Uses the ``confluent-kafka`` official client.

用户只需继承 ``BaseKafkaPlugin``，实现 ``before_request`` / ``after_response``。
Users extend ``BaseKafkaPlugin``, implement ``before_request`` / ``after_response``.
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
# confluent-kafka 延迟导入 / Lazy import — only when a Kafka processor is triggered
# ============================================================================
_KAFKA_AVAILABLE = False
_confluent_kafka_module = None


def _ensure_confluent_kafka():
    """确保 confluent-kafka 可用，否则给出友好错误提示。
    Ensure confluent-kafka is importable; raise with install hint otherwise."""
    global _KAFKA_AVAILABLE, _confluent_kafka_module
    if _KAFKA_AVAILABLE:
        return
    try:
        import confluent_kafka as _ck
        _confluent_kafka_module = _ck
        _KAFKA_AVAILABLE = True
    except ImportError:
        raise ProcessorError(
            "confluent-kafka is required for Kafka processors. "
            "Install it with: pip install confluent-kafka\n"
            "confluent-kafka is the official Confluent Python client for Apache Kafka.",
            processor_name="kafka",
        )


# ============================================================================
# 自定义异常 / Custom exceptions
# ============================================================================

class KafkaConnectionError(ProcessorError):
    """Kafka 连接失败。Kafka connection failure."""


class KafkaPublishError(ProcessorError):
    """Kafka 消息发送失败。Kafka message publish failure."""


# ============================================================================
# Kafka Producer 管理器 — 单例、懒加载、按 (bootstrap_servers, client_id) 缓存
# ============================================================================

class _KafkaProducerManager:
    """Kafka Producer 管理器（线程安全）。
    Kafka Producer manager (thread-safe).

    相同 ``(bootstrap_servers, client_id)`` 的多个处理器共享同一个 Producer 实例。
    Multiple processors with the same ``(bootstrap_servers, client_id)`` share one Producer.
    """

    _producers: Dict[str, Any] = {}
    _lock = threading.Lock()

    @classmethod
    def _make_key(cls, bootstrap_servers: str, client_id: str) -> str:
        return f"{bootstrap_servers}|{client_id}"

    @classmethod
    def get_producer(cls, bootstrap_servers: str, client_id: str = "flow-forge"):
        """获取或创建 Producer 实例。Get or create a Producer instance.

        懒加载：首次调用时才创建 Producer。
        Lazy: Producer is created on first access.
        """
        _ensure_confluent_kafka()
        key = cls._make_key(bootstrap_servers, client_id)
        with cls._lock:
            if key not in cls._producers:
                producer = _confluent_kafka_module.Producer({
                    "bootstrap.servers": bootstrap_servers,
                    "client.id": client_id,
                })
                cls._producers[key] = producer
                safe_servers = _mask_password(bootstrap_servers)
                logger.info(
                    "Kafka Producer created — bootstrap_servers=%s, client_id=%s",
                    safe_servers, client_id,
                )
        return cls._producers[key]


# ============================================================================
# Kafka 插件注册表 / Kafka plugin registry
# ============================================================================

_KAFKA_PLUGIN_REGISTRY: Dict[str, Type["BaseKafkaPlugin"]] = {}
"""name → BaseKafkaPlugin 子类映射。name → BaseKafkaPlugin subclass mapping."""


def _register_kafka_plugin(cls: Type["BaseKafkaPlugin"]) -> None:
    """注册 BaseKafkaPlugin 子类并自动创建 Pre/Post 包装类。
    Register a BaseKafkaPlugin subclass and auto-create Pre/Post wrapper classes.
    """
    _create_external_plugin_wrappers(cls, _KAFKA_PLUGIN_REGISTRY)


# ============================================================================
# BaseKafkaPlugin — 用户继承的基类 / Base class for user implementations
# ============================================================================

class BaseKafkaPlugin(ABC):
    """Kafka 操作基类 — 管理连接，暴露 before_request / after_response 扩展点。
    Kafka operation base — manages connections, exposes before/after extension points.

    用户只需定义 ``name`` 类属性，实现 ``before_request`` / ``after_response``。
    ``__init_subclass__`` 自动创建并注册 PreProcessor / PostProcessor 包装类。

    Users only need to define ``name`` and implement ``before_request`` /
    ``after_response``. ``__init_subclass__`` auto-creates and registers
    PreProcessor / PostProcessor wrappers.

    用法示例 / Usage::

        class KafkaOrderPlugin(BaseKafkaPlugin):
            name = "kafka-order-event"

            def before_request(self, headers, body, case_config, global_config):
                self._send_message("order-topic", body, global_config=global_config)
                return headers, body

            def after_response(self, request_headers, request_body,
                               response_headers, response_body, case_config,
                               global_config):
                print(f"[kafka-order-event] Message sent to Kafka successfully")

    环境配置 / Env config (env-local.yml)::

        processor_configs:
          kafka-order-event:
            bootstrap_servers: "localhost:9092"
            topic: "order-topic"

    用例 YAML / Test case YAML::

        preprocessors:
          - name: kafka-order-event
            config: {}
    """

    name: str  # 子类必须定义 / Must be defined on each subclass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _register_kafka_plugin(cls)

    # ── 连接管理 / Connection management ─────────────────────────────────

    def _get_producer(self, global_config: Dict[str, Any]):
        """获取 Kafka Producer 实例。Get a Kafka Producer instance.

        配置读取路径 / Config read path:
        ``global_config["processor_configs"][self.name].bootstrap_servers``
        ``global_config["processor_configs"][self.name].client_id``（可选 / optional）

        confluent-kafka Producer 内部线程安全，可跨线程共享。
        confluent-kafka Producer is internally thread-safe and can be shared across threads.
        """
        proc_configs = global_config.get("processor_configs", {})
        if not isinstance(proc_configs, dict):
            raise KafkaConnectionError(
                "global_config['processor_configs'] is missing or not a dict",
                processor_name=self.name,
            )
        processor_cfg = proc_configs.get(self.name, {})
        if not isinstance(processor_cfg, dict):
            raise KafkaConnectionError(
                f"processor_configs['{self.name}'] is missing or not a dict",
                processor_name=self.name,
            )
        bootstrap_servers = processor_cfg.get("bootstrap_servers", "")
        if not bootstrap_servers:
            raise KafkaConnectionError(
                f"processor_configs['{self.name}'].bootstrap_servers is not set. "
                "Please configure the Kafka bootstrap servers in env.yml, e.g.:\n"
                f"processor_configs:\n  {self.name}:\n"
                '    bootstrap_servers: "localhost:9092"\n'
                '    topic: "order-topic"',
                processor_name=self.name,
            )

        client_id = processor_cfg.get("client_id", "flow-forge")
        return _KafkaProducerManager.get_producer(bootstrap_servers, client_id)

    # ── 便捷方法 / Convenience methods ────────────────────────────────────

    def _send_message(
        self,
        topic: str,
        body: Any,
        key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        global_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """发送消息到 Kafka topic。Send a message to a Kafka topic.

        使用 ``producer.produce()`` + ``producer.flush()`` 同步发送。
        Uses ``producer.produce()`` + ``producer.flush()`` for synchronous send.

        Args:
            topic: 主题名称 / Topic name.
            body: 消息体（自动 JSON 序列化）/ Message body (auto JSON serialized).
            key: 消息键（用于分区路由，可选）/ Message key (for partition routing, optional).
            headers: 消息头（可选）/ Message headers (optional).
            global_config: 全局配置 / Global config.
        """
        if global_config is None:
            raise KafkaPublishError(
                "global_config is required for _send_message()",
                processor_name=self.name,
            )
        import json

        producer = self._get_producer(global_config)
        msg_body = json.dumps(body, ensure_ascii=False)

        # 构建 headers 为 confluent-kafka 需要的格式（list of (str, bytes) tuples）
        # Build headers in confluent-kafka format (list of (str, bytes) tuples)
        kafka_headers = None
        if headers:
            kafka_headers = [
                (k, v.encode("utf-8") if isinstance(v, str) else v)
                for k, v in headers.items()
            ]

        producer.produce(
            topic=topic,
            value=msg_body.encode("utf-8"),
            key=key.encode("utf-8") if key else None,
            headers=kafka_headers,
        )
        # 同步等待消息发送完成 / Synchronously wait for message delivery
        producer.flush()
        logger.info("Kafka message sent to topic '%s' (key=%s)", topic, key)

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
        """请求前 Kafka 操作（前置处理器）。
        Pre-request Kafka operation (pre-processor).

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
        """响应后 Kafka 操作（后置处理器）。
        Post-response Kafka operation (post-processor).

        默认 no-op。Kafka 消费由独立消费者服务处理，后置通常只做日志记录。
        Default: no-op. Kafka consumption is handled by dedicated consumer services;
        post-processing typically only logs confirmation.
        """
        pass
