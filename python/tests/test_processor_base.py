"""Tests for processors.base — auto-registration, ProcessorError."""

import pytest

from processors.base import (
    PreProcessor,
    PostProcessor,
    ProcessorError,
    _PRE_PROCESSOR_REGISTRY,
    _POST_PROCESSOR_REGISTRY,
    _register_pre_processor,
    _register_post_processor,
)


# ---------------------------------------------------------------------------
# helpers: clean registries before each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_registries():
    _PRE_PROCESSOR_REGISTRY.clear()
    _POST_PROCESSOR_REGISTRY.clear()
    yield
    _PRE_PROCESSOR_REGISTRY.clear()
    _POST_PROCESSOR_REGISTRY.clear()


# ============================================================================
# PreProcessorRegistrationTest
# ============================================================================

class TestPreProcessorRegistrationTest:

    def should_auto_register_with_name(self):
        class MyPre(PreProcessor):
            name = "my_pre"

            def process(self, headers, body, case_config, global_config):
                return headers, body

        assert "my_pre" in _PRE_PROCESSOR_REGISTRY
        assert _PRE_PROCESSOR_REGISTRY["my_pre"] is MyPre

    def should_raise_type_error_when_name_missing(self):
        with pytest.raises(TypeError, match="must define a 'name' class attribute"):
            class BadPre(PreProcessor):  # noqa: F841
                def process(self, headers, body, case_config, global_config):
                    return headers, body

    def should_have_true_can_process_default(self):
        class SimplePre(PreProcessor):
            name = "simple"

            def process(self, headers, body, case_config, global_config):
                return headers, body

        instance = SimplePre()
        assert instance.can_process({"any": "case"}) is True
        assert instance.can_process({}) is True
        assert instance.can_process(None) is True  # type: ignore

    def should_subclass_can_override_can_process(self):
        class ConditionalPre(PreProcessor):
            name = "conditional"

            def can_process(self, case):
                return case.get("enabled", False)

            def process(self, headers, body, case_config, global_config):
                headers["X-Extra"] = "1"
                return headers, body

        instance = ConditionalPre()
        assert instance.can_process({"enabled": True}) is True
        assert instance.can_process({"enabled": False}) is False
        assert instance.can_process({}) is False


# ============================================================================
# PostProcessorRegistrationTest
# ============================================================================

class TestPostProcessorRegistrationTest:

    def should_auto_register_with_name(self):
        class MyPost(PostProcessor):
            name = "my_post"

            def process(self, request_headers, request_body, response_headers,
                        response_body, case_config, global_config):
                pass

        assert "my_post" in _POST_PROCESSOR_REGISTRY
        assert _POST_PROCESSOR_REGISTRY["my_post"] is MyPost

    def should_raise_type_error_when_name_missing(self):
        with pytest.raises(TypeError, match="must define a 'name' class attribute"):
            class BadPost(PostProcessor):  # noqa: F841
                def process(self, request_headers, request_body, response_headers,
                            response_body, case_config, global_config):
                    pass

    def should_have_true_can_process_default(self):
        """PostProcessor does not define can_process, but subclass can optionally add it."""
        # The PostProcessor base does NOT define can_process. Verify it is absent.
        assert not hasattr(PostProcessor, 'can_process')

    def should_subclass_can_override_can_process(self):
        class ConditionalPost(PostProcessor):
            name = "cond_post"

            def can_process(self, case):
                return case.get("enabled", False)

            def process(self, request_headers, request_body, response_headers,
                        response_body, case_config, global_config):
                pass

        instance = ConditionalPost()
        assert instance.can_process({"enabled": True}) is True
        assert instance.can_process({"enabled": False}) is False


# ============================================================================
# ProcessorErrorTest
# ============================================================================

class TestProcessorErrorTest:

    def should_store_message_and_processor_name(self):
        err = ProcessorError("something went wrong", processor_name="hmac_sign")
        assert err.processor_name == "hmac_sign"
        assert str(err) == "something went wrong"

    def should_have_empty_processor_name_by_default(self):
        err = ProcessorError("generic error")
        assert err.processor_name == ""

    def should_format_as_string(self):
        err = ProcessorError("token expired", processor_name="auth_pre")
        assert str(err) == "token expired"
        # repr should contain the class name
        assert "ProcessorError" in repr(err)


# ============================================================================
# Registration helper function edge cases
# ============================================================================

class TestRegistrationHelperEdgeCases:
    """Test _register_pre_processor / _register_post_processor directly."""

    def should_register_via_helper(self):
        class MyPre(PreProcessor):
            name = "helper_pre"

            def process(self, headers, body, case_config, global_config):
                return headers, body

        # Already registered via __init_subclass__, clear and test helper directly
        _PRE_PROCESSOR_REGISTRY.clear()
        _register_pre_processor(MyPre)
        assert _PRE_PROCESSOR_REGISTRY["helper_pre"] is MyPre

    def should_raise_type_error_for_empty_name(self):
        """When name is an empty string, __init_subclass__ raises TypeError."""
        _PRE_PROCESSOR_REGISTRY.clear()
        with pytest.raises(TypeError, match="must define a 'name' class attribute"):
            class EmptyNamePre(PreProcessor):  # noqa: F841
                name = ""  # type: ignore
                def process(self, headers, body, case_config, global_config):
                    return headers, body

    def should_register_multiple_preprocessors(self):
        class PreA(PreProcessor):
            name = "pre_a"

            def process(self, headers, body, case_config, global_config):
                return headers, body

        class PreB(PreProcessor):
            name = "pre_b"

            def process(self, headers, body, case_config, global_config):
                return headers, body

        assert "pre_a" in _PRE_PROCESSOR_REGISTRY
        assert "pre_b" in _PRE_PROCESSOR_REGISTRY
        assert len(_PRE_PROCESSOR_REGISTRY) == 2

    def should_register_multiple_postprocessors(self):
        class PostA(PostProcessor):
            name = "post_a"

            def process(self, request_headers, request_body, response_headers,
                        response_body, case_config, global_config):
                pass

        class PostB(PostProcessor):
            name = "post_b"

            def process(self, request_headers, request_body, response_headers,
                        response_body, case_config, global_config):
                pass

        assert "post_a" in _POST_PROCESSOR_REGISTRY
        assert "post_b" in _POST_PROCESSOR_REGISTRY
        assert len(_POST_PROCESSOR_REGISTRY) == 2
