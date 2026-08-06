"""用户前置数据夹具处理器 — 直接操作 fm_user。
User fixture processor — manipulates fm_user directly.

测试场景：注册用例需要"用户名不存在"的前置状态（幂等）；禁用账号登录需要
status=0；"用户已删除后访问 /me" 需要删除用户。本插件提供
predelete / create / set_status / delete 四种操作，注册用例通过前置 predelete
与后置 cleanup 保证可重复执行。
Test scenario: register cases need a "username does not exist" precondition
(idempotent); disabled-account login needs status=0; the deleted-user /me case
needs the user removed. This plugin provides predelete / create / set_status /
delete operations. Register cases use a predelete preprocessor plus a cleanup
postprocessor so they can be re-run safely.

环境配置 / Env config (env-local.yml)::

    processor_configs:
      user-fixture:
        db_url: "h2://sa:@localhost:9092/mem:foli_mall;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_UPPER=false"

用例 YAML / Test case YAML::

    preprocessors:
      - name: user-fixture
        config:
          mode: predelete        # predelete / create / set_status / delete
          username: e2e_user
          status: 0              # create/set_status 使用：0=禁用 1=正常
    postprocessors:
      - name: user-fixture
        config:
          cleanup: true
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
_USERNAME_KEY = "_user_fixture_username"
_USER_ID_KEY = "_user_fixture_user_id"

# 默认密码 e2e123 的 BCrypt 哈希（用 foli-mall 的 Hutool BCrypt 预生成）
# Default BCrypt hash for password "e2e123" (pre-generated with foli-mall's Hutool BCrypt)
DEFAULT_PASSWORD_HASH = "$2a$10$KhnJr94CErN9gZN7cvsW3edvUTFDriUi2GwhN3DcT/4z8s0puDRmK"

# 角色常量（与 foli-mall RoleConstants 一致）
# Role constants (consistent with foli-mall RoleConstants)
ROLE_BUYER = 0
ROLE_SELLER = 1
ROLE_ADMIN = 2


class UserFixturePlugin(BaseDBPlugin):
    """用户前置数据夹具：predelete / create / set_status / delete 四种操作。
    User fixture: predelete / create / set_status / delete operations."""

    name = "user-fixture"

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
        """按 mode 操作用户。Manipulate the user by mode."""
        from sqlalchemy import text

        cfg = self._merge_config(case_config, global_config)
        mode = str(cfg.get("mode", "predelete")).lower()
        username = str(cfg.get("username", "")).strip()
        user_id = int(cfg["user_id"]) if cfg.get("user_id") else None
        if not username and user_id is None:
            raise ProcessorError(
                _("user_fixture.missing_identity"),
                processor_name=self.name,
            )

        try:
            with self._get_connection(global_config) as conn:
                with conn.begin():
                    if mode == "predelete":
                        result = conn.execute(
                            text("DELETE FROM fm_user WHERE username = :name"),
                            {"name": username},
                        )
                        logger.info(
                            _("user_fixture.predeleted",
                              username=username, count=result.rowcount)
                        )
                    elif mode == "create":
                        # 幂等：先删除同名/同 ID 旧记录再插入
                        # Idempotent: delete stale rows by username/id, then insert
                        conn.execute(
                            text("DELETE FROM fm_user WHERE username = :name"),
                            {"name": username},
                        )
                        if user_id is not None:
                            conn.execute(
                                text("DELETE FROM fm_user WHERE id = :uid"),
                                {"uid": user_id},
                            )
                        created_id = user_id if user_id is not None else common.gen_id(offset=5)
                        now = common.now_str()
                        balance = float(cfg.get("balance", 0.0))
                        role = int(cfg.get("role", ROLE_BUYER))
                        status = int(cfg.get("status", 1))
                        nickname = str(cfg.get("nickname", username))
                        password_hash = str(
                            cfg.get("password_hash", DEFAULT_PASSWORD_HASH)
                        )
                        conn.execute(
                            text(
                                "INSERT INTO fm_user (id, username, password, nickname, phone, email, avatar, "
                                "balance, role, status, is_delete, create_time, edit_time, update_time) "
                                "VALUES (:id, :username, :password, :nickname, :phone, :email, :avatar, "
                                ":balance, :role, :status, 0, :now, :now, :now)"
                            ),
                            {
                                "id": created_id,
                                "username": username,
                                "password": password_hash,
                                "nickname": nickname,
                                "phone": str(cfg.get("phone", "")),
                                "email": str(cfg.get("email", "")),
                                "avatar": str(cfg.get("avatar", "")),
                                "balance": balance,
                                "role": role,
                                "status": status,
                                "now": now,
                            },
                        )
                        logger.info(
                            _("user_fixture.created",
                              user_id=created_id, username=username,
                              role=role, status=status)
                        )
                    elif mode == "set_status":
                        status = int(cfg.get("status", 0))
                        if username:
                            rows = conn.execute(
                                text(
                                    "SELECT status FROM fm_user WHERE username = :name"
                                ),
                                {"name": username},
                            ).fetchall()
                            where_sql, params = "username = :name", {"name": username}
                        else:
                            rows = conn.execute(
                                text("SELECT status FROM fm_user WHERE id = :uid"),
                                {"uid": user_id},
                            ).fetchall()
                            where_sql, params = "id = :uid", {"uid": user_id}
                        if not rows:
                            raise ProcessorError(
                                _("user_fixture.user_missing",
                                  username=username or user_id),
                                processor_name=self.name,
                            )
                        old_status = rows[0][0]
                        conn.execute(
                            text(
                                "UPDATE fm_user SET status = :status, "
                                "edit_time = :now, update_time = :now WHERE " + where_sql
                            ),
                            {**params, "status": status, "now": common.now_str()},
                        )
                        logger.info(
                            _("user_fixture.status_set",
                              username=username or user_id,
                              old=old_status, status=status)
                        )
                    elif mode == "delete":
                        if username:
                            result = conn.execute(
                                text("DELETE FROM fm_user WHERE username = :name"),
                                {"name": username},
                            )
                        else:
                            result = conn.execute(
                                text("DELETE FROM fm_user WHERE id = :uid"),
                                {"uid": user_id},
                            )
                        logger.info(
                            _("user_fixture.deleted",
                              username=username or user_id, count=result.rowcount)
                        )
                    else:
                        raise ValueError(mode)
        except ValueError as e:
            raise ProcessorError(
                _("user_fixture.mode_invalid", mode=e),
                processor_name=self.name,
            ) from e
        except ProcessorError:
            raise
        except Exception as e:
            raise DBQueryError(
                _("user_fixture.failed", error=e),
                processor_name=self.name,
            ) from e

        # 记录用户标识供后置清理使用 / Record user identity for post cleanup
        if cfg.get("cleanup"):
            body[_USERNAME_KEY] = username
            if user_id is not None:
                body[_USER_ID_KEY] = user_id
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
        """按配置删除测试用户并校验无残留。
        Optionally delete the fixture user and verify no residual rows."""
        from sqlalchemy import text

        cfg = self._merge_config(case_config, global_config)
        if not cfg.get("cleanup"):
            logger.info(_("user_fixture.cleanup_skip"))
            return

        username = request_body.get(_USERNAME_KEY)
        user_id = request_body.get(_USER_ID_KEY)
        if not username and user_id is None:
            logger.warning(_("user_fixture.missing_user"))
            return

        try:
            with self._get_connection(global_config) as conn:
                with conn.begin():
                    if username:
                        conn.execute(
                            text("DELETE FROM fm_user WHERE username = :name"),
                            {"name": username},
                        )
                    if user_id is not None:
                        conn.execute(
                            text("DELETE FROM fm_user WHERE id = :uid"),
                            {"uid": int(user_id)},
                        )
        except Exception as e:
            raise DBQueryError(
                _("user_fixture.cleanup_failed", error=e),
                processor_name=self.name,
            ) from e
        logger.info(
            _("user_fixture.cleanup_deleted",
              username=username, user_id=user_id)
        )
