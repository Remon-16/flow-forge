"""RocketMQ 处理器基类 — 基于内置纯 Python 客户端（跨平台）。
RocketMQ processor base — built on the built-in pure-Python client (cross-platform).

官方 ``rocketmq-client-python`` 不支持 Windows，因此本模块使用
``processors.rocketmq_client`` 中基于 remoting 协议实现的纯 Python 客户端，
在 Windows/Linux/macOS 上均可收发消息，无第三方原生依赖。

The official ``rocketmq-client-python`` does not support Windows, so this module
uses the pure-Python client in ``processors.rocketmq_client`` (implemented over
the remoting protocol) to send and receive messages on Windows/Linux/macOS
without third-party native dependencies.

用户只需继承 ``BaseRocketMQPlugin``，实现 ``before_request`` / ``after_response``。
Users extend ``BaseRocketMQPlugin`` and implement ``before_request`` /
``after_response``.
"""

import json
import logging
import threading
from typing import Any, Dict, Optional, Tuple, Type

from i18n import _
from processors.base import (
    BaseExternalPlugin,
    ProcessorError,
    _create_external_plugin_wrappers,
)
from processors.rocketmq_client import RocketMQClient

logger = logging.getLogger(__name__)


# ============================================================================
# 自定义异常 / Custom exceptions
# ============================================================================

class RocketMQConnectionError(ProcessorError):
    """RocketMQ 连接/配置失败。RocketMQ connection or configuration failure."""


class RocketMQPublishError(ProcessorError):
    """RocketMQ 消息发送失败。RocketMQ message send failure."""


class RocketMQReceiveError(ProcessorError):
    """RocketMQ 消息消费失败。RocketMQ message receive failure."""


# ============================================================================
# 客户端管理器 — 按 namesrv_addr 缓存，线程安全 / Client manager cached by address
# ============================================================================

class _RocketMQManager:
    """RocketMQ 客户端管理器（线程安全）。
    RocketMQ client manager (thread-safe)."""

    _clients: Dict[str, RocketMQClient] = {}
    _lock = threading.Lock()

    @classmethod
    def get_client(cls, namesrv_addr: str) -> RocketMQClient:
        """获取或创建客户端。Get or create a client."""
        with cls._lock:
            if namesrv_addr not in cls._clients:
                cls._clients[namesrv_addr] = RocketMQClient(namesrv_addr)
        return cls._clients[namesrv_addr]


# ============================================================================
# 插件注册表 / Plugin registry
# ============================================================================

_ROCKETMQ_PLUGIN_REGISTRY: Dict[str, Type["BaseRocketMQPlugin"]] = {}
"""name → BaseRocketMQPlugin 子类映射。name → BaseRocketMQPlugin subclass mapping."""


def _register_rocketmq_plugin(cls: Type["BaseRocketMQPlugin"]) -> None:
    """注册 BaseRocketMQPlugin 子类并自动创建 Pre/Post 包装类。
    Register a BaseRocketMQPlugin subclass and auto-create Pre/Post wrapper classes."""
    _create_external_plugin_wrappers(cls, _ROCKETMQ_PLUGIN_REGISTRY)


# ============================================================================
# BaseRocketMQPlugin — 用户继承的基类 / Base class for user implementations
# ============================================================================

class BaseRocketMQPlugin(BaseExternalPlugin):
    """RocketMQ 操作基类 — 管理客户端，暴露 before_request / after_response 扩展点。
    RocketMQ operation base — manages the client, exposes before_request /
    after_response extension points."""

    name: str  # 子类必须定义 / Must be defined on each subclass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _register_rocketmq_plugin(cls)

    # ── 配置与客户端 / Config and client ─────────────────────────────────

    def _get_config(self, global_config: Dict[str, Any]) -> Dict[str, Any]:
        """读取当前插件的处理器配置。Read the processor config for this plugin."""
        proc_configs = global_config.get("processor_configs", {})
        if not isinstance(proc_configs, dict):
            raise RocketMQConnectionError(
                _("rocketmq.global_config_required"),
                processor_name=self.name,
            )
        cfg = proc_configs.get(self.name, {})
        if not isinstance(cfg, dict):
            raise RocketMQConnectionError(
                _("rocketmq.config_not_dict", name=self.name),
                processor_name=self.name,
            )
        return cfg

    def _get_client(self, global_config: Dict[str, Any]) -> RocketMQClient:
        """获取 RocketMQ 客户端。Get the RocketMQ client."""
        cfg = self._get_config(global_config)
        namesrv_addr = cfg.get("namesrv_addr", "")
        if not namesrv_addr:
            raise RocketMQConnectionError(
                _("rocketmq.namesrv_missing", name=self.name),
                processor_name=self.name,
            )
        return _RocketMQManager.get_client(namesrv_addr)

    def _get_group(self, global_config: Dict[str, Any]) -> str:
        """获取生产者组。Get the producer group."""
        cfg = self._get_config(global_config)
        group_id = cfg.get("group_id", "")
        if not group_id:
            raise RocketMQConnectionError(
                _("rocketmq.group_missing", name=self.name),
                processor_name=self.name,
            )
        return group_id

    # ── 便捷方法 / Convenience methods ────────────────────────────────────

    def _send_message(
        self,
        topic: str,
        body: Any,
        tag: str = "",
        key: str = "",
        global_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """发送消息，返回 {broker_addr, queue_id, queue_offset, msg_id}。
        Send a message; returns {broker_addr, queue_id, queue_offset, msg_id}."""
        if global_config is None:
            raise RocketMQPublishError(
                _("rocketmq.global_config_required"),
                processor_name=self.name,
            )
        client = self._get_client(global_config)
        group = self._get_group(global_config)
        msg_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        return client.send_message(
            topic=topic,
            body=msg_body,
            tags=tag,
            keys=key,
            group=group,
        )

    def _receive_message(
        self,
        topic: str,
        queue_id: int,
        queue_offset: int,
        broker_addr: Optional[str] = None,
        tag: str = "",
        timeout: float = 10.0,
        global_config: Optional[Dict[str, Any]] = None,
    ):
        """从指定队列偏移消费消息（使用独立的 verify 消费组）。
        Consume from the given queue offset (using a dedicated verify group)."""
        if global_config is None:
            raise RocketMQReceiveError(
                _("rocketmq.global_config_required"),
                processor_name=self.name,
            )
        client = self._get_client(global_config)
        group = self._get_group(global_config)
        return client.receive_message(
            topic=topic,
            group="%s-verify" % group,
            queue_id=queue_id,
            offset=queue_offset,
            broker_addr=broker_addr,
            tags=tag,
            timeout=timeout,
        )
