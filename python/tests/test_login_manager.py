"""Tests for auth.login_manager — user context tracking utilities.
测试 auth.login_manager 的用户上下文追踪工具方法。
"""

import threading
import time
from unittest.mock import patch

import pytest

from auth.login_manager import LoginManager


# ---------------------------------------------------------------------------
# 测试辅助：构造 app_config / Test helpers: build app_config
# ---------------------------------------------------------------------------

def _make_app_config(app_name="testApp", **extra_users):
    """构造模拟的 App 配置。Build a mock app config dict."""
    cfg = {
        "_app_name": app_name,
        "baseURL": "http://localhost:8080",
        "headTokenName": "Authorization",
        "loginPath": "/api/login",
        "loginBody": "username,password",
        "resTokenPath": "$.data.token",
        "admin": {
            "username": "admin",
            "password": "admin123",
            "user_id": 1,
            "role": "admin",
        },
        "buyer01": {
            "username": "buyer01",
            "password": "buyer123",
            "user_id": 2,
            "role": "buyer",
        },
    }
    cfg.update(extra_users)
    return cfg


# ---------------------------------------------------------------------------
# 每个测试前清理 / Clean up before each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_login_manager():
    """清理 LoginManager 状态，确保测试隔离。
    Clear LoginManager state for test isolation."""
    LoginManager.clear()
    # 也清除 thread-local / Also clear thread-local
    LoginManager._clear_current_user()
    yield
    LoginManager.clear()
    LoginManager._clear_current_user()


# ============================================================================
# TestGetCurrentUser — get_current_user() 无参方法
# ============================================================================

class TestGetCurrentUser:
    """验证 get_current_user() 在各种场景下的行为。
    Verify get_current_user() behavior under various scenarios."""

    def test_returns_none_when_no_resolution(self):
        """未解析过 #{userParamName} 时返回 None。
        Returns None when no #{userParamName} has been resolved."""
        assert LoginManager.get_current_user() is None

    def test_returns_user_config_after_resolve_token(self):
        """resolve_token() 解析 #{admin} 后，get_current_user() 返回完整用户配置。
        After resolve_token() resolves #{admin}, returns full user config."""
        app_config = _make_app_config()

        with patch.object(LoginManager, "_do_login", return_value=("fake-token", None)):
            headers = {"Authorization": "#{admin}"}
            new_headers, error = LoginManager.resolve_token(app_config, headers)

        assert error is None
        user = LoginManager.get_current_user()
        assert user is not None
        assert user["username"] == "admin"
        assert user["password"] == "admin123"
        assert user["user_id"] == 1  # 冗余字段也可获取 / extra field accessible
        assert user["role"] == "admin"  # 冗余字段也可获取 / extra field accessible

    def test_returns_user_config_on_cache_hit(self):
        """缓存命中时，get_current_user() 仍然正确返回用户配置。
        On cache hit, get_current_user() still returns correct user config."""
        app_config = _make_app_config()

        # 第一次调用：执行登录 / First call: execute login
        with patch.object(LoginManager, "_do_login", return_value=("fake-token", None)):
            headers = {"Authorization": "#{admin}"}
            LoginManager.resolve_token(app_config, headers)

        # 清除 thread-local 模拟跨用例 / Clear thread-local to simulate cross-case
        LoginManager._clear_current_user()

        # 第二次调用：缓存命中 / Second call: cache hit
        headers2 = {"Authorization": "#{admin}"}
        new_headers, error = LoginManager.resolve_token(app_config, headers2)

        assert error is None
        user = LoginManager.get_current_user()
        assert user is not None
        assert user["username"] == "admin"

    def test_returns_none_when_no_placeholder(self):
        """请求头中没有 #{...} 占位符时，get_current_user() 返回 None。
        Returns None when header has no #{...} placeholder."""
        app_config = _make_app_config()
        headers = {"Authorization": "Bearer static-token"}
        new_headers, error = LoginManager.resolve_token(app_config, headers)

        assert error is None
        assert LoginManager.get_current_user() is None

    def test_returns_none_when_no_head_token_name(self):
        """请求头中没有 headTokenName 对应的 key 时返回 None。
        Returns None when headTokenName key is not in headers."""
        app_config = _make_app_config()
        headers = {"Content-Type": "application/json"}
        new_headers, error = LoginManager.resolve_token(app_config, headers)

        assert error is None
        assert LoginManager.get_current_user() is None


# ============================================================================
# TestGetUser — get_user(user_param_name) 隐式 App 方法
# ============================================================================

class TestGetUser:
    """验证 get_user() 使用隐式 App 上下文查找用户。
    Verify get_user() uses implicit app context to look up users."""

    def test_returns_user_by_param_name(self):
        """通过 userParamName 获取当前 App 下的其他用户配置。
        Retrieve another user's config in the current app by param name."""
        app_config = _make_app_config()

        with patch.object(LoginManager, "_do_login", return_value=("fake-token", None)):
            headers = {"Authorization": "#{admin}"}
            LoginManager.resolve_token(app_config, headers)

        # 获取当前 App 下的另一个用户 / Get another user in the current app
        buyer = LoginManager.get_user("buyer01")
        assert buyer is not None
        assert buyer["username"] == "buyer01"
        assert buyer["user_id"] == 2

    def test_returns_none_for_unknown_param_name(self):
        """不存在的 userParamName 返回 None。
        Returns None for unknown user param name."""
        app_config = _make_app_config()

        with patch.object(LoginManager, "_do_login", return_value=("fake-token", None)):
            headers = {"Authorization": "#{admin}"}
            LoginManager.resolve_token(app_config, headers)

        assert LoginManager.get_user("nonexistent") is None

    def test_returns_none_when_no_app_context(self):
        """没有 App 上下文时返回 None。
        Returns None when there's no app context."""
        assert LoginManager.get_user("admin") is None


# ============================================================================
# TestGetAppUser — get_app_user(app_name, user_param_name) 显式方法
# ============================================================================

class TestGetAppUser:
    """验证 get_app_user() 完整显式查找。
    Verify get_app_user() full explicit lookup."""

    def test_returns_user_by_app_and_param_name(self, monkeypatch):
        """通过 App 名和 userParamName 显式获取用户配置。
        Explicitly retrieve user config by app name and param name."""
        app_config = _make_app_config()

        # Mock config_manager.get_app / Mock config_manager.get_app
        import config.config_manager
        monkeypatch.setattr(
            config.config_manager, "_apps",
            {"testApp": app_config},
        )
        monkeypatch.setattr(
            config.config_manager, "_initialized", True,
        )

        user = LoginManager.get_app_user("testApp", "admin")
        assert user is not None
        assert user["username"] == "admin"
        assert user["user_id"] == 1

    def test_returns_none_for_unknown_app(self, monkeypatch):
        """不存在的 App 名返回 None。
        Returns None for unknown app name."""
        import config.config_manager
        monkeypatch.setattr(config.config_manager, "_apps", {})
        monkeypatch.setattr(config.config_manager, "_initialized", True)

        assert LoginManager.get_app_user("unknownApp", "admin") is None

    def test_returns_none_for_unknown_user(self, monkeypatch):
        """不存在的 userParamName 返回 None。
        Returns None for unknown user param name."""
        app_config = _make_app_config()

        import config.config_manager
        monkeypatch.setattr(
            config.config_manager, "_apps",
            {"testApp": app_config},
        )
        monkeypatch.setattr(
            config.config_manager, "_initialized", True,
        )

        assert LoginManager.get_app_user("testApp", "nonexistent") is None

    def test_no_app_context_needed(self, monkeypatch):
        """get_app_user() 不依赖线程上下文（不需要先调用 resolve_token）。
        Does not depend on thread context (no need to call resolve_token first)."""
        app_config = _make_app_config()

        import config.config_manager
        monkeypatch.setattr(
            config.config_manager, "_apps",
            {"testApp": app_config},
        )
        monkeypatch.setattr(
            config.config_manager, "_initialized", True,
        )

        # 没有调用过 resolve_token / resolve_token was never called
        assert LoginManager.get_current_user() is None
        # 但仍然可以通过 get_app_user 查找 / But get_app_user still works
        user = LoginManager.get_app_user("testApp", "buyer01")
        assert user is not None
        assert user["username"] == "buyer01"


# ============================================================================
# TestThreadIsolation — 线程隔离
# ============================================================================

class TestThreadIsolation:
    """验证用户上下文在不同线程间隔离。
    Verify user context is isolated across threads."""

    def test_threads_do_not_cross_contaminate(self):
        """两个线程解析不同用户，互不污染。
        Two threads resolving different users do not cross-contaminate."""
        results = {}

        def thread_a():
            app_config = _make_app_config()
            with patch.object(LoginManager, "_do_login", return_value=("token-a", None)):
                headers = {"Authorization": "#{admin}"}
                LoginManager.resolve_token(app_config, headers)
            results["a"] = LoginManager.get_current_user()

        def thread_b():
            app_config = _make_app_config()
            with patch.object(LoginManager, "_do_login", return_value=("token-b", None)):
                headers = {"Authorization": "#{buyer01}"}
                LoginManager.resolve_token(app_config, headers)
            results["b"] = LoginManager.get_current_user()

        t1 = threading.Thread(target=thread_a)
        t2 = threading.Thread(target=thread_b)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # 线程 A 应拿到 admin / Thread A should get admin
        assert results["a"]["username"] == "admin"
        assert results["a"]["user_id"] == 1
        # 线程 B 应拿到 buyer01 / Thread B should get buyer01
        assert results["b"]["username"] == "buyer01"
        assert results["b"]["user_id"] == 2

    def test_cleared_between_resolve_token_calls(self):
        """同一线程中两次 resolve_token() 调用之间，上下文被正确清除和更新。
        Context is correctly cleared and updated between two resolve_token() calls
        in the same thread."""
        app_config = _make_app_config()

        # 第一次解析 / First resolution
        with patch.object(LoginManager, "_do_login", return_value=("token1", None)):
            headers1 = {"Authorization": "#{admin}"}
            LoginManager.resolve_token(app_config, headers1)

        assert LoginManager.get_current_user()["username"] == "admin"

        # 第二次解析（不同用户）/ Second resolution (different user)
        with patch.object(LoginManager, "_do_login", return_value=("token2", None)):
            headers2 = {"Authorization": "#{buyer01}"}
            LoginManager.resolve_token(app_config, headers2)

        assert LoginManager.get_current_user()["username"] == "buyer01"
