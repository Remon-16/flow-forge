"""退货单数据库处理器 — 示例 BaseDBPlugin 实现。
Return Order DB Processor — example BaseDBPlugin implementation.

测试场景：申请退货退款（POST /api/returns）。
该接口需要一个状态为"已完成"(status=4)的订单才能发起退货；
请求体需要 orderId / returnReason / returnType 字段，其中 orderId 由前置处理器注入。

Test scenario: apply for return/refund (POST /api/returns).
This API requires an order with status=4 (completed) to exist beforehand;
the request body needs orderId / returnReason / returnType, with orderId
injected by the pre-processor.

前置处理器（before_request）：INSERT 测试订单 + 订单明细，注入 order_id 到请求体。
后置处理器（after_response）：查询 API 创建的退货记录并 print（示例用 print，生产环境应 DELETE）。

Pre-processor (before_request): INSERT test order + order item, inject order_id into body.
Post-processor (after_response): query created return record and print (demo: print; prod: DELETE).

使用方式 / Usage in YAML:

.. code-block:: yaml

    preprocessors:
      - name: return-order-db
        config: {}
    postprocessors:
      - name: return-order-db
        config: {}

env-local.yml 配置 / Configuration::

    processor_configs:
      return-order-db:
        db_url: "h2://sa:@localhost:9092/mem:foli_mall;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_UPPER=false"
        test_buyer_id: "1000000000000000007"   # 测试买家用户 ID (buyer01) / Test buyer user ID
        test_store_id: "1000000000000002001"   # 测试店铺 ID (store1) / Test store ID
        test_product_id: "1000000000000003001" # 测试商品 ID (product1) / Test product ID
        order_status: 4                        # 订单状态：4=已完成（foli-mall 要求） / order status: 4=completed (required by foli-mall)

    H2 依赖安装 / H2 dependency install::

        pip install JPype1 JayDeBeApi

    H2 SQLAlchemy 方言内置在 / H2 SQLAlchemy dialect is built into::

        processors/h2_dialect.py

    H2 运行前提（对应 foli-mall 的 H2 内存库）/ H2 prerequisites::

        1. 运行 python tools/h2/init_h2.py 下载 H2 JDBC jar（方言自动加载，无需 CLASSPATH）
        2. 启动 foli-mall 后端（应用启动时自动开启 H2 TCP Server，默认端口 9092）
        3. 运行 flow-forge 用例

        1. Run python tools/h2/init_h2.py to download the H2 JDBC jar (auto-loaded, no CLASSPATH)
        2. Start the foli-mall backend (it starts an H2 TCP Server on port 9092 on boot)
        3. Run flow-forge cases
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, Tuple

from i18n import _
from processors.db import BaseDBPlugin, DBQueryError
from auth.login_manager import LoginManager

logger = logging.getLogger(__name__)


class ReturnOrderDBPlugin(BaseDBPlugin):
    """退货单数据库处理器：前置造订单数据，后置展示退货结果。
    Return order DB processor: pre-creates order, post-prints return result."""

    name = "return-order-db"

    # ── 前置处理器：创建测试订单 / Pre: create test order ────────────────

    def before_request(
        self,
        headers: Dict[str, Any],
        body: Dict[str, Any],
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """在数据库中创建一条已收货的测试订单，将 order_id 注入请求体。
        INSERT a test order (status=received) into DB, inject order_id into body."""

        # 读取处理器配置（合并 env 配置和 case 配置）
        # Read processor config (env config merged with case config)
        proc_configs = global_config.get("processor_configs", {})
        env_cfg = proc_configs.get(self.name, {}) if isinstance(proc_configs, dict) else {}
        cfg = {**env_cfg, **case_config}

        # 优先从登录用户配置获取 buyer_id（动态解析 #{} 语法时的用户信息）
        # Prefer buyer_id from login user config (user info from #{userParamName} resolution)
        # 若未使用 #{} 登录或无 user_id 字段，则 fallback 到 processor_configs 中的静态配置
        # Falls back to static config in processor_configs if no #{userParamName} login
        current_user = LoginManager.get_current_user()
        if current_user and "user_id" in current_user:
            buyer_id = int(current_user["user_id"])
        else:
            buyer_id = int(cfg.get("test_buyer_id", 1))
        store_id = int(cfg.get("test_store_id", 1))
        product_id = int(cfg.get("test_product_id", 1))
        # 4=已完成/completed（foli-mall 创建退货要求 COMPLETED）
        # 4=completed (foli-mall requires COMPLETED to create a return)
        order_status = int(cfg.get("order_status", 4))

        # 生成唯一 ID（简单雪花ID模拟）
        # Generate unique ID (simple Snowflake-ID-like)
        order_id = int(time.time() * 1000000) % (10 ** 15)
        order_item_id = order_id + 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        order_no = f"TEST{order_id % (10 ** 12):012d}"

        logger.info(
            _("return_order.creating_order", order_id=order_id, buyer=buyer_id, store=store_id, product=product_id)
        )

        with self._get_connection(global_config) as conn:
            try:
                # 查询商品信息作为快照 / Query product info for snapshot
                # 事务上下文（SQLAlchemy 1.4+/2.0 兼容）：成功自动提交，异常自动回滚
                # Transaction context (SQLAlchemy 1.4+/2.0 compatible): auto commit/rollback
                with conn.begin():
                    from sqlalchemy import text
                    prod_rows = conn.execute(
                        text("SELECT name, main_image, price FROM fm_product WHERE id = :pid AND is_delete = 0"),
                        {"pid": product_id},
                    ).fetchall()

                    if prod_rows:
                        row = prod_rows[0]
                        product_name, product_image, price = row[0], row[1], row[2]
                    else:
                        # 商品不存在时使用默认值 / Fallback defaults when product not found
                        logger.warning(_("return_order.product_not_found", product_id=product_id))
                        product_name = "Test Product"
                        product_image = ""
                        price = 99.99

                    # 1) INSERT 订单 / Insert order
                    conn.execute(
                        text(
                            "INSERT INTO fm_order (id, order_no, user_id, store_id, "
                            "total_amount, status, create_time, edit_time, update_time) "
                            "VALUES (:id, :order_no, :user_id, :store_id, "
                            ":total_amount, :status, :now, :now, :now)"
                        ),
                        {
                            "id": order_id,
                            "order_no": order_no,
                            "user_id": buyer_id,
                            "store_id": store_id,
                            "total_amount": price,
                            "status": order_status,
                            "now": now,
                        },
                    )

                    # 2) INSERT 订单明细 / Insert order item
                    conn.execute(
                        text(
                            "INSERT INTO fm_order_item (id, order_id, product_id, "
                            "product_name, product_image, price, quantity, "
                            "create_time, edit_time, update_time) "
                            "VALUES (:id, :order_id, :product_id, "
                            ":product_name, :product_image, :price, :quantity, "
                            ":now, :now, :now)"
                        ),
                        {
                            "id": order_item_id,
                            "order_id": order_id,
                            "product_id": product_id,
                            "product_name": product_name,
                            "product_image": product_image or "",
                            "price": price,
                            "quantity": 1,
                            "now": now,
                        },
                    )

                logger.info(
                    _("return_order.order_created", order_id=order_id, order_no=order_no,
                      product=product_name, price=price)
                )

            except Exception as e:
                raise DBQueryError(
                    _("return_order.create_failed", error=e),
                    processor_name=self.name,
                ) from e

        # 3) 将 orderId 注入请求体，供 API 使用（与 ReturnCreateRequest 的驼峰字段一致）
        # Inject orderId into the request body for the API (camelCase matches ReturnCreateRequest)
        body["orderId"] = order_id
        return headers, body

    # ── 后置处理器：查询退货记录并展示 / Post: query return record and print ──

    def after_response(
        self,
        request_headers: Dict[str, Any],
        request_body: Dict[str, Any],
        response_headers: Dict[str, Any],
        response_body: Any,
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> None:
        """查询 API 创建的退货记录并 print 展示（生产环境应改为 DELETE 清理）。
        Query the return record created by the API and print it (prod: DELETE cleanup)."""

        # 优先读取驼峰 orderId，兼容旧版下划线 order_id
        # Prefer camelCase orderId; fall back to legacy snake_case order_id
        order_id = request_body.get("orderId") or request_body.get("order_id")
        if not order_id:
            logger.warning(_("return_order.post_no_order"))
            return

        logger.info(_("return_order.post_querying", order_id=order_id))

        with self._get_connection(global_config) as conn:
            try:
                from sqlalchemy import text
                rows = conn.execute(
                    text(
                        "SELECT id, return_no, order_id, user_id, store_id, "
                        "return_reason, return_type, refund_amount, status, create_time "
                        "FROM fm_return_refund WHERE order_id = :oid ORDER BY create_time DESC"
                    ),
                    {"oid": order_id},
                ).fetchall()

                # ── 展示结果（生产环境应改为 DELETE 清理测试数据） ──
                # Print results (in production, DELETE test data instead)
                print("\n" + "=" * 60)
                print("  [DB Post-Processor: return-order-db]")
                print(_("return_order.print_created", order_id=order_id))
                if rows:
                    for r in rows:
                        print(_("return_order.print_return", id=r[0], return_no=r[1]))
                        print(_("return_order.print_return_detail", status=r[8], refund_amount=r[7]))
                        print(_("return_order.print_return_reason", reason=r[5]))
                else:
                    print(_("return_order.print_no_return"))
                print("=" * 60 + "\n")

                if rows:
                    logger.info(
                        _("return_order.post_found", count=len(rows), order_id=order_id)
                    )

            except Exception as e:
                # 后置处理器失败不抛异常，仅记录日志
                # Post-processor failure only logs, does not throw
                logger.warning(_("return_order.post_query_failed", order_id=order_id, error=e))
