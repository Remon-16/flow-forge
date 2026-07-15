"""Pulsar 处理器基类 — 提供连接管理、消息发送、自动注册。
Pulsar processor base — connection management, message sending, auto-registration.

Apache Pulsar 在国内是主流 MQ，因其协议与 AMQP 不同（Kombu 不支持），
故单独创建此模块。使用 ``pulsar-client`` 官方客户端。

Apache Pulsar is widely used in China. Since its protocol differs from
AMQP (not supported by Kombu), this module is created separately.
Uses the ``pulsar-client`` official client.

用户只需继承 ``BasePulsarPlugin``，实现 ``before_request`` / ``after_response``。
Users extend ``BasePulsarPlugin``, implement ``before_request`` / ``after_response``.
"""

import logging
import threading
from typing import Any, Dict, Optional, Tuple, Type

from processors.base import (
    BaseExternalPlugin,
    ProcessorError,
    _create_external_plugin_wrappers,
    _mask_password,
)

logger = logging.getLogger(__name__)

# ============================================================================
# pulsar-client 延迟导入 / Lazy import — only when a Pulsar processor is triggered
# ============================================================================
_PULSAR_AVAILABLE = False
_pulsar_module = None


def _ensure_pulsar_client():
    """确保 pulsar-client 可用，否则给出友好错误提示。
    Ensure pulsar-client is importable; raise with install hint otherwise."""
    global _PULSAR_AVAILABLE, _pulsar_module
    if _PULSAR_AVAILABLE:
        return
    try:
        import pulsar as _ps
        _pulsar_module = _ps
        _PULSAR_AVAILABLE = True
    except ImportError:
        raise ProcessorError(
            "pulsar-client is required for Pulsar processors. "
            "Install it with: pip install pulsar-client\n"
            "pulsar-client is the official Apache Pulsar Python client.",
            processor_name="pulsar",
        )


# ============================================================================
# 自定义异常 / Custom exceptions
# ============================================================================

class PulsarConnectionError(ProcessorError):
    """Pulsar 连接失败。Pulsar connection failure."""


class PulsarPublishError(ProcessorError):
    """Pulsar 消息发送失败。Pulsar message send failure."""


# ============================================================================
# Pulsar Client 管理器 — 单例、懒加载、按 service_url 缓存
# ============================================================================

class _PulsarClientManager:
    """Pulsar Client 管理器（线程安全）。
    Pulsar Client manager (thread-safe).

    相同 ``service_url`` 的多个处理器共享同一个 Client 实例。
    Multiple processors with the same ``service_url`` share one Client.
    """

    _clients: Dict[str, Any] = {}
    _lock = threading.Lock()

    @classmethod
    def get_client(cls, service_url: str):
        """获取或创建 Pulsar Client 实例。Get or create a Pulsar Client instance.

        懒加载：首次调用时才创建 Client。
        Lazy: Client is created on first access.
        """
        _ensure_pulsar_client()
        with cls._lock:
            if service_url not in cls._clients:
                client = _pulsar_module.Client(service_url)
                cls._clients[service_url] = client
                safe_url = _mask_password(service_url)
                logger.info("Pulsar Client created for: %s", safe_url)
        return cls._clients[service_url]


# ============================================================================
# Pulsar 插件注册表 / Pulsar plugin registry
# ============================================================================

_PULSAR_PLUGIN_REGISTRY: Dict[str, Type["BasePulsarPlugin"]] = {}
"""name → BasePulsarPlugin 子类映射。name → BasePulsarPlugin subclass mapping."""


def _register_pulsar_plugin(cls: Type["BasePulsarPlugin"]) -> None:
    """注册 BasePulsarPlugin 子类并自动创建 Pre/Post 包装类。
    Register a BasePulsarPlugin subclass and auto-create Pre/Post wrapper classes.
    """
    _create_external_plugin_wrappers(cls, _PULSAR_PLUGIN_REGISTRY)


# ============================================================================
# BasePulsarPlugin — 用户继承的基类 / Base class for user implementations
# ============================================================================

class BasePulsarPlugin(BaseExternalPlugin):
    """Pulsar 操作基类 — 管理连接，暴露 before_request / after_response 扩展点。
    Pulsar operation base — manages connections, exposes before/after extension points.

    扩展点方法（can_process / before_request / after_response）继承自
    BaseExternalPlugin，默认 no-op。子类按需覆写。
    Extension point methods (can_process / before_request / after_response)
    are inherited from BaseExternalPlugin with default no-op implementations.
    Subclasses override as needed.

    用户只需定义 ``name`` 类属性，实现 ``before_request`` / ``after_response``。
    ``__init_subclass__`` 自动创建并注册 PreProcessor / PostProcessor 包装类。

    Users only need to define ``name`` and implement ``before_request`` /
    ``after_response``. ``__init_subclass__`` auto-creates and registers
    PreProcessor / PostProcessor wrappers.

    用法示例 / Usage::

        class PulsarOrderPlugin(BasePulsarPlugin):
            name = "pulsar-order-event"

            def before_request(self, headers, body, case_config, global_config):
                self._send_message("order-topic", body, global_config=global_config)
                return headers, body

            def after_response(self, request_headers, request_body,
                               response_headers, response_body, case_config,
                               global_config):
                print(f"[pulsar-order-event] Message sent to Pulsar successfully")

    环境配置 / Env config (env-local.yml)::

        processor_configs:
          pulsar-order-event:
            service_url: "pulsar://localhost:6650"
            topic: "order-topic"

    用例 YAML / Test case YAML::

        preprocessors:
          - name: pulsar-order-event
            config: {}
    """

    name: str  # 子类必须定义 / Must be defined on each subclass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _register_pulsar_plugin(cls)

    # ── 连接管理 / Connection management ─────────────────────────────────

    def _get_client(self, global_config: Dict[str, Any]):
        """获取 Pulsar Client 实例。Get a Pulsar Client instance.

        配置读取路径 / Config read path:
        ``global_config["processor_configs"][self.name].service_url``

        Pulsar Client 是线程安全的，可跨线程共享。
        Pulsar Client is thread-safe and can be shared across threads.
        """
        proc_configs = global_config.get("processor_configs", {})
        if not isinstance(proc_configs, dict):
            raise PulsarConnectionError(
                "global_config['processor_configs'] is missing or not a dict",
                processor_name=self.name,
            )
        processor_cfg = proc_configs.get(self.name, {})
        if not isinstance(processor_cfg, dict):
            raise PulsarConnectionError(
                f"processor_configs['{self.name}'] is missing or not a dict",
                processor_name=self.name,
            )
        service_url = processor_cfg.get("service_url", "")
        if not service_url:
            raise PulsarConnectionError(
                f"processor_configs['{self.name}'].service_url is not set. "
                "Please configure the Pulsar service URL in env.yml, e.g.:\n"
                f"processor_configs:\n  {self.name}:\n"
                '    service_url: "pulsar://localhost:6650"\n'
                '    topic: "order-topic"',
                processor_name=self.name,
            )

        return _PulsarClientManager.get_client(service_url)

    # ── 便捷方法 / Convenience methods ────────────────────────────────────

    def _send_message(
        self,
        topic: str,
        body: Any,
        properties: Optional[Dict[str, str]] = None,
        global_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """发送消息到 Pulsar topic。Send a message to a Pulsar topic.

        创建 Producer → send → close，确保消息已提交。
        Create Producer → send → close to ensure message is committed.

        Args:
            topic: 主题名称 / Topic name.
            body: 消息体（自动 JSON 序列化）/ Message body (auto JSON serialized).
            properties: 消息属性（可选）/ Message properties (optional).
            global_config: 全局配置 / Global config.
        """
        if global_config is None:
            raise PulsarPublishError(
                "global_config is required for _send_message()",
                processor_name=self.name,
            )
        import json

        client = self._get_client(global_config)
        msg_body = json.dumps(body, ensure_ascii=False)

        producer = client.create_producer(topic)
        try:
            producer.send(
                msg_body.encode("utf-8"),
                properties=properties,
            )
        finally:
            producer.close()

        logger.info("Pulsar message sent to topic '%s'", topic)
