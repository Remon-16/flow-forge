import hashlib
import logging
import threading
from typing import Any, Dict, Optional, Tuple

import requests

from resolvers.path_resolver import resolve_path, _Missing
from resolvers.var_resolver import resolve_placeholders, has_placeholders

logger = logging.getLogger(__name__)


class LoginManager:
    """Thread-safe login state manager with fine-grained per-user locking."""

    _tokens: Dict[str, str] = {}
    _locks: Dict[str, threading.Lock] = {}
    _failed_hashes: set = set()
    _global_lock = threading.Lock()

    # 线程局部存储：记录当前解析的用户上下文，供插件通过 get_current_user() 获取
    # Thread-local storage: records the currently resolved user context for
    # plugins to retrieve via get_current_user()
    _tls = threading.local()

    @classmethod
    def resolve_token(
        cls, app_config: Dict[str, Any], headers: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Resolve #{userParamName} placeholders in headers.

        Supports both whole-value placeholders (``"#{userParamName}"``) and
        embedded placeholders (``"Bearer #{userParamName}"``).  Each
        placeholder is independently resolved via login or cache.

        Returns (updated_headers, error_msg).  error_msg is None on success.
        """
        # 每次解析前先清除线程上下文，防止跨用例状态泄漏
        # Clear thread-local context before each resolution to prevent cross-case state leakage
        cls._clear_current_user()

        if not app_config or not headers:
            return headers, None

        head_token_name = app_config.get("headTokenName")
        if not head_token_name or head_token_name not in headers:
            return headers, None

        token_value = headers[head_token_name]
        if not isinstance(token_value, str):
            return headers, None

        if not has_placeholders(token_value):
            return headers, None

        def token_resolver(var_name: str) -> Optional[str]:
            token, error = cls._get_or_login(app_config, var_name)
            if error:
                logger.warning("Token resolution failed for '%s': %s", var_name, error)
                return None
            return token

        resolved_value = resolve_placeholders(token_value, token_resolver)
        if resolved_value == token_value:
            return headers, None

        headers = dict(headers)
        headers[head_token_name] = resolved_value
        return headers, None

    @classmethod
    def _get_or_login(
        cls, app_config: Dict[str, Any], user_param_name: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Get cached token or perform login. Returns (token, error)."""
        app_name = app_config.get("_app_name", "unknown")
        cache_key = f"{app_name}:{user_param_name}"
        fail_hash = cls._make_hash(app_name, user_param_name)

        if fail_hash in cls._failed_hashes:
            return None, f"Login previously failed for '{user_param_name}' in app '{app_name}' — skipping"

        lock = cls._get_lock(cache_key)
        with lock:
            if cache_key in cls._tokens:
                logger.debug("Token cache hit for %s", cache_key)
                cls._record_current_user(app_config, user_param_name)
                return cls._tokens[cache_key], None

            token, error = cls._do_login(app_config, user_param_name)
            if error:
                cls._failed_hashes.add(fail_hash)
                return None, error

            cls._tokens[cache_key] = token
            cls._record_current_user(app_config, user_param_name)
            logger.info("Token cached for %s", cache_key)
            return token, None

    @classmethod
    def _do_login(
        cls, app_config: Dict[str, Any], user_param_name: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Execute login API call and extract token from response."""
        base_url = app_config.get("baseURL", "")
        login_path = app_config.get("loginPath", "")
        login_body_fields = app_config.get("loginBody", "")
        res_token_path = app_config.get("resTokenPath", "")

        user_config = app_config.get(user_param_name)
        if not user_config:
            return None, f"User config '{user_param_name}' not found in app config"

        body_field_names = [f.strip() for f in login_body_fields.split(",") if f.strip()]
        login_body = {}
        for field_name in body_field_names:
            login_body[field_name] = user_config.get(field_name, "")

        url = f"{base_url.rstrip('/')}/{login_path.lstrip('/')}"
        logger.info("Logging in user '%s' at %s", user_param_name, url)

        try:
            resp = requests.post(url, json=login_body, timeout=30)
        except requests.RequestException as e:
            return None, f"Login request failed for '{user_param_name}': {e}"

        if resp.status_code != 200:
            return None, (
                f"Login returned status {resp.status_code} for '{user_param_name}'"
            )

        token = cls._extract_value(resp, res_token_path)
        if token is None:
            return None, (
                f"Token path '{res_token_path}' not found in login response for '{user_param_name}'"
            )

        return str(token), None

    @classmethod
    def _extract_value(cls, response: requests.Response, path: str) -> Any:
        if not path:
            return None
        try:
            data = response.json()
        except (ValueError, requests.JSONDecodeError):
            return None
        try:
            result = resolve_path(data, path)
            return None if isinstance(result, _Missing) else result
        except Exception:
            return None

    @classmethod
    def _get_lock(cls, cache_key: str) -> threading.Lock:
        with cls._global_lock:
            if cache_key not in cls._locks:
                cls._locks[cache_key] = threading.Lock()
            return cls._locks[cache_key]

    @staticmethod
    def _make_hash(app_name: str, user_param_name: str) -> str:
        raw = f"{app_name}:{user_param_name}"
        return hashlib.md5(raw.encode()).hexdigest()

    # ── 用户上下文追踪 / User context tracking ──────────────────────────

    @classmethod
    def _record_current_user(
        cls, app_config: Dict[str, Any], user_param_name: str
    ) -> None:
        """记录当前解析的用户上下文到线程局部存储。
        Store the resolved user context in thread-local storage.

        插件可通过 get_current_user() / get_user() / get_app_user() 获取。
        Plugins can retrieve this via get_current_user() / get_user() / get_app_user().
        """
        cls._tls.app_name = app_config.get("_app_name", "unknown")
        cls._tls.user_param_name = user_param_name
        cls._tls.app_config = app_config

    @classmethod
    def _clear_current_user(cls) -> None:
        """清除线程局部存储中的用户上下文。
        Clear thread-local user context.

        在 resolve_token() 开头调用，防止跨用例的状态泄漏。
        Called at the start of resolve_token() to prevent cross-case state leakage.
        """
        cls._tls.app_name = None
        cls._tls.user_param_name = None
        cls._tls.app_config = None

    @classmethod
    def get_current_user(cls) -> Optional[Dict[str, Any]]:
        """获取当前线程最近通过 #{} 语法解析的用户完整配置。
        Return the full user config dict for the most recently resolved
        #{userParamName} in the current thread.

        无需入参，自动返回当前登录用户的所有字段（含冗余字段如 user_id、role）。
        No arguments needed — returns all fields (including extra fields like
        user_id, role) of the currently logged-in user.

        未解析过 #{userParamName} 时返回 None。
        Returns None if no #{userParamName} has been resolved in this thread.
        """
        app_config = getattr(cls._tls, 'app_config', None)
        user_param_name = getattr(cls._tls, 'user_param_name', None)
        if app_config is None or user_param_name is None:
            return None
        return app_config.get(user_param_name)

    @classmethod
    def get_user(cls, user_param_name: str) -> Optional[Dict[str, Any]]:
        """获取当前 App 下指定用户名的配置。
        Return the user config for *user_param_name* within the current app.

        使用隐式的当前 app_name（从线程局部存储获取），只需提供 userParamName。
        Uses the implicit current app_name from thread-local state;
        only *user_param_name* is required.

        当前无 App 上下文或用户名不存在时返回 None。
        Returns None if no app context is available or the name is not found.
        """
        app_config = getattr(cls._tls, 'app_config', None)
        if app_config is None:
            return None
        return app_config.get(user_param_name)

    @classmethod
    def get_app_user(
        cls, app_name: str, user_param_name: str
    ) -> Optional[Dict[str, Any]]:
        """获取指定 App 下指定用户名的配置（完整显式查找）。
        Return the user config for *user_param_name* in a specific app.

        通过 config_manager 做完整查找，不依赖线程上下文。
        Full explicit lookup via config_manager; does not rely on thread context.

        App 或用户名不存在时返回 None。
        Returns None if the app or user is not found.
        """
        from config.config_manager import get_app
        app_config = get_app(app_name)
        if app_config is None:
            return None
        return app_config.get(user_param_name)

    @classmethod
    def clear(cls) -> None:
        """Clear all cached tokens and failed hashes (useful for testing)."""
        with cls._global_lock:
            cls._tokens.clear()
            cls._locks.clear()
            cls._failed_hashes.clear()
