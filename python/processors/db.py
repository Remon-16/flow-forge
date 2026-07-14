"""数据库处理器基类 — 提供连接池管理、SQL 执行、自动注册。
Database processor base — connection pool, SQL execution, auto-registration.

用户只需继承 ``BaseDBPlugin``，实现 ``before_request`` / ``after_response``，
框架自动为其创建 PreProcessor / PostProcessor 包装类并注册到全局注册表。

Users extend ``BaseDBPlugin``, implement ``before_request`` / ``after_response``,
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
# SQLAlchemy 延迟导入 / Lazy import — only when a DB processor is triggered
# ============================================================================
_SA_AVAILABLE = False
_create_engine = None
_text = None


def _ensure_sqlalchemy():
    """确保 SQLAlchemy 可用，否则给出友好错误提示。
    Ensure SQLAlchemy is importable; raise with install hint otherwise."""
    global _SA_AVAILABLE, _create_engine, _text
    if _SA_AVAILABLE:
        return
    try:
        from sqlalchemy import create_engine as _ce, text as _t
        _create_engine = _ce
        _text = _t
        _SA_AVAILABLE = True
    except ImportError:
        raise ProcessorError(
            "SQLAlchemy is required for DB processors. "
            "Install it with: pip install sqlalchemy\n"
            "You may also need a DB driver, e.g.: pip install pymysql  (MySQL)\n"
            "                                    pip install psycopg2 (PostgreSQL)",
            processor_name="db",
        )


# ============================================================================
# 自定义异常 / Custom exceptions
# ============================================================================

class DBConnectionError(ProcessorError):
    """数据库连接失败。Database connection failure."""


class DBQueryError(ProcessorError):
    """数据库查询/操作失败。Database query/operation failure.

    自动包含处理器名称，方便报告定位。
    Processor name is included for easy report tracing.
    """


# ============================================================================
# Engine 管理器 — 单例、懒加载、按 db_url 缓存 / Engine manager (singleton, lazy, cached by db_url)
# ============================================================================

class _EngineManager:
    """SQLAlchemy Engine 管理器（线程安全）。
    SQLAlchemy Engine manager (thread-safe).

    相同 ``db_url`` 的多个处理器共享同一个 Engine（及其 QueuePool）。
    Multiple processors with the same ``db_url`` share one Engine (with QueuePool).
    """

    _engines: Dict[str, Any] = {}
    _lock = threading.Lock()

    @classmethod
    def get_engine(cls, db_url: str):
        """获取或创建 Engine。Get or create an Engine for the given db_url.

        懒加载：首次调用时才创建 Engine。
        Lazy: Engine is created on first access.
        """
        _ensure_sqlalchemy()
        with cls._lock:
            if db_url not in cls._engines:
                # 使用 QueuePool（默认），pool_size=5, max_overflow=10
                # Use QueuePool (default), pool_size=5, max_overflow=10
                cls._engines[db_url] = _create_engine(
                    db_url,
                    pool_size=5,
                    max_overflow=10,
                    pool_pre_ping=True,  # 连接前检查可用性 / verify connection before use
                )
                # 掩码密码后记录日志 / Log with masked password
                safe_url = _mask_password(db_url)
                logger.info("DB Engine created for: %s", safe_url)
        return cls._engines[db_url]


# ============================================================================
# DB 插件注册表 / DB plugin registry
# ============================================================================

_DB_PLUGIN_REGISTRY: Dict[str, Type["BaseDBPlugin"]] = {}
"""name → BaseDBPlugin 子类映射。name → BaseDBPlugin subclass mapping."""


def _register_db_plugin(cls: Type["BaseDBPlugin"]) -> None:
    """注册 BaseDBPlugin 子类并自动创建 PreProcessor / PostProcessor 包装类。
    Register a BaseDBPlugin subclass and auto-create Pre/Post wrapper classes.

    委托到共享 helper _create_external_plugin_wrappers，避免重复代码。
    Delegates to shared helper _create_external_plugin_wrappers to avoid duplication.
    """
    _create_external_plugin_wrappers(cls, _DB_PLUGIN_REGISTRY)


# ============================================================================
# BaseDBPlugin — 用户继承的基类 / Base class for user implementations
# ============================================================================

class BaseDBPlugin(ABC):
    """数据库操作基类 — 管理连接，暴露 before_request / after_response 扩展点。
    DB operation base — manages connections, exposes before/after extension points.

    用户只需定义 ``name`` 类属性，实现 ``before_request`` / ``after_response``。
    ``__init_subclass__`` 自动创建并注册 PreProcessor / PostProcessor 包装类。

    Users only need to define ``name`` and implement ``before_request`` /
    ``after_response``. ``__init_subclass__`` auto-creates and registers
    PreProcessor / PostProcessor wrappers.

    用法示例 / Usage::

        class ReturnOrderDBPlugin(BaseDBPlugin):
            name = "return-order-db"

            def before_request(self, headers, body, case_config, global_config):
                with self._get_connection(global_config) as conn:
                    result = conn.execute(text("INSERT INTO ..."))
                    conn.commit()
                    body["order_id"] = result.lastrowid
                return headers, body

            def after_response(self, req_h, req_b, resp_h, resp_b, cc, gc):
                with self._get_connection(gc) as conn:
                    rows = conn.execute(text("SELECT * FROM ...")).fetchall()
                    print("Created return record:", rows)

    用例 YAML / Test case YAML::

        preprocessors:
          - name: return-order-db
            config: {}
        postprocessors:
          - name: return-order-db
            config: {}
    """

    name: str  # 子类必须定义 / Must be defined on each subclass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _register_db_plugin(cls)

    # ── 连接管理 / Connection management ─────────────────────────────────

    def _get_connection(self, global_config: Dict[str, Any]):
        """获取数据库连接（从 Engine 池中）。
        Get a database connection from the engine pool.

        配置读取路径 / Config read path:
        ``global_config["processor_configs"][self.name]["db_url"]``

        返回的 connection 支持 context manager（``with ... as conn:``），
        退出时自动归还连接到池。
        The returned connection supports context manager — connection is
        automatically returned to the pool on exit.
        """
        proc_configs = global_config.get("processor_configs", {})
        if not isinstance(proc_configs, dict):
            raise DBConnectionError(
                "global_config['processor_configs'] is missing or not a dict",
                processor_name=self.name,
            )
        processor_cfg = proc_configs.get(self.name, {})
        if not isinstance(processor_cfg, dict):
            raise DBConnectionError(
                f"processor_configs['{self.name}'] is missing or not a dict",
                processor_name=self.name,
            )
        db_url = processor_cfg.get("db_url", "")
        if not db_url:
            raise DBConnectionError(
                f"processor_configs['{self.name}'].db_url is not set. "
                "Please configure the database connection URL in env.yml, e.g.:\n"
                f"processor_configs:\n  {self.name}:\n"
                '    db_url: "mysql+pymysql://user:pass@host:3306/database"',
                processor_name=self.name,
            )

        engine = _EngineManager.get_engine(db_url)
        return engine.connect()

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
        """请求前数据库操作（前置处理器）。
        Pre-request DB operation (pre-processor).

        默认直接返回 headers, body 不做修改。子类按需覆写。
        Default: return headers, body unchanged. Override as needed.

        推荐用法 / Recommended pattern::

            with self._get_connection(global_config) as conn:
                conn.execute(text("INSERT INTO ..."))
                conn.commit()
                body["some_field"] = ...
            return headers, body
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
        """响应后数据库操作（后置处理器）。
        Post-response DB operation (post-processor).

        默认 no-op。子类按需覆写。
        Default: no-op. Override as needed.

        推荐用法 / Recommended pattern::

            with self._get_connection(global_config) as conn:
                rows = conn.execute(text("SELECT * FROM ...")).fetchall()
                print("Result:", rows)
        """
        pass
