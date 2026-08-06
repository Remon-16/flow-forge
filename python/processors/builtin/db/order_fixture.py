"""订单前置数据夹具处理器 — 直接向 fm_order / fm_order_item 造测试订单。
Order fixture processor — creates test orders directly in fm_order / fm_order_item.

测试场景：很多订单接口需要"指定状态的前置订单"，例如退货需要 COMPLETED(4)，
发货/收货需要 PAID(1)/SHIPPED(2)。用本插件可一步造出任意状态的订单，
避免在用例里串联"下单→支付→发货→收货"多步。
Test scenario: many order endpoints require an order in a specific state (e.g.
returns need COMPLETED(4); shipping/receiving need PAID(1)/SHIPPED(2)). This
plugin creates an order in any state in one step, avoiding long chained setup.

环境配置 / Env config (env-local.yml)::

    processor_configs:
      order-fixture:
        db_url: "h2://sa:@localhost:9092/mem:foli_mall;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_UPPER=false"
        test_buyer_id: "1000000000000000007"
        test_store_id: "1000000000000002001"
        test_product_id: "1000000000000003001"

用例 YAML / Test case YAML::

    preprocessors:
      - name: order-fixture
        config:
          order_status: 4          # 0=待支付 1=已支付 2=已发货 3=已收货 4=已完成 5=已取消
          cleanup: true            # 后置删除测试订单（可选）
    postprocessors:
      - name: order-fixture
        config:
          cleanup: true
"""

import logging
from typing import Any, Dict, Tuple

from i18n import _
from auth.login_manager import LoginManager
from processors.base import ProcessorError
from processors.builtin.db import _fixtures_common as common
from processors.db import BaseDBPlugin, DBQueryError

logger = logging.getLogger(__name__)

# 内部元数据键（下划线前缀，沿用 _cleared_path_params 约定）
# Internal metadata key (underscore-prefixed, following the _cleared_path_params convention)
_ORDER_ID_KEY = "_order_fixture_id"


class OrderFixturePlugin(BaseDBPlugin):
    """订单前置数据夹具：前置造任意状态订单，后置按需清理。
    Order fixture: pre-creates an order in any state; optional post cleanup."""

    name = "order-fixture"

    def _merge_config(
        self,
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """合并 env 与 case 配置。Merge env config with case-level config."""
        proc_configs = global_config.get("processor_configs", {})
        env_config = proc_configs.get(self.name, {}) if isinstance(proc_configs, dict) else {}
        return {**env_config, **case_config}

    def before_request(
        self,
        headers: Dict[str, Any],
        body: Dict[str, Any],
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """创建指定状态的测试订单并把 orderId 注入请求体。
        Create a test order in the configured state and inject orderId into the body."""
        cfg = self._merge_config(case_config, global_config)

        # 优先取当前登录用户（#{userParamName} 解析出的 buyer），否则取静态配置
        # Prefer the current logged-in user; fall back to static config
        buyer_id = int(
            common.resolve_user_id(
                LoginManager.get_current_user(),
                cfg.get("test_buyer_id", common.SEED_BUYER_ID),
            )
        )
        store_id = int(cfg.get("test_store_id", common.SEED_STORE_ID))
        product_id = int(cfg.get("test_product_id", common.SEED_PRODUCT_ID))
        status = int(cfg.get("order_status", 4))
        quantity = int(cfg.get("quantity", 1))
        total_amount = cfg.get("total_amount")
        if total_amount is not None:
            total_amount = float(total_amount)

        # 支持固定 ID（幂等：先删除旧记录再插入），便于 URL 直接使用字面 ID
        # Support a fixed ID (idempotent: delete first, then insert) so the URL
        # can reference the literal ID
        order_id = int(cfg["order_id"]) if cfg.get("order_id") else common.gen_id()
        logger.info(
            _("order_fixture.creating_order",
              order_id=order_id, buyer=buyer_id, store=store_id,
              product=product_id, status=status)
        )

        with self._get_connection(global_config) as conn:
            try:
                # 事务上下文：成功自动提交，异常自动回滚
                # Transaction context: auto-commit on success, auto-rollback on error
                with conn.begin():
                    if cfg.get("order_id"):
                        common.delete_order(conn, order_id)
                    order_no, product_name, _image, price = common.insert_order(
                        conn,
                        order_id=order_id,
                        buyer_id=buyer_id,
                        store_id=store_id,
                        product_id=product_id,
                        quantity=quantity,
                        total_amount=total_amount,
                        status=status,
                        receiver_name=cfg.get("receiver_name", "Test Buyer"),
                        receiver_phone=cfg.get("receiver_phone", "13800000000"),
                        receiver_address=cfg.get("receiver_address", "Test Address"),
                    )
            except Exception as e:
                raise DBQueryError(
                    _("order_fixture.create_failed", error=e),
                    processor_name=self.name,
                ) from e

        logger.info(
            _("order_fixture.order_created",
              order_id=order_id, order_no=order_no, product=product_name, price=price)
        )
        # 注入业务字段供接口使用 / Inject business field for the API
        body["orderId"] = order_id
        if cfg.get("cleanup"):
            body[_ORDER_ID_KEY] = order_id
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
        """按配置删除测试订单并校验无残留。
        Optionally delete the test order and verify no residual rows."""
        from sqlalchemy import text

        cfg = self._merge_config(case_config, global_config)
        if not cfg.get("cleanup"):
            logger.info(_("order_fixture.cleanup_skip"))
            return

        order_id = request_body.get(_ORDER_ID_KEY)
        if order_id is None:
            logger.warning(_("order_fixture.missing_order"))
            return

        with self._get_connection(global_config) as conn:
            try:
                with conn.begin():
                    common.delete_order(conn, int(order_id))
                    remaining = conn.execute(
                        text("SELECT COUNT(*) FROM fm_order WHERE id = :oid"),
                        {"oid": int(order_id)},
                    ).scalar()
                if remaining != 0:
                    raise ProcessorError(
                        _("order_fixture.cleanup_failed",
                          order_id=order_id, error="residual rows"),
                        processor_name=self.name,
                    )
            except ProcessorError:
                raise
            except Exception as e:
                raise DBQueryError(
                    _("order_fixture.cleanup_failed", order_id=order_id, error=e),
                    processor_name=self.name,
                ) from e
        logger.info(_("order_fixture.cleanup_deleted", order_id=order_id))
