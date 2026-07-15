"""退货单数据库处理器 — 示例 BaseDBPlugin 实现。
Return Order DB Processor — example BaseDBPlugin implementation.

测试场景：申请退货退款（POST /api/return_refund）。
该接口需要一个状态为"已收货"(status=3)的订单才能发起退货。

Test scenario: apply for return/refund (POST /api/return_refund).
This API requires an order with status=3 (received) to exist beforehand.

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
        db_url: "mysql+pymysql://root:123456@localhost:3306/foli_mall"
        test_buyer_id: 1        # 测试买家用户 ID / Test buyer user ID
        test_store_id: 1        # 测试店铺 ID / Test store ID
        test_product_id: 1      # 测试商品 ID / Test product ID
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, Tuple

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
        order_status = int(cfg.get("order_status", 3))  # 3=已收货/received

        # 生成唯一 ID（简单雪花ID模拟）
        # Generate unique ID (simple Snowflake-ID-like)
        order_id = int(time.time() * 1000000) % (10 ** 15)
        order_item_id = order_id + 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        order_no = f"TEST{order_id % (10 ** 12):012d}"

        logger.info(
            "Creating test order: order_id=%s, buyer=%s, store=%s, product=%s",
            order_id, buyer_id, store_id, product_id,
        )

        with self._get_connection(global_config) as conn:
            try:
                # 查询商品信息作为快照 / Query product info for snapshot
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
                    logger.warning("Product id=%s not found, using defaults", product_id)
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

                conn.commit()
                logger.info(
                    "Test order created: id=%s, order_no=%s, product=%s, price=%s",
                    order_id, order_no, product_name, price,
                )

            except Exception as e:
                conn.rollback()
                raise DBQueryError(
                    f"Failed to create test order: {e}",
                    processor_name=self.name,
                ) from e

        # 3) 将 order_id 注入请求体，供 API 使用
        # Inject order_id into request body for the API
        body["order_id"] = order_id
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

        order_id = request_body.get("order_id")
        if not order_id:
            logger.warning("No order_id in request body, skipping post-processing")
            return

        logger.info("Post-processing: querying return record for order_id=%s", order_id)

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
                print(f"  Created test order: id={order_id}")
                if rows:
                    for r in rows:
                        print(f"  Return record: id={r[0]}, return_no={r[1]}")
                        print(f"    status={r[8]}, refund_amount={r[7]}")
                        print(f"    reason={r[5]}")
                else:
                    print(f"  (No return record found — API may have failed)")
                print("=" * 60 + "\n")

                if rows:
                    logger.info(
                        "Found %d return record(s) for order_id=%s", len(rows), order_id,
                    )

            except Exception as e:
                # 后置处理器失败不抛异常，仅记录日志
                # Post-processor failure only logs, does not throw
                logger.warning("Post-processing query failed for order_id=%s: %s", order_id, e)
