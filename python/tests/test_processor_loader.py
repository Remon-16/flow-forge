"""Tests for processors.loader — discover_processors()."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestDiscoverProcessorsTest:

    @pytest.fixture(autouse=True)
    def _reset_discovered_flag(self):
        """Reset the _DISCOVERED flag before and after each test."""
        import processors.loader as loader_module
        loader_module._DISCOVERED = False
        yield
        loader_module._DISCOVERED = False

    @staticmethod
    def _make_mock_py_file(name):
        """Create a mock Path that looks like a .py file in a processors dir."""
        p = MagicMock(spec=Path)
        p.is_dir.return_value = True  # the root is a dir
        p.stem = name
        p.suffix = ".py"
        p.name = f"{name}.py"
        # Mock relative_to to return a simple relative path
        p.relative_to.return_value = Path(f"processors/{name}.py")
        p.with_suffix.return_value = Path(f"processors/{name}")
        # 让 mock 可被真实 sorted() 排序（按文件名）；MagicMock 调用魔术方法会传 self，故用 2 参签名。
        # Make the mock orderable for the real sorted() (by file name); MagicMock passes
        # `self` when invoking magic methods, hence the two-argument lambda.
        p.__lt__ = lambda self, other: self.name < other.name
        return p

    def should_import_valid_processor_modules(self):
        """discover_processors should import valid .py modules."""
        mock_module = MagicMock()
        mock_module.__name__ = "processors.hmac_sign"

        valid_file = self._make_mock_py_file("hmac_sign")
        root = MagicMock(spec=Path)

        with patch.object(Path, "glob", return_value=[valid_file]), \
             patch("importlib.import_module", return_value=mock_module) as mock_import, \
             patch.object(Path, "is_dir", return_value=True):
            from processors.loader import discover_processors
            discover_processors("mock_dir")

        # One call for the discovered module, one for processors.builtin
        assert mock_import.call_count >= 1
        called_name = mock_import.call_args_list[0][0][0]
        assert "hmac_sign" in called_name

    def should_skip_internal_modules(self):
        """Internal modules (base, loader, runner) should be skipped."""
        mock_module = MagicMock()

        # Create mock files for both internal and valid modules
        base_file = self._make_mock_py_file("base")
        loader_file = self._make_mock_py_file("loader")
        runner_file = self._make_mock_py_file("runner")
        init_file = self._make_mock_py_file("__init__")
        valid_file = self._make_mock_py_file("hmac_sign")

        all_files = [base_file, loader_file, runner_file, init_file, valid_file]

        with patch.object(Path, "glob", return_value=all_files), \
             patch("importlib.import_module", return_value=mock_module) as mock_import, \
             patch.object(Path, "is_dir", return_value=True):
            from processors.loader import discover_processors
            discover_processors("mock_dir")

        # Only hmac_sign should be imported from file scan (plus builtin package)
        non_builtin_calls = [
            c for c in mock_import.call_args_list
            if "hmac_sign" in str(c) or "base" in str(c[0][0])
        ]
        assert len(non_builtin_calls) == 1
        called_name = non_builtin_calls[0][0][0]
        assert "hmac_sign" in called_name
        assert "base" not in called_name

    def should_be_idempotent(self):
        """Second call to discover_processors should be a no-op."""
        mock_module = MagicMock()
        valid_file = self._make_mock_py_file("my_processor")

        with patch.object(Path, "glob", return_value=[valid_file]), \
             patch("importlib.import_module", return_value=mock_module) as mock_import, \
             patch.object(Path, "is_dir", return_value=True):
            from processors.loader import discover_processors

            discover_processors("mock_dir")
            first_call_count = mock_import.call_count

            discover_processors("mock_dir")
            second_call_count = mock_import.call_count

        assert first_call_count >= 1
        assert second_call_count == first_call_count  # unchanged — no-op

    def should_handle_import_error(self):
        """A module with a syntax/import error should not crash discovery."""
        bad_module = self._make_mock_py_file("bad_module")

        def failing_import(name):
            raise SyntaxError("syntax error in module")

        with patch.object(Path, "glob", return_value=[bad_module]), \
             patch("importlib.import_module", side_effect=failing_import), \
             patch.object(Path, "is_dir", return_value=True):
            from processors.loader import discover_processors

            # Should not raise
            discover_processors("mock_dir")

        # _DISCOVERED should still be True (we tried)
        import processors.loader as loader_module
        assert loader_module._DISCOVERED is True

    def should_handle_nonexistent_directory(self):
        """When directory doesn't exist, log debug and set _DISCOVERED=True gracefully."""
        with patch.object(Path, "is_dir", return_value=False):
            from processors.loader import discover_processors

            # Should not raise
            discover_processors("nonexistent_dir")

        import processors.loader as loader_module
        assert loader_module._DISCOVERED is True

    def should_handle_empty_directory(self):
        """Empty directory should not crash."""
        with patch.object(Path, "glob", return_value=[]), \
             patch.object(Path, "is_dir", return_value=True):
            from processors.loader import discover_processors

            # Should not raise
            discover_processors("mock_empty_dir")

        import processors.loader as loader_module
        assert loader_module._DISCOVERED is True

    def should_use_default_directory_when_none_provided(self):
        """When no directory is provided, default to the loader's own directory."""
        mock_module = MagicMock()
        valid_file = self._make_mock_py_file("test_mod")

        with patch.object(Path, "glob", return_value=[valid_file]), \
             patch("importlib.import_module", return_value=mock_module) as mock_import:
            from processors.loader import discover_processors

            # Should not crash; the default path is the processors/ dir
            discover_processors()
            # import_module should have been called at least once
            assert mock_import.call_count >= 1

        import processors.loader as loader_module
        assert loader_module._DISCOVERED is True
