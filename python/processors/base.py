"""Abstract base classes and registry for Pre/Post processors.

提供了 PreProcessor / PostProcessor 抽象基类、自动注册机制，
以及外部资源插件（DB/Redis/MQ）的共享包装器创建工具。
Provides PreProcessor/PostProcessor ABCs, auto-registration, and shared
wrapper-creation utilities for external resource plugins (DB/Redis/MQ).
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Type

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global registries (populated automatically via __init_subclass__)
# ---------------------------------------------------------------------------
_PRE_PROCESSOR_REGISTRY: Dict[str, Type["PreProcessor"]] = {}
_POST_PROCESSOR_REGISTRY: Dict[str, Type["PostProcessor"]] = {}


def _register_pre_processor(cls: Type["PreProcessor"]) -> None:
    name = getattr(cls, "name", None)
    if not name:
        raise TypeError(f"PreProcessor subclass {cls.__name__} must define a 'name' class attribute")
    _PRE_PROCESSOR_REGISTRY[name] = cls


def _register_post_processor(cls: Type["PostProcessor"]) -> None:
    name = getattr(cls, "name", None)
    if not name:
        raise TypeError(f"PostProcessor subclass {cls.__name__} must define a 'name' class attribute")
    _POST_PROCESSOR_REGISTRY[name] = cls


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class ProcessorError(Exception):
    """处理器抛出的可控错误——消息会出现在测试报告中。
    Controlled error from a processor — message flows into the test report."""

    def __init__(self, message: str, processor_name: str = ""):
        super().__init__(message)
        self.processor_name = processor_name


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def _mask_password(url: str) -> str:
    """掩码 URL 中的密码，用于安全日志输出。
    Mask password in a connection URL for safe logging.

    适用于 db_url、redis_url、mq_url 等包含 user:password@host 格式的 URL。
    Works for db_url, redis_url, mq_url, etc. in user:password@host format.
    """
    try:
        # 格式: scheme://user:password@host:port/path
        # Format: scheme://user:password@host:port/path
        if "@" in url and "://" in url:
            prefix = url.split("://", 1)[0]
            rest = url.split("://", 1)[1]
            if ":" in rest and "@" in rest:
                user_pass, host_part = rest.split("@", 1)
                if ":" in user_pass:
                    user, _pass = user_pass.split(":", 1)
                    return f"{prefix}://{user}:***@{host_part}"
    except Exception:
        pass
    return url


def _create_external_plugin_wrappers(
    cls: Type,
    plugin_registry: Dict[str, Type],
) -> None:
    """为外部资源插件（DB/Redis/MQ/RocketMQ）自动创建 Pre/PostProcessor 包装类。
    Auto-create PreProcessor/PostProcessor wrapper classes for external resource
    plugins (DB/Redis/MQ/RocketMQ).

    此函数封装了 type() 动态创建包装类的通用逻辑，避免在每个插件模块中重复。
    This function encapsulates the common type()-based wrapper creation logic,
    avoiding duplication across plugin modules.

    工作流程 / Workflow:
    1. 验证 cls.name 存在且非空 / Validate cls.name is set and non-empty
    2. 将 cls 注册到 plugin_registry[name] / Register cls in plugin_registry[name]
    3. 用 type() 动态创建 PreProcessor 子类，process() → cls().before_request()
    4. 用 type() 动态创建 PostProcessor 子类，process() → cls().after_response()
    5. type() 自动触发 __init_subclass__ → 注册到全局 _PRE/_POST_PROCESSOR_REGISTRY

    Args:
        cls: 用户编写的插件子类（BaseDBPlugin/BaseRedisPlugin/... 的子类）。
             User-defined plugin subclass.
        plugin_registry: 类别专属注册表（如 _DB_PLUGIN_REGISTRY）。
                         Category-specific registry dict.
    """
    name = getattr(cls, "name", None)
    if not name:
        raise TypeError(
            f"{cls.__name__} must define a 'name' class attribute. "
            f"请在 {cls.__name__} 上定义 'name' 类属性。"
        )
    plugin_registry[name] = cls

    # ── 动态创建 PreProcessor 包装类 ────────────────────────────────────
    # Dynamically create PreProcessor wrapper class
    # 委托到 cls().before_request / Delegate to cls().before_request
    pre_cls = type(
        f"{cls.__name__}PreWrapper",
        (PreProcessor,),
        {
            "name": name,
            "_plugin_cls": cls,
            "process": lambda self, h, b, cc, gc: cls().before_request(h, b, cc, gc),
            "can_process": lambda self, case: cls().can_process(case),
        },
    )
    # type() 创建 PreProcessor 子类 → 触发 PreProcessor.__init_subclass__
    # → _register_pre_processor(pre_cls)

    # ── 动态创建 PostProcessor 包装类 ───────────────────────────────────
    # Dynamically create PostProcessor wrapper class
    # 委托到 cls().after_response / Delegate to cls().after_response
    post_cls = type(
        f"{cls.__name__}PostWrapper",
        (PostProcessor,),
        {
            "name": name,
            "_plugin_cls": cls,
            "process": lambda self, rh, rb, rsh, rsb, cc, gc: (
                cls().after_response(rh, rb, rsh, rsb, cc, gc)
            ),
        },
    )
    # type() 创建 PostProcessor 子类 → 触发 PostProcessor.__init_subclass__
    # → _register_post_processor(post_cls)

    logger.info(
        "Registered plugin '%s' → PreProcessor=%s, PostProcessor=%s",
        name, pre_cls.__name__, post_cls.__name__,
    )


# ---------------------------------------------------------------------------
# Abstract base classes
# ---------------------------------------------------------------------------

class PreProcessor(ABC):
    """Base class for pre-request processors.

    Subclasses are auto-registered by ``name``.  Place your ``.py`` file in
    the ``processors/`` directory and it will be discovered at runtime.
    """

    name: str  # Must be set on each subclass (used as registry key)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _register_pre_processor(cls)

    def can_process(self, case: Dict[str, Any]) -> bool:
        """Override to conditionally skip this processor for a given case."""
        return True

    @abstractmethod
    def process(
        self,
        headers: Dict[str, Any],
        body: Dict[str, Any],
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Modify request headers and/or body before the request is sent.

        Args:
            headers: Current request headers (mutable copy).
            body: Current request body (mutable copy).
            case_config: Inline ``config`` dict from the test case.
            global_config: Full merged environment configuration
                (includes ``processor_configs`` top-level key).

        Returns:
            ``(modified_headers, modified_body)``.

        Raises:
            ProcessorError: Abort the test case with an error message
                that appears in the report.
        """
        ...


class PostProcessor(ABC):
    """Base class for post-response processors.

    Subclasses are auto-registered by ``name``.
    """

    name: str  # Must be set on each subclass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _register_post_processor(cls)

    @abstractmethod
    def process(
        self,
        request_headers: Dict[str, Any],
        request_body: Dict[str, Any],
        response_headers: Dict[str, Any],
        response_body: Any,
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> None:
        """Inspect or post-process the response after assertions have run.

        Args:
            request_headers: Headers that were sent.
            request_body: Body that was sent.
            response_headers: Response headers (dict).
            response_body: Parsed response body (JSON object, list, or string).
            case_config: Inline ``config`` dict from the test case.
            global_config: Full merged environment configuration.

        Raises:
            ProcessorError: Record a post-processing error in the report.
        """
        ...


# ---------------------------------------------------------------------------
# 外部资源插件共享基类 / Shared base for external-resource plugins
# ---------------------------------------------------------------------------

class BaseExternalPlugin(ABC):
    """外部资源插件共享基类（DB / Redis / MQ / Kafka / Pulsar / RocketMQ）。
    Shared base for external-resource plugin base classes
    (BaseDBPlugin, BaseRedisPlugin, BaseMQPlugin, BaseKafkaPlugin,
    BasePulsarPlugin, BaseRocketMQPlugin).

    定义 before_request / after_response / can_process 三个扩展点的默认实现，
    各资源基类仅需提供资源专属的连接管理逻辑（如 _get_connection / _get_client）。
    Defines default no-op implementations for the three extension points,
    so resource-specific bases only need to provide connection management.

    不定义 __init_subclass__ — 注册逻辑仍由各资源基类负责，
    避免 BaseExternalPlugin 子类化时触发额外的注册行为。
    No __init_subclass__ — registration is handled by each resource-specific
    base class to avoid double-registration.
    """

    name: str  # 子类必须定义 / Must be defined on each concrete subclass

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
        """请求前操作（前置处理器）。默认直接返回 headers, body 不做修改。
        Pre-request operation (pre-processor). Default: return unchanged.
        子类按需覆写。Subclasses override as needed."""
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
        """响应后操作（后置处理器）。默认 no-op。
        Post-response operation (post-processor). Default: no-op.
        子类按需覆写。Subclasses override as needed."""
        pass
