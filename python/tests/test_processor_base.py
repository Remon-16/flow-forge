"""Tests for processors.base — _create_external_plugin_wrappers and _mask_password."""

import pytest

from processors.base import (
    BaseExternalPlugin,
    PreProcessor,
    PostProcessor,
    _PRE_PROCESSOR_REGISTRY,
    _POST_PROCESSOR_REGISTRY,
    _create_external_plugin_wrappers,
    _mask_password,
)


# ---------------------------------------------------------------------------
# helpers: clean registries before each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_registries():
    """清理所有注册表，确保测试隔离。Clean all registries for test isolation."""
    _PRE_PROCESSOR_REGISTRY.clear()
    _POST_PROCESSOR_REGISTRY.clear()
    yield
    _PRE_PROCESSOR_REGISTRY.clear()
    _POST_PROCESSOR_REGISTRY.clear()


# ============================================================================
# TestMaskPassword — 密码掩码（通用 URL）
# ============================================================================

class TestMaskPassword:
    """验证 _mask_password 对各种 URL 格式的密码掩码。"""

    def test_masks_redis_url(self):
        url = "redis://:secret123@localhost:6379/0"
        masked = _mask_password(url)
        assert "secret123" not in masked
        assert "***" in masked

    def test_masks_amqp_url(self):
        url = "amqp://guest:guest@localhost:5672//"
        masked = _mask_password(url)
        assert "***" in masked
        # 用户名应保留 / username should be preserved
        assert "guest" in masked

    def test_no_password_unchanged(self):
        url = "redis://localhost:6379/0"
        masked = _mask_password(url)
        assert masked == url

    def test_no_at_symbol_unchanged(self):
        url = "memory://"
        masked = _mask_password(url)
        assert masked == url


# ============================================================================
# Fake plugin for testing wrapper creation
# ============================================================================

class _FakePlugin:
    """模拟外部插件基类。Fake plugin base class for testing."""
    name = "fake-plugin"

    def can_process(self, case):
        return True

    def before_request(self, headers, body, case_config, global_config):
        body["from_plugin"] = True
        return headers, body

    def after_response(self, request_headers, request_body, response_headers,
                       response_body, case_config, global_config):
        pass


class TestCreateExternalPluginWrappers:
    """验证 _create_external_plugin_wrappers 的行为。"""

    def test_registers_in_custom_registry(self):
        """插件类被注册到传入的自定义 registry 中。"""
        fake_registry = {}
        _create_external_plugin_wrappers(_FakePlugin, fake_registry)
        assert "fake-plugin" in fake_registry
        assert fake_registry["fake-plugin"] is _FakePlugin

    def test_creates_pre_processor_wrapper(self):
        """自动创建 PreProcessor 包装类并注册到全局 _PRE_PROCESSOR_REGISTRY。"""
        fake_registry = {}
        _create_external_plugin_wrappers(_FakePlugin, fake_registry)
        assert "fake-plugin" in _PRE_PROCESSOR_REGISTRY
        wrapper_cls = _PRE_PROCESSOR_REGISTRY["fake-plugin"]
        assert issubclass(wrapper_cls, PreProcessor)

    def test_creates_post_processor_wrapper(self):
        """自动创建 PostProcessor 包装类并注册到全局 _POST_PROCESSOR_REGISTRY。"""
        fake_registry = {}
        _create_external_plugin_wrappers(_FakePlugin, fake_registry)
        assert "fake-plugin" in _POST_PROCESSOR_REGISTRY
        wrapper_cls = _POST_PROCESSOR_REGISTRY["fake-plugin"]
        assert issubclass(wrapper_cls, PostProcessor)

    def test_pre_wrapper_delegates_to_before_request(self):
        """PreProcessor 包装器的 process() 委托到 before_request()。"""
        fake_registry = {}
        _create_external_plugin_wrappers(_FakePlugin, fake_registry)
        pre_cls = _PRE_PROCESSOR_REGISTRY["fake-plugin"]
        instance = pre_cls()
        h, b = instance.process(
            {"Content-Type": "json"}, {"key": "val"}, {}, {"processor_configs": {}}
        )
        assert b["from_plugin"] is True
        assert b["key"] == "val"

    def test_post_wrapper_delegates_to_after_response(self):
        """PostProcessor 包装器的 process() 委托到 after_response()。"""
        call_log = []

        class TrackingPlugin(_FakePlugin):
            name = "tracking-plugin"

            def after_response(self, rh, rb, rsh, rsb, cc, gc):
                call_log.append(rsb)

        fake_registry = {}
        _create_external_plugin_wrappers(TrackingPlugin, fake_registry)
        post_cls = _POST_PROCESSOR_REGISTRY["tracking-plugin"]
        instance = post_cls()
        instance.process({}, {}, {}, {"result": "ok"}, {}, {"processor_configs": {}})
        assert call_log == [{"result": "ok"}]

    def test_raises_type_error_when_name_missing(self):
        """未定义 name 时抛出 TypeError。"""

        class NoNamePlugin:
            pass

        with pytest.raises(TypeError, match="must define a 'name'"):
            _create_external_plugin_wrappers(NoNamePlugin, {})

    def test_multiple_plugins_independent(self):
        """多个插件独立注册，互不干扰。"""

        class PluginA(_FakePlugin):
            name = "plugin-a"

        class PluginB(_FakePlugin):
            name = "plugin-b"

        registry = {}
        _create_external_plugin_wrappers(PluginA, registry)
        _create_external_plugin_wrappers(PluginB, registry)

        assert "plugin-a" in _PRE_PROCESSOR_REGISTRY
        assert "plugin-b" in _PRE_PROCESSOR_REGISTRY
        assert registry["plugin-a"] is PluginA
        assert registry["plugin-b"] is PluginB

    def test_can_process_delegation(self):
        """PreProcessor 包装器的 can_process 委托到插件的 can_process。"""

        class ConditionalPlugin(_FakePlugin):
            name = "conditional-plugin"

            def can_process(self, case):
                return case.get("enabled", False)

        registry = {}
        _create_external_plugin_wrappers(ConditionalPlugin, registry)
        pre_cls = _PRE_PROCESSOR_REGISTRY["conditional-plugin"]
        instance = pre_cls()
        assert instance.can_process({"enabled": True}) is True
        assert instance.can_process({"enabled": False}) is False


# ============================================================================
# TestBaseExternalPlugin — 共享基类默认行为 / Shared base class default behavior
# ============================================================================

class _MinimalPlugin(BaseExternalPlugin):
    """最小插件实现，仅定义 name，不覆写任何方法。
    Minimal plugin — only defines name, overrides no methods."""
    name = "minimal-plugin"


class _OverridePlugin(BaseExternalPlugin):
    """覆写所有扩展点的插件。Plugin that overrides all extension points."""
    name = "override-plugin"

    def can_process(self, case):
        return case.get("active", True)

    def before_request(self, headers, body, case_config, global_config):
        body["modified"] = True
        return headers, body

    def after_response(self, rh, rb, rsh, rsb, cc, gc):
        pass


class TestBaseExternalPlugin:
    """验证 BaseExternalPlugin 默认实现与 MRO 行为。
    Verify BaseExternalPlugin default implementations and MRO behavior."""

    def test_default_can_process_returns_true(self):
        """默认 can_process() 返回 True。Default can_process() returns True."""
        plugin = _MinimalPlugin()
        assert plugin.can_process({}) is True

    def test_default_before_request_returns_unchanged(self):
        """默认 before_request() 原样返回 (headers, body)。
        Default before_request() returns (headers, body) unchanged."""
        plugin = _MinimalPlugin()
        h, b = plugin.before_request(
            {"X-Test": "1"}, {"key": "val"}, {}, {"processor_configs": {}}
        )
        assert h == {"X-Test": "1"}
        assert b == {"key": "val"}

    def test_default_after_response_is_noop(self):
        """默认 after_response() 是空操作，不抛异常。
        Default after_response() is a no-op that doesn't raise."""
        plugin = _MinimalPlugin()
        # 不应抛异常 / Should not raise
        plugin.after_response({}, {}, {}, {}, {}, {})

    def test_can_override_can_process(self):
        """子类可以覆写 can_process()。Subclass can override can_process()."""
        plugin = _OverridePlugin()
        assert plugin.can_process({"active": True}) is True
        assert plugin.can_process({"active": False}) is False

    def test_can_override_before_request(self):
        """子类可以覆写 before_request()。Subclass can override before_request()."""
        plugin = _OverridePlugin()
        h, b = plugin.before_request(
            {}, {"key": "val"}, {}, {"processor_configs": {}}
        )
        assert b["modified"] is True
        assert b["key"] == "val"

    def test_mro_resolves_to_subclass_first(self):
        """MRO 优先使用子类覆写的方法。
        MRO resolves to subclass override first."""
        plugin = _OverridePlugin()
        # can_process 被覆写 / can_process is overridden
        assert plugin.can_process({}) is True  # active not in dict → defaults True

    def test_name_must_be_defined(self):
        """BaseExternalPlugin 声明了 name 但需子类赋值。
        BaseExternalPlugin declares name but subclass must assign it."""
        assert _MinimalPlugin.name == "minimal-plugin"
        assert _OverridePlugin.name == "override-plugin"
