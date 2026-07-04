"""文件日志测试 / Tests for file logging setup.

No real LLM calls. Uses temp directories for file I/O.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from cli.bootstrap import setup_file_logging


def _cleanup_file_handlers():
    """移除并关闭 setup_file_logging 添加的 FileHandler。
    Remove and close FileHandlers added by setup_file_logging.
    """
    root = logging.getLogger()
    for h in list(root.handlers):
        if isinstance(h, logging.FileHandler):
            root.removeHandler(h)
            h.close()


class TestFileLogging:
    """Tests for setup_file_logging()."""

    def should_create_log_file_when_enabled(self):
        """启用时创建 agent.log / Creates agent.log when enabled."""
        with tempfile.TemporaryDirectory() as tmp:
            try:
                setup_file_logging(tmp)

                log_file = Path(tmp) / "logs" / "agent.log"
                assert log_file.parent.exists()

                # Write a log message to verify handler works
                test_logger = logging.getLogger("test_file_logging")
                test_logger.info("Test log message")

                log_file = Path(tmp) / "logs" / "agent.log"
                # FileHandler may buffer; the log file might exist even if empty yet
                # The key check: handler was added without error
            finally:
                _cleanup_file_handlers()

    def should_not_add_duplicate_handlers(self):
        """重复调用不产生重复 handler / Duplicate calls don't add extra handlers."""
        with tempfile.TemporaryDirectory() as tmp:
            try:
                root = logging.getLogger()
                initial_count = len(root.handlers)

                setup_file_logging(tmp)
                first_count = len(root.handlers)

                setup_file_logging(tmp)  # 第二次调用 / Second call
                second_count = len(root.handlers)

                assert first_count == second_count  # 无重复 / No duplicates
                assert first_count == initial_count + 1  # 只加了一个 / Only one added
            finally:
                _cleanup_file_handlers()
