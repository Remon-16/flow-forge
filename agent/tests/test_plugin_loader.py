"""Tests for plugin loader — load_user_plugins() and load_all_plugins().

All imports are mocked — NO real modules are loaded.
"""

from unittest.mock import MagicMock, patch

import pytest

from plugins.base import CaseAttributeGenerator, PluginDeclaration
from plugins.loader import load_all_plugins, load_user_plugins


# ---------------------------------------------------------------------------
# Concrete plugin classes for testing
# ---------------------------------------------------------------------------

class _ValidPlugin(CaseAttributeGenerator):
    """A well-formed plugin that accepts (settings, knowledge)."""

    def __init__(self, settings=None, knowledge=None):
        self._settings = settings
        self._knowledge = knowledge
        self._guidance = ""

    @property
    def declaration(self):
        return PluginDeclaration(
            plugin_name="test_valid",
            applies_to_single=True,
            applies_to_biz=False,
        )

    def generate(self, cases, interfaces, api_summary, api_doc_text):
        return cases

    def set_user_guidance(self, guidance: str):
        self._guidance = guidance


class _PluginNoSettings(CaseAttributeGenerator):
    """A plugin whose constructor takes no arguments."""

    def __init__(self):
        pass

    @property
    def declaration(self):
        return PluginDeclaration(plugin_name="test_no_args")

    def generate(self, cases, interfaces, api_summary, api_doc_text):
        return cases


class _PluginWithoutGuidance(CaseAttributeGenerator):
    """A plugin without set_user_guidance method."""

    def __init__(self, settings=None, knowledge=None):
        pass

    @property
    def declaration(self):
        return PluginDeclaration(plugin_name="test_no_guidance")

    def generate(self, cases, interfaces, api_summary, api_doc_text):
        return cases


class _NotASubclass:
    """A class that is found in a module but does NOT extend CaseAttributeGenerator."""

    def __init__(self):
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _ModuleStub:
    """A plain object used as a fake module — does NOT auto-create attributes
    like MagicMock does, so getattr(mod, name, None) correctly returns None
    when the attribute was never set."""

    pass


def _make_mock_module(cls):
    """Create a mock module that exposes *cls* as an attribute."""
    mod = _ModuleStub()
    setattr(mod, cls.__name__, cls)
    return mod


# ---------------------------------------------------------------------------
# PluginLoaderTest
# ---------------------------------------------------------------------------

class PluginLoaderTest:
    """Tests for load_user_plugins() and load_all_plugins()."""

    def should_load_valid_plugin(self):
        mock_mod = _make_mock_module(_ValidPlugin)

        with patch("plugins.loader.importlib.import_module", return_value=mock_mod):
            plugins = load_user_plugins(
                module_paths=["mypackage.plugins._ValidPlugin"],
            )

        assert len(plugins) == 1
        assert isinstance(plugins[0], _ValidPlugin)
        assert plugins[0].declaration.plugin_name == "test_valid"

    def should_skip_empty_module_path(self):
        with patch("plugins.loader.importlib.import_module") as mock_import:
            plugins = load_user_plugins(module_paths=["  ", ""])

        assert plugins == []
        mock_import.assert_not_called()

    def should_skip_missing_class_in_module(self):
        # _ModuleStub does NOT auto-create attributes, so getattr with
        # a missing name returns None, triggering the "continue" in the loader.
        mock_mod = _ModuleStub()

        with patch("plugins.loader.importlib.import_module", return_value=mock_mod):
            # Use a class name that won't be found on the stub
            plugins = load_user_plugins(
                module_paths=["mypackage.plugins.MissingClass"],
            )

        assert plugins == []

    def should_skip_non_subclass(self):
        mock_mod = _make_mock_module(_NotASubclass)

        with patch("plugins.loader.importlib.import_module", return_value=mock_mod):
            plugins = load_user_plugins(
                module_paths=["mypackage.plugins._NotASubclass"],
            )

        assert plugins == []

    def should_skip_import_error(self):
        with patch(
            "plugins.loader.importlib.import_module",
            side_effect=ImportError("No module named 'nonexistent'"),
        ):
            plugins = load_user_plugins(
                module_paths=["nonexistent.module.SomeClass"],
            )

        assert plugins == []

    def should_instantiate_with_settings_and_knowledge(self):
        mock_mod = _make_mock_module(_ValidPlugin)

        with patch("plugins.loader.importlib.import_module", return_value=mock_mod):
            settings = MagicMock(name="settings")
            knowledge = MagicMock(name="knowledge")
            plugins = load_user_plugins(
                module_paths=["pkg._ValidPlugin"],
                settings=settings,
                knowledge=knowledge,
            )

        assert len(plugins) == 1
        assert plugins[0]._settings is settings
        assert plugins[0]._knowledge is knowledge

    def should_fallback_to_no_arg_constructor(self):
        mock_mod = _make_mock_module(_PluginNoSettings)

        with patch("plugins.loader.importlib.import_module", return_value=mock_mod):
            settings = MagicMock(name="settings")
            plugins = load_user_plugins(
                module_paths=["pkg._PluginNoSettings"],
                settings=settings,
            )

        assert len(plugins) == 1
        assert isinstance(plugins[0], _PluginNoSettings)

    def should_return_empty_for_empty_paths(self):
        assert load_user_plugins(module_paths=[]) == []
        assert load_user_plugins(module_paths=[], settings=MagicMock()) == []

    def should_preserve_plugin_order(self):
        mod_a = _make_mock_module(_ValidPlugin)

        class _PluginB(CaseAttributeGenerator):
            def __init__(self, settings=None, knowledge=None):
                pass

            @property
            def declaration(self):
                return PluginDeclaration(plugin_name="plugin_b")

            def generate(self, cases, interfaces, api_summary, api_doc_text):
                return cases

        mod_b = _make_mock_module(_PluginB)

        import_responses = {
            "pkg_a": mod_a,
            "pkg_b": mod_b,
        }

        def _mock_import(module_path):
            return import_responses.get(module_path, MagicMock())

        with patch("plugins.loader.importlib.import_module", side_effect=_mock_import):
            plugins = load_user_plugins(
                module_paths=["pkg_a._ValidPlugin", "pkg_b._PluginB"],
            )

        assert len(plugins) == 2
        assert plugins[0].declaration.plugin_name == "test_valid"
        assert plugins[1].declaration.plugin_name == "plugin_b"

    def should_set_user_guidance_on_plugins(self):
        """load_all_plugins should call set_user_guidance on each plugin."""
        mock_mod = _make_mock_module(_ValidPlugin)

        with patch("plugins.loader.importlib.import_module", return_value=mock_mod):
            plugins = load_all_plugins(
                settings=MagicMock(),
                user_module_paths=["pkg._ValidPlugin"],
                user_guidance="Use HMAC signing",
            )

        assert len(plugins) == 1
        assert plugins[0]._guidance == "Use HMAC signing"

    def should_skip_user_guidance_if_no_method(self):
        """Plugins without set_user_guidance should not crash."""
        mock_mod = _make_mock_module(_PluginWithoutGuidance)

        with patch("plugins.loader.importlib.import_module", return_value=mock_mod):
            plugins = load_all_plugins(
                settings=MagicMock(),
                user_module_paths=["pkg._PluginWithoutGuidance"],
                user_guidance="Some guidance",
            )

        assert len(plugins) == 1
        assert isinstance(plugins[0], _PluginWithoutGuidance)
