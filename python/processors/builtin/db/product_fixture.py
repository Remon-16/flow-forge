"""商品前置数据夹具处理器 — 直接操作 fm_product。
Product fixture processor — manipulates fm_product directly.

测试场景：库存不足下单/加购需要明确库存；下架商品购物车项删除需要
status=OFF_SHELF(4)；"商品已删除"列表场景需要逻辑删除（is_delete=1）。
种子商品被多个用例共享，因此本插件的后置 cleanup 会恢复原 stock /
status / is_delete，避免污染其他用例。
Test scenario: insufficient-stock cases need explicit stock; deleting a cart
item of an off-shelf product needs status=OFF_SHELF(4); the deleted-product
list case needs a logical delete (is_delete=1). Seed products are shared across
cases, so the post cleanup restores the original stock / status / is_delete.

环境配置 / Env config (env-local.yml)::

    processor_configs:
      product-fixture:
        db_url: "h2://sa:@localhost:9092/mem:foli_mall;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_UPPER=false"
        test_product_id: "1000000000000003001"

用例 YAML / Test case YAML::

    preprocessors:
      - name: product-fixture
        config:
          mode: set_stock        # set_stock / set_status / set_deleted
          product_id: 1000000000000003001
          stock: 50
    postprocessors:
      - name: product-fixture
        config:
          cleanup: true          # 恢复原 stock / status / is_delete
"""

import logging
from typing import Any, Dict, Tuple

from i18n import _
from processors.base import ProcessorError
from processors.builtin.db import _fixtures_common as common
from processors.db import BaseDBPlugin, DBQueryError

logger = logging.getLogger(__name__)

# 内部元数据键（下划线前缀，沿用 _cleared_path_params 约定）
# Internal metadata keys (underscore-prefixed, following the _cleared_path_params convention)
_PRODUCT_ID_KEY = "_product_fixture_id"
_ORIGINAL_KEY = "_product_fixture_original"

# 商品状态（与 foli-mall ProductStatusEnum 一致）
# Product statuses (consistent with foli-mall ProductStatusEnum)
STATUS_APPROVED = 2
STATUS_OFF_SHELF = 4


class ProductFixturePlugin(BaseDBPlugin):
    """商品前置数据夹具：set_stock / set_status / set_deleted，后置恢复原值。
    Product fixture: set_stock / set_status / set_deleted; optional post restore."""

    name = "product-fixture"

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
        """按 mode 修改商品并记录原值。Modify the product by mode and record originals."""
        from sqlalchemy import text

        cfg = self._merge_config(case_config, global_config)
        mode = str(cfg.get("mode", "set_stock")).lower()
        product_id = int(
            cfg.get("product_id") or cfg.get("test_product_id", common.SEED_PRODUCT_ID)
        )

        try:
            with self._get_connection(global_config) as conn:
                with conn.begin():
                    rows = conn.execute(
                        text(
                            "SELECT stock, status, is_delete FROM fm_product "
                            "WHERE id = :pid"
                        ),
                        {"pid": product_id},
                    ).fetchall()
                    if not rows:
                        raise ProcessorError(
                            _("product_fixture.missing_product", product_id=product_id),
                            processor_name=self.name,
                        )
                    old_stock, old_status, old_deleted = rows[0]
                    original = (old_stock, old_status, old_deleted)
                    now = common.now_str()

                    if mode == "set_stock":
                        stock = int(cfg.get("stock", 50))
                        conn.execute(
                            text(
                                "UPDATE fm_product SET stock = :stock, "
                                "edit_time = :now, update_time = :now WHERE id = :pid"
                            ),
                            {"stock": stock, "now": now, "pid": product_id},
                        )
                        logger.info(
                            _("product_fixture.updated",
                              product_id=product_id, stock=stock,
                              status=old_status, is_delete=old_deleted)
                        )
                    elif mode == "set_status":
                        status = int(cfg.get("status", STATUS_OFF_SHELF))
                        conn.execute(
                            text(
                                "UPDATE fm_product SET status = :status, "
                                "edit_time = :now, update_time = :now WHERE id = :pid"
                            ),
                            {"status": status, "now": now, "pid": product_id},
                        )
                        logger.info(
                            _("product_fixture.updated",
                              product_id=product_id, stock=old_stock,
                              status=status, is_delete=old_deleted)
                        )
                    elif mode == "set_deleted":
                        conn.execute(
                            text(
                                "UPDATE fm_product SET is_delete = 1, "
                                "edit_time = :now, update_time = :now WHERE id = :pid"
                            ),
                            {"now": now, "pid": product_id},
                        )
                        logger.info(
                            _("product_fixture.updated",
                              product_id=product_id, stock=old_stock,
                              status=old_status, is_delete=1)
                        )
                    else:
                        raise ValueError(mode)
        except ValueError as e:
            raise ProcessorError(
                _("product_fixture.mode_invalid", mode=e),
                processor_name=self.name,
            ) from e
        except ProcessorError:
            raise
        except Exception as e:
            raise DBQueryError(
                _("product_fixture.failed", error=e),
                processor_name=self.name,
            ) from e

        # 记录原值供后置恢复使用 / Record originals for post restore
        if cfg.get("cleanup"):
            body[_PRODUCT_ID_KEY] = product_id
            body[_ORIGINAL_KEY] = original
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
        """按配置恢复商品原值。Restore the original product values if configured."""
        from sqlalchemy import text

        cfg = self._merge_config(case_config, global_config)
        if not cfg.get("cleanup"):
            logger.info(_("product_fixture.cleanup_skip"))
            return

        product_id = request_body.get(_PRODUCT_ID_KEY)
        original = request_body.get(_ORIGINAL_KEY)
        if product_id is None or not original:
            logger.warning(_("product_fixture.missing_meta"))
            return

        old_stock, old_status, old_deleted = original
        try:
            with self._get_connection(global_config) as conn:
                with conn.begin():
                    conn.execute(
                        text(
                            "UPDATE fm_product SET stock = :stock, status = :status, "
                            "is_delete = :deleted, edit_time = :now, update_time = :now "
                            "WHERE id = :pid"
                        ),
                        {
                            "stock": old_stock,
                            "status": old_status,
                            "deleted": old_deleted,
                            "now": common.now_str(),
                            "pid": int(product_id),
                        },
                    )
        except Exception as e:
            raise DBQueryError(
                _("product_fixture.cleanup_failed", error=e),
                processor_name=self.name,
            ) from e
        logger.info(
            _("product_fixture.restored",
              product_id=product_id, stock=old_stock,
              status=old_status, is_delete=old_deleted)
        )
