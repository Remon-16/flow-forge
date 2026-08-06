"""余额前置数据夹具处理器 — 直接更新 fm_user.balance。
Balance fixture processor — updates fm_user.balance directly.

测试场景：余额不足支付（205001）需要把买家余额调到很低；测试完成后又需要恢复
原余额。本插件一次 UPDATE 即可完成设置，repeatable。
Test scenario: insufficient-balance cases (205001) need a low buyer balance, and
the balance should be restored afterwards. This plugin sets it in one UPDATE.

环境配置 / Env config (env-local.yml)::

    processor_configs:
      balance-fixture:
        db_url: "h2://sa:@localhost:9092/mem:foli_mall;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_UPPER=false"
        test_buyer_id: "1000000000000000007"

用例 YAML / Test case YAML::

    preprocessors:
      - name: balance-fixture
        config:
          balance: 0.01           # 设为 0.01 模拟余额不足；恢复时再设回 10000
"""

import logging
from typing import Any, Dict, Tuple

from i18n import _
from auth.login_manager import LoginManager
from processors.base import ProcessorError
from processors.builtin.db import _fixtures_common as common
from processors.db import BaseDBPlugin, DBQueryError

logger = logging.getLogger(__name__)


class BalanceFixturePlugin(BaseDBPlugin):
    """余额前置数据夹具。Balance fixture."""

    name = "balance-fixture"

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
        """设置用户余额。Set the user balance."""
        from sqlalchemy import text

        cfg = self._merge_config(case_config, global_config)
        user_id = int(
            common.resolve_user_id(
                LoginManager.get_current_user(),
                cfg.get("test_buyer_id", common.SEED_BUYER_ID),
            )
        )
        balance = float(cfg.get("balance", 10000.0))

        try:
            with self._get_connection(global_config) as conn:
                with conn.begin():
                    rows = conn.execute(
                        text("SELECT balance FROM fm_user WHERE id = :uid"),
                        {"uid": user_id},
                    ).fetchall()
                    if not rows:
                        raise ProcessorError(
                            _("balance_fixture.user_not_found", user=user_id),
                            processor_name=self.name,
                        )
                    old_balance = rows[0][0]
                    conn.execute(
                        text("UPDATE fm_user SET balance = :bal WHERE id = :uid"),
                        {"bal": balance, "uid": user_id},
                    )
        except Exception as e:
            raise DBQueryError(
                _("balance_fixture.failed", error=e),
                processor_name=self.name,
            ) from e

        logger.info(
            _("balance_fixture.set", user=user_id, old=old_balance, balance=balance)
        )
        return headers, body
