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
                return cls._tokens[cache_key], None

            token, error = cls._do_login(app_config, user_param_name)
            if error:
                cls._failed_hashes.add(fail_hash)
                return None, error

            cls._tokens[cache_key] = token
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

    @classmethod
    def clear(cls) -> None:
        """Clear all cached tokens and failed hashes (useful for testing)."""
        with cls._global_lock:
            cls._tokens.clear()
            cls._locks.clear()
            cls._failed_hashes.clear()
