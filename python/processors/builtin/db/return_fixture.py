"""退货前置数据夹具处理器 — 直接向 fm_return_refund 造退货记录。
Return fixture processor — creates return records directly in fm_return_refund.

测试场景：ship-back 需要退货状态 APPROVED(1)，买家争议需要 REJECTED(2)，
退货详情/列表需要任意状态的记录。本插件先造一条 COMPLETED(4) 订单（可选），
再插入指定状态的退货记录，并把 returnId 注入请求体。
Test scenario: ship-back requires APPROVED(1), buyer dispute requires REJECTED(2),
and detail/list endpoints need records in any state. This plugin creates a
COMPLETED(4) order first (optional), then a return record in the configured
state, and injects returnId into the request body.

环境配置 / Env config (env-local.yml)::

    processor_configs:
      return-fixture:
        db_url: "h2://sa:@localhost:9092/mem:foli_mall;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_UPPER=false"
        test_buyer_id: "1000000000000000007"
        test_store_id: "1000000000000002001"
        test_product_id: "1000000000000003001"

用例 YAML / Test case YAML::

    preprocessors:
      - name: return-fixture
        config:
          return_status: 2        # 0=待审核 1=已通过 2=已拒绝 3=买家退回中 4=卖家已收货 6=已退款 7=争议中
          create_order: true      # 是否同时创建 COMPLETED 订单（默认 true）
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
# Internal metadata keys (underscore-prefixed, following the _cleared_path_params convention)
_RETURN_ID_KEY = "_return_fixture_id"
_ORDER_ID_KEY = "_return_fixture_order_id"


class ReturnFixturePlugin(BaseDBPlugin):
    """退货前置数据夹具：前置造退货记录（含关联订单），后置按需清理。
    Return fixture: pre-creates a return record (with its order); optional post cleanup."""

    name = "return-fixture"

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
        """创建退货夹具并注入 returnId。Create the return fixture and inject returnId."""
        cfg = self._merge_config(case_config, global_config)
        buyer_id = int(
            common.resolve_user_id(
                LoginManager.get_current_user(),
                cfg.get("test_buyer_id", common.SEED_BUYER_ID),
            )
        )
        store_id = int(cfg.get("test_store_id", common.SEED_STORE_ID))
        product_id = int(cfg.get("test_product_id", common.SEED_PRODUCT_ID))
        return_status = int(cfg.get("return_status", 0))
        return_type = int(cfg.get("return_type", 1))
        return_reason = cfg.get("return_reason", "e2e fixture return")
        refund_amount = cfg.get("refund_amount")
        if refund_amount is not None:
            refund_amount = float(refund_amount)

        # 支持固定 ID（幂等：先删除旧记录再插入），便于 URL 直接使用字面 ID
        # Support a fixed ID (idempotent: delete first, then insert) so the URL
        # can reference the literal ID
        return_id = int(cfg["return_id"]) if cfg.get("return_id") else common.gen_id(offset=3)
        with self._get_connection(global_config) as conn:
            try:
                with conn.begin():
                    if cfg.get("return_id"):
                        common.delete_return(conn, return_id)
                    # 先保证存在一条已完成订单 / Ensure a COMPLETED order exists first
                    if cfg.get("create_order", True):
                        order_id = int(cfg["order_id"]) if cfg.get("order_id") else common.gen_id(offset=4)
                        if cfg.get("order_id"):
                            common.delete_order(conn, order_id)
                        order_no, _pname, _pimg, price = common.insert_order(
                            conn,
                            order_id=order_id,
                            buyer_id=buyer_id,
                            store_id=store_id,
                            product_id=product_id,
                            quantity=int(cfg.get("quantity", 1)),
                            status=4,
                        )
                        order_total = price
                    else:
                        order_id = int(cfg.get("order_id", 0))
                        order_no = ""
                        order_total = refund_amount if refund_amount is not None else 0.0
                        if order_id <= 0:
                            raise ValueError("order_id is required when create_order=false")

                    return_no = common.insert_return(
                        conn,
                        return_id=return_id,
                        order_id=order_id,
                        buyer_id=buyer_id,
                        store_id=store_id,
                        return_reason=return_reason,
                        return_type=return_type,
                        refund_amount=refund_amount if refund_amount is not None else order_total,
                        status=return_status,
                    )
            except ValueError as e:
                raise ProcessorError(
                    _("return_fixture.create_failed", error=e),
                    processor_name=self.name,
                ) from e
            except Exception as e:
                raise DBQueryError(
                    _("return_fixture.create_failed", error=e),
                    processor_name=self.name,
                ) from e

        logger.info(
            _("return_fixture.created",
              return_id=return_id, return_no=return_no, order_id=order_id)
        )
        body["returnId"] = return_id
        if cfg.get("cleanup"):
            body[_RETURN_ID_KEY] = return_id
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
        """按配置删除退货夹具并校验无残留。
        Optionally delete the return fixture and verify no residual rows."""
        from sqlalchemy import text

        cfg = self._merge_config(case_config, global_config)
        if not cfg.get("cleanup"):
            logger.info(_("return_fixture.cleanup_skip"))
            return

        return_id = request_body.get(_RETURN_ID_KEY)
        order_id = request_body.get(_ORDER_ID_KEY)
        if return_id is None:
            logger.warning(_("return_fixture.missing_return"))
            return

        with self._get_connection(global_config) as conn:
            try:
                with conn.begin():
                    common.delete_return(conn, int(return_id))
                    if order_id is not None:
                        common.delete_order(conn, int(order_id))
                    remaining = conn.execute(
                        text("SELECT COUNT(*) FROM fm_return_refund WHERE id = :rid"),
                        {"rid": int(return_id)},
                    ).scalar()
                if remaining != 0:
                    raise ProcessorError(
                        _("return_fixture.cleanup_failed", error="residual rows"),
                        processor_name=self.name,
                    )
            except Exception as e:
                raise DBQueryError(
                    _("return_fixture.cleanup_failed", error=e),
                    processor_name=self.name,
                ) from e
        logger.info(
            _("return_fixture.cleanup_deleted",
              return_id=return_id, order_id=order_id)
        )
