"""Tests for processors.h2_dialect — JDBC connect args and jar resolution."""

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.engine.url import make_url

from processors.h2_dialect import H2Dialect


class TestJvmExitConfig:
    """验证 DB 用例退出不再阻塞（JPype destroy_jvm=False）。
    Verify DB-fixture runs no longer block exit (JPype destroy_jvm=False)."""

    def test_import_dbapi_disables_jvm_destroy_on_exit(self):
        """import_dbapi 后 JPype 退出时不等待 JVM 销毁。
        After import_dbapi, JPype no longer waits for JVM destruction on exit."""
        jpype = pytest.importorskip("jpype")
        H2Dialect.import_dbapi()
        assert jpype.config.destroy_jvm is False

    def test_dbapi_hook_disables_jvm_destroy_on_exit(self):
        """1.4 兼容钩子 dbapi() 同样设置退出配置。
        The 1.4-compat dbapi() hook also applies the exit config."""
        jpype = pytest.importorskip("jpype")
        H2Dialect.dbapi()
        assert jpype.config.destroy_jvm is False


class TestCreateConnectArgs:
    """验证 h2:// 连接串到 JDBC 参数的转换。Verify h2:// URL to JDBC args conversion."""

    def test_builds_jdbc_args_with_resolved_jar(self, tmp_path):
        jar = tmp_path / "h2-2.3.232.jar"
        jar.write_bytes(b"fake")
        url = make_url(
            "h2://sa:@localhost:9092/mem:foli_mall;"
            "MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_UPPER=false"
        )
        with patch("processors.h2_dialect.resolve_jar_path", return_value=jar):
            args, kwargs = H2Dialect().create_connect_args(url)

        assert args[0] == "org.h2.Driver"
        assert args[1] == (
            "jdbc:h2:tcp://localhost:9092/mem:foli_mall;"
            "MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_UPPER=false"
        )
        assert args[2] == {"user": "sa", "password": ""}
        assert args[3] == [str(jar)]

    def test_raises_when_jar_missing(self):
        url = make_url("h2://sa:@localhost:9092/mem:foli_mall")
        with patch("processors.h2_dialect.resolve_jar_path", return_value=None), \
             patch(
                 "processors.h2_dialect._",
                 return_value="H2 jar not found; run python tools/h2/init_h2.py",
             ):
            with pytest.raises(ImportError, match="init_h2.py"):
                H2Dialect().create_connect_args(url)
