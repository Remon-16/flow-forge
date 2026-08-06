"""MySQL 示例处理器 — 前置写入测试数据，后置读取并清理。
MySQL demo processor — pre-write test data, post-read and clean up.

测试场景 / Test scenario:
    验证 flow-forge 的数据库处理器可连接 MySQL，并保证「写入 → 可读 → 清理后查不到」。
    Validates that flow-forge DB processors can connect to MySQL and that
    "write → readable → not found after cleanup" holds.

前置处理器（before_request）：创建示例表（如不存在），写入一行数据，并把 key 注入请求体。
后置处理器（after_response）：SELECT 校验数据可读，print 展示后 DELETE，再校验已删除。

Pre-processor (before_request): create the demo table (if absent), insert one row,
and inject the key into the request body.
Post-processor (after_response): SELECT to verify the row is readable, print it,
DELETE it, then verify it is gone.

环境配置 / Env config (env-local.yml)::

    processor_configs:
      mysql-demo:
        db_url: "mysql+pymysql://root:password@localhost:3306/flow_forge_demo?charset=utf8mb4"

用例 YAML / Test case YAML::

    preprocessors:
      - name: mysql-demo
        config: {}
    postprocessors:
      - name: mysql-demo
        config: {}
"""

import json
import logging
import time
from typing import Any, Dict, Tuple

from i18n import _
from processors.base import ProcessorError
from processors.db import BaseDBPlugin, DBQueryError

logger = logging.getLogger(__name__)

# 示例表名（常量，非用户输入，可安全拼接）/ Demo table name (constant, safe to interpolate)
_TABLE = "ff_plugin_demo"


class MysqlDemoPlugin(BaseDBPlugin):
    """MySQL 示例处理器：前置写数据，后置读+删并校验。
    MySQL demo processor: pre-write, post-read + delete with verification."""

    name = "mysql-demo"

    def before_request(
        self,
        headers: Dict[str, Any],
        body: Dict[str, Any],
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """写入一行测试数据并把 key 注入请求体。
        Insert one test row and inject the key into the request body."""
        # 合并配置：case 级覆盖 env 默认值 / Merge config: case-level overrides env defaults
        proc_configs = global_config.get("processor_configs", {})
        env_cfg = proc_configs.get(self.name, {}) if isinstance(proc_configs, dict) else {}
        cfg = {**env_cfg, **case_config}

        key = int(time.time() * 1000)
        payload = json.dumps(body, ensure_ascii=False)[:500]

        with self._get_connection(global_config) as conn:
            try:
                from sqlalchemy import text
                # 事务上下文（SQLAlchemy 1.4+/2.0 兼容）：成功自动提交，异常自动回滚
                # Transaction context (SQLAlchemy 1.4+/2.0 compatible): auto commit/rollback
                with conn.begin():
                    conn.execute(text(
                        "CREATE TABLE IF NOT EXISTS %s ("
                        "id BIGINT PRIMARY KEY, "
                        "payload VARCHAR(500) NOT NULL, "
                        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)" % _TABLE
                    ))
                    conn.execute(
                        text("INSERT INTO %s (id, payload) VALUES (:id, :payload)" % _TABLE),
                        {"id": key, "payload": payload},
                    )
            except Exception as e:
                raise DBQueryError(
                    _("mysql_demo.write_failed", error=str(e)),
                    processor_name=self.name,
                ) from e

        logger.info(_("mysql_demo.inserted", demo_id=key))
        body["mysql_demo_key"] = key
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
        """读取并展示测试数据，随后删除并校验无残留。
        Read and print the test row, then delete it and verify no residual rows."""
        key = request_body.get("mysql_demo_key")
        if not key:
            logger.warning(_("mysql_demo.missing_key"))
            return

        with self._get_connection(global_config) as conn:
            try:
                from sqlalchemy import text
                with conn.begin():
                    rows = conn.execute(
                        text("SELECT payload FROM %s WHERE id = :id" % _TABLE),
                        {"id": int(key)},
                    ).fetchall()
                    if not rows:
                        raise ProcessorError(
                            _("mysql_demo.read_failed", demo_id=key),
                            processor_name=self.name,
                        )

                    print("\n" + "=" * 60)
                    print("  [DB Post-Processor: mysql-demo]")
                    print(_("mysql_demo.read_ok", demo_id=key, payload=rows[0][0]))

                    result = conn.execute(
                        text("DELETE FROM %s WHERE id = :id" % _TABLE),
                        {"id": int(key)},
                    )
                    if result.rowcount != 1:
                        raise ProcessorError(
                            _("mysql_demo.delete_failed", demo_id=key),
                            processor_name=self.name,
                        )

                    remaining = conn.execute(
                        text("SELECT COUNT(*) FROM %s WHERE id = :id" % _TABLE),
                        {"id": int(key)},
                    ).scalar()
                    if remaining != 0:
                        raise ProcessorError(
                            _("mysql_demo.delete_failed", demo_id=key),
                            processor_name=self.name,
                        )

                    print(_("mysql_demo.deleted_ok", demo_id=key))
                    print("=" * 60 + "\n")
            except ProcessorError:
                raise
            except Exception as e:
                # 后置处理器失败不中断报告，仅记录日志
                # Post-processor failure only logs; the report continues
                logger.warning("mysql-demo post-processing failed: %s", e)
