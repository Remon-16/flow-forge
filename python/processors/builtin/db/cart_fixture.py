"""购物车前置数据夹具处理器 — 直接向 fm_cart_item 造购物车数据。
Cart fixture processor — creates cart data directly in fm_cart_item.

测试场景：创建订单（POST /api/orders）要求购物车存在"选中项"；
"购物车为空下单失败"要求购物车为空。本插件通过 mode 快速切换这两种前置状态。
Test scenario: creating an order requires selected cart items; the
"empty-cart order failure" case requires an empty cart. This plugin switches
between these two states via the mode option.

环境配置 / Env config (env-local.yml)::

    processor_configs:
      cart-fixture:
        db_url: "h2://sa:@localhost:9092/mem:foli_mall;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_UPPER=false"
        test_buyer_id: "1000000000000000007"
        test_product_id: "1000000000000003001"

用例 YAML / Test case YAML::

    preprocessors:
      - name: cart-fixture
        config:
          mode: ensure          # add=新增/累加, clear=清空, ensure=确保至少一个选中项
          product_id: 1000000000000003001
          quantity: 2
          selected: 1
          cart_item_id: 9000000000000000021   # 可选：固定购物车项 ID（幂等，add 模式）
"""

import logging
from typing import Any, Dict, Tuple

from i18n import _
from auth.login_manager import LoginManager
from processors.base import ProcessorError
from processors.builtin.db import _fixtures_common as common
from processors.db import BaseDBPlugin, DBQueryError

logger = logging.getLogger(__name__)


class CartFixturePlugin(BaseDBPlugin):
    """购物车前置数据夹具：add / clear / ensure 三种模式。
    Cart fixture: add / clear / ensure modes."""

    name = "cart-fixture"

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
        """按 mode 操作购物车并可选注入结果。
        Manipulate the cart by mode and optionally inject results."""
        from sqlalchemy import text

        cfg = self._merge_config(case_config, global_config)
        user_id = int(
            common.resolve_user_id(
                LoginManager.get_current_user(),
                cfg.get("test_buyer_id", common.SEED_BUYER_ID),
            )
        )

        mode = str(cfg.get("mode", "ensure")).lower()
        product_id = int(cfg.get("product_id", common.SEED_PRODUCT_ID))
        quantity = int(cfg.get("quantity", 1))
        selected = int(cfg.get("selected", 1))
        now = common.now_str()

        try:
            with self._get_connection(global_config) as conn:
                with conn.begin():
                    if mode == "clear":
                        # 物理删除该用户全部购物车行（含历史逻辑删除残留），彻底重置状态
                        # Physically delete all cart rows (including logically-deleted leftovers) to fully reset state
                        result = conn.execute(
                            text("DELETE FROM fm_cart_item WHERE user_id = :uid"),
                            {"uid": user_id},
                        )
                        logger.info(_("cart_fixture.cleared", user=user_id, count=result.rowcount))
                    elif mode == "add":
                        # 固定 ID 模式：幂等先删后插，便于 URL 直接使用字面 ID
                        # Fixed-ID mode: idempotent delete-then-insert so the URL can use a literal ID
                        fixed_item_id = int(cfg["cart_item_id"]) if cfg.get("cart_item_id") else None
                        if fixed_item_id is not None:
                            conn.execute(
                                text("DELETE FROM fm_cart_item WHERE id = :id"),
                                {"id": fixed_item_id},
                            )
                            item_id = fixed_item_id
                            conn.execute(
                                text(
                                    "INSERT INTO fm_cart_item (id, user_id, product_id, quantity, selected, is_delete, "
                                    "create_time, edit_time, update_time) "
                                    "VALUES (:id, :uid, :pid, :qty, :sel, 0, :now, :now, :now)"
                                ),
                                {
                                    "id": item_id, "uid": user_id, "pid": product_id,
                                    "qty": quantity, "sel": selected, "now": now,
                                },
                            )
                            logger.info(
                                _("cart_fixture.inserted",
                                  cart_item_id=item_id, user=user_id,
                                  product=product_id, quantity=quantity)
                            )
                            if cfg.get("inject_cart_item_id"):
                                body["cartItemId"] = item_id
                        else:
                            # 只认未删除行（MyBatis-Plus 逻辑删除约定 is_delete=0）
                            # Only treat non-deleted rows as existing (MyBatis-Plus logic-delete convention)
                            rows = conn.execute(
                                text(
                                    "SELECT id, quantity FROM fm_cart_item "
                                    "WHERE user_id = :uid AND product_id = :pid AND is_delete = 0"
                                ),
                                {"uid": user_id, "pid": product_id},
                            ).fetchall()
                            if rows:
                                # 遵循 foli-mall 语义：同商品累加数量
                                # Follow foli-mall semantics: accumulate quantity
                                item_id, old_qty = rows[0][0], rows[0][1]
                                conn.execute(
                                    text(
                                        "UPDATE fm_cart_item SET quantity = :qty, selected = :sel, "
                                        "edit_time = :now, update_time = :now WHERE id = :id"
                                    ),
                                    {"qty": old_qty + quantity, "sel": selected, "now": now, "id": item_id},
                                )
                                logger.info(
                                    _("cart_fixture.updated",
                                      cart_item_id=item_id, quantity=old_qty + quantity, selected=selected)
                                )
                                if cfg.get("inject_cart_item_id"):
                                    body["cartItemId"] = item_id
                            else:
                                item_id = common.gen_id(offset=1)
                                conn.execute(
                                    text(
                                        "INSERT INTO fm_cart_item (id, user_id, product_id, quantity, selected, is_delete, "
                                        "create_time, edit_time, update_time) "
                                        "VALUES (:id, :uid, :pid, :qty, :sel, 0, :now, :now, :now)"
                                    ),
                                    {
                                        "id": item_id, "uid": user_id, "pid": product_id,
                                        "qty": quantity, "sel": selected, "now": now,
                                    },
                                )
                                logger.info(
                                    _("cart_fixture.inserted",
                                      cart_item_id=item_id, user=user_id,
                                      product=product_id, quantity=quantity)
                                )
                                if cfg.get("inject_cart_item_id"):
                                    body["cartItemId"] = item_id
                    elif mode == "ensure":
                        count = conn.execute(
                            text(
                                "SELECT COUNT(*) FROM fm_cart_item "
                                "WHERE user_id = :uid AND selected = 1 AND is_delete = 0"
                            ),
                            {"uid": user_id},
                        ).scalar()
                        if not count:
                            item_id = common.gen_id(offset=2)
                            conn.execute(
                                text(
                                    "INSERT INTO fm_cart_item (id, user_id, product_id, quantity, selected, is_delete, "
                                    "create_time, edit_time, update_time) "
                                    "VALUES (:id, :uid, :pid, :qty, :sel, 0, :now, :now, :now)"
                                ),
                                {
                                    "id": item_id, "uid": user_id, "pid": product_id,
                                    "qty": quantity, "sel": 1, "now": now,
                                },
                            )
                            count = 1
                            logger.info(
                                _("cart_fixture.inserted",
                                  cart_item_id=item_id, user=user_id,
                                  product=product_id, quantity=quantity)
                            )
                        if cfg.get("inject_selected_count"):
                            body["cartSelectedCount"] = count
                        logger.info(_("cart_fixture.ensured", count=count))
                    else:
                        raise ValueError(mode)
        except ValueError as e:
            raise ProcessorError(
                _("cart_fixture.mode_invalid", mode=e),
                processor_name=self.name,
            ) from e
        except Exception as e:
            raise DBQueryError(
                _("cart_fixture.failed", error=e),
                processor_name=self.name,
            ) from e
        return headers, body
