"""Tests for plugins.base — PluginDeclaration and CaseAttributeGenerator."""

import pytest

from plugins.base import CaseAttributeGenerator, PluginDeclaration


class TestPluginDeclaration:
    """Tests for PluginDeclaration dataclass."""

    def should_have_default_values(self):
        d = PluginDeclaration(plugin_name="test")
        assert d.plugin_name == "test"
        assert d.attributes == []
        assert d.applies_to_single is True
        assert d.applies_to_biz is True
        assert d.max_retries == 1
        assert d.error_strategy == "skip"

    def should_set_custom_values(self):
        d = PluginDeclaration(
            plugin_name="custom",
            attributes=["preprocessors", "postprocessors"],
            applies_to_single=True,
            applies_to_biz=False,
            max_retries=5,
            error_strategy="fail",
        )
        assert d.plugin_name == "custom"
        assert d.attributes == ["preprocessors", "postprocessors"]
        assert d.applies_to_single is True
        assert d.applies_to_biz is False
        assert d.max_retries == 5
        assert d.error_strategy == "fail"

    def should_accept_warn_error_strategy(self):
        d = PluginDeclaration(plugin_name="w", error_strategy="warn")
        assert d.error_strategy == "warn"


class TestCaseAttributeGenerator:
    """Tests for CaseAttributeGenerator ABC."""

    def should_not_instantiate_without_declaration(self):
        with pytest.raises(TypeError):
            CaseAttributeGenerator()  # type: ignore[abstract]

    def should_instantiate_with_declaration(self):
        class Concrete(CaseAttributeGenerator):
            @property
            def declaration(self):
                return PluginDeclaration(plugin_name="concrete")

            def generate(self, cases, interfaces, api_summary, api_doc_text):
                return cases

        inst = Concrete()
        assert inst.declaration.plugin_name == "concrete"
        assert inst.validate({}) == []

    def should_validate_return_empty_list_by_default(self):
        class Concrete(CaseAttributeGenerator):
            @property
            def declaration(self):
                return PluginDeclaration(plugin_name="concrete")

            def generate(self, cases, interfaces, api_summary, api_doc_text):
                return cases

        inst = Concrete()
        assert inst.validate({"foo": "bar"}) == []

    def should_allow_custom_validate(self):
        class Concrete(CaseAttributeGenerator):
            @property
            def declaration(self):
                return PluginDeclaration(plugin_name="concrete")

            def generate(self, cases, interfaces, api_summary, api_doc_text):
                return cases

            def validate(self, case):
                return ["error"] if "bad" in case else []

        inst = Concrete()
        assert inst.validate({"good": True}) == []
        assert inst.validate({"bad": True}) == ["error"]
