"""RocketMQ 处理器基类 — 提供连接管理、消息发送、自动注册。
RocketMQ processor base — connection management, message sending, auto-registration.

Apache RocketMQ 在国内是主流 MQ，因其协议与 AMQP/Redis 不同（Kombu 不支持），
故单独创建此模块。使用 ``rocketmq-client-python`` 官方客户端。

Apache RocketMQ is widely used in China. Since its protocol differs from
AMQP/Redis (not supported by Kombu), this module is created separately.
Uses the ``rocketmq-client-python`` official client.

注意 / Note:
    ``rocketmq-client-python`` 基于 C++ 扩展，安装可能需要编译环境。
    对于纯 Python 环境，建议使用 Docker 部署 RocketMQ + Name Server。
    ``rocketmq-client-python`` is a C++ extension; installation may require
    build tools. For pure Python environments, consider Docker for RocketMQ.
"""

import logging
import threading
from abc import ABC
from typing import Any, Dict, Optional, Tuple, Type

from processors.base import (
    ProcessorError,
    _create_external_plugin_wrappers,
)

logger = logging.getLogger(__name__)

# ============================================================================
# rocketmq-client-python 延迟导入 / Lazy import
# ============================================================================
_ROCKETMQ_AVAILABLE = False
_rocketmq_client = None
_rocketmq_message = None


def _ensure_rocketmq():
    """确保 rocketmq-client-python 可用，否则给出友好错误提示。
    Ensure rocketmq-client-python is importable; raise with install hint otherwise."""
    global _ROCKETMQ_AVAILABLE, _rocketmq_client, _rocketmq_message
    if _ROCKETMQ_AVAILABLE:
        return
    try:
        from rocketmq.client import Producer, Message as RMessage, SendStatus
        _rocketmq_client = type("_client", (), {
            "Producer": Producer,
            "SendStatus": SendStatus,
        })
        _rocketmq_message = RMessage
        _ROCKETMQ_AVAILABLE = True
    except ImportError:
        raise ProcessorError(
            "rocketmq-client-python is required for RocketMQ processors. "
            "Install it with: pip install rocketmq-client-python\n"
            "Note: this package requires a C++ build environment.\n"
            "For Docker-based RocketMQ, see: https://rocketmq.apache.org/",
            processor_name="rocketmq",
        )


# ============================================================================
# 自定义异常 / Custom exceptions
# ============================================================================

class RocketMQConnectionError(ProcessorError):
    """RocketMQ 连接失败。RocketMQ connection failure."""


class RocketMQPublishError(ProcessorError):
    """RocketMQ 消息发送失败。RocketMQ message send failure."""


# ============================================================================
# RocketMQ Producer 管理器 — 单例、懒加载、按 namesrv_addr 缓存
# ============================================================================

class _RocketMQManager:
    """RocketMQ Producer 管理器（线程安全）。
    RocketMQ Producer manager (thread-safe).

    相同 ``(namesrv_addr, group_id)`` 的多个处理器共享同一个 Producer 实例。
    Multiple processors with the same ``(namesrv_addr, group_id)`` share one Producer.
    """

    _producers: Dict[str, Any] = {}
    _lock = threading.Lock()

    @classmethod
    def _make_key(cls, namesrv_addr: str, group_id: str) -> str:
        return f"{namesrv_addr}|{group_id}"

    @classmethod
    def get_producer(cls, namesrv_addr: str, group_id: str):
        """获取或创建 Producer 实例。Get or create a Producer instance.

        懒加载：首次调用时才创建 Producer 并启动。
        Lazy: Producer is created and started on first access.
        """
        _ensure_rocketmq()
        key = cls._make_key(namesrv_addr, group_id)
        with cls._lock:
            if key not in cls._producers:
                producer = _rocketmq_client.Producer(group_id)
                producer.set_namesrv_addr(namesrv_addr)
                producer.start()
                cls._producers[key] = producer
                logger.info(
                    "RocketMQ Producer started — namesrv=%s, group=%s",
                    namesrv_addr, group_id,
                )
        return cls._producers[key]


# ============================================================================
# RocketMQ 插件注册表 / RocketMQ plugin registry
# ============================================================================

_ROCKETMQ_PLUGIN_REGISTRY: Dict[str, Type["BaseRocketMQPlugin"]] = {}
"""name → BaseRocketMQPlugin 子类映射。name → BaseRocketMQPlugin subclass mapping."""


def _register_rocketmq_plugin(cls: Type["BaseRocketMQPlugin"]) -> None:
    """注册 BaseRocketMQPlugin 子类并自动创建 Pre/Post 包装类。
    Register a BaseRocketMQPlugin subclass and auto-create Pre/Post wrapper classes.
    """
    _create_external_plugin_wrappers(cls, _ROCKETMQ_PLUGIN_REGISTRY)


# ============================================================================
# BaseRocketMQPlugin — 用户继承的基类 / Base class for user implementations
# ============================================================================

class BaseRocketMQPlugin(ABC):
    """RocketMQ 操作基类 — 管理连接，暴露 before_request / after_response 扩展点。
    RocketMQ operation base — manages connections, exposes before/after extension points.

    用户只需定义 ``name`` 类属性，实现 ``before_request`` / ``after_response``。
    ``__init_subclass__`` 自动创建并注册 PreProcessor / PostProcessor 包装类。

    Users only need to define ``name`` and implement ``before_request`` /
    ``after_response``. ``__init_subclass__`` auto-creates and registers
    PreProcessor / PostProcessor wrappers.

    用法示例 / Usage::

        class RocketMQOrderPlugin(BaseRocketMQPlugin):
            name = "rocketmq-order"

            def before_request(self, headers, body, case_config, global_config):
                self._send_message("order-topic", body, "order_create", global_config)
                return headers, body

    环境配置 / Env config (env-local.yml)::

        processor_configs:
          rocketmq-order:
            namesrv_addr: "localhost:9876"
            group_id: "test-producer-group"
            topic: "order-topic"
            tag: "order_create"

    用例 YAML / Test case YAML::

        preprocessors:
          - name: rocketmq-order
            config: {}
    """

    name: str  # 子类必须定义 / Must be defined on each subclass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _register_rocketmq_plugin(cls)

    # ── 连接管理 / Connection management ─────────────────────────────────

    def _get_producer(self, global_config: Dict[str, Any]):
        """获取 RocketMQ Producer 实例。Get a RocketMQ Producer instance.

        配置读取路径 / Config read path:
        ``global_config["processor_configs"][self.name].namesrv_addr``
        ``global_config["processor_configs"][self.name].group_id``
        """
        proc_configs = global_config.get("processor_configs", {})
        if not isinstance(proc_configs, dict):
            raise RocketMQConnectionError(
                "global_config['processor_configs'] is missing or not a dict",
                processor_name=self.name,
            )
        processor_cfg = proc_configs.get(self.name, {})
        if not isinstance(processor_cfg, dict):
            raise RocketMQConnectionError(
                f"processor_configs['{self.name}'] is missing or not a dict",
                processor_name=self.name,
            )
        namesrv_addr = processor_cfg.get("namesrv_addr", "")
        group_id = processor_cfg.get("group_id", "")
        if not namesrv_addr:
            raise RocketMQConnectionError(
                f"processor_configs['{self.name}'].namesrv_addr is not set. "
                "Please configure the RocketMQ Name Server address in env.yml, e.g.:\n"
                f"processor_configs:\n  {self.name}:\n"
                '    namesrv_addr: "localhost:9876"\n'
                '    group_id: "test-producer-group"',
                processor_name=self.name,
            )
        if not group_id:
            raise RocketMQConnectionError(
                f"processor_configs['{self.name}'].group_id is not set.",
                processor_name=self.name,
            )

        return _RocketMQManager.get_producer(namesrv_addr, group_id)

    # ── 便捷方法 / Convenience methods ────────────────────────────────────

    def _send_message(
        self,
        topic: str,
        body: Any,
        tag: str = "",
        global_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """发送消息到 RocketMQ 主题。Send a message to a RocketMQ topic.

        Args:
            topic: 主题名称 / Topic name.
            body: 消息体（自动 JSON 序列化）/ Message body (auto JSON serialized).
            tag: 消息标签 / Message tag.
            global_config: 全局配置 / Global config.
        """
        if global_config is None:
            raise RocketMQPublishError(
                "global_config is required for _send_message()",
                processor_name=self.name,
            )
        import json

        producer = self._get_producer(global_config)
        msg_body = json.dumps(body, ensure_ascii=False)
        msg = _rocketmq_message(topic)
        msg.set_keys(self.name)
        if tag:
            msg.set_tags(tag)
        msg.set_body(msg_body)

        result = producer.send_sync(msg)
        status = _rocketmq_client.SendStatus.OK
        if result != status:
            raise RocketMQPublishError(
                f"Failed to send message to topic '{topic}': status={result}",
                processor_name=self.name,
            )
        logger.info("RocketMQ message sent to topic '%s' (tag=%s)", topic, tag)

    # ── 扩展点 / Extension points ────────────────────────────────────────

    def can_process(self, case: Dict[str, Any]) -> bool:
        """是否对当前用例执行处理器。默认总是执行。
        Whether to process this case. Default: always True."""
        return True

    def before_request(
        self,
        headers: Dict[str, Any],
        body: Dict[str, Any],
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """请求前 RocketMQ 操作（前置处理器）。
        Pre-request RocketMQ operation (pre-processor).

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
        """响应后 RocketMQ 操作（后置处理器）。
        Post-response RocketMQ operation (post-processor).

        默认 no-op。RocketMQ 消费由独立消费者服务处理，后置通常只做日志记录。
        Default: no-op. RocketMQ consumption is handled by dedicated consumer services;
        post-processing typically only logs confirmation.
        """
        pass
