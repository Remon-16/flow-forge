"""H2 数据库 SQLAlchemy 方言（基于 JayDeBeApi / JDBC）。
Minimal H2 SQLAlchemy dialect backed by JayDeBeApi (JDBC).

SQLAlchemy 自带方言不含 H2，且 `sqlalchemy-h2` 等第三方包不在 PyPI 上，
因此在本仓库内置一个最小方言：只负责构造 JDBC 连接参数，
供 ``BaseDBPlugin``（processors/db.py）通过 SQLAlchemy ``h2://`` URL 执行原生 SQL。

连接串示例 / Example URL::

    h2://sa:@localhost:9092/mem:foli_mall;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_UPPER=false

H2 JDBC jar 不入库，由 ``tools/h2/init_h2.py`` 下载到用户目录；
本方言通过 ``processors.h2_support.resolve_jar_path()`` 自动探测并加载，无需手工设置 CLASSPATH。

The H2 JDBC jar is not committed; ``tools/h2/init_h2.py`` downloads it to a user
directory. This dialect auto-detects and loads it via
``processors.h2_support.resolve_jar_path()`` without manual CLASSPATH setup.
"""

from sqlalchemy.engine.default import DefaultDialect

from i18n import _
from processors.h2_support import resolve_jar_path


class H2Dialect(DefaultDialect):
    """最小 H2 方言：通过 jaydebeapi 连接 org.h2.Driver。"""

    name = "h2"
    driver = "jaydebeapi"

    supports_statement_cache = False
    supports_native_decimal = False
    supports_unicode_statements = True
    supports_unicode_binds = True

    @classmethod
    def import_dbapi(cls):
        """SQLAlchemy 2.x 方言钩子：返回 DBAPI 模块。
        SQLAlchemy 2.x dialect hook: return the DBAPI module."""
        import jaydebeapi

        return jaydebeapi

    @classmethod
    def dbapi(cls):
        """SQLAlchemy 1.4 方言钩子：返回 DBAPI 模块。
        SQLAlchemy 1.4 dialect hook: return the DBAPI module."""
        import jaydebeapi

        return jaydebeapi

    def create_connect_args(self, url):
        host = url.host or "localhost"
        port = url.port or 9092
        database = url.database or "mem:foli_mall"
        jar_path = resolve_jar_path()
        if jar_path is None:
            raise ImportError(_("h2.jar.not_found"))
        jdbc_url = "jdbc:h2:tcp://%s:%s/%s" % (host, port, database)
        driver_args = {
            "user": url.username or "sa",
            "password": url.password or "",
        }
        # jaydebeapi.connect(jclassname, url, driver_args, jars)
        return (["org.h2.Driver", jdbc_url, driver_args, [str(jar_path)]], {})

    def on_connect(self):
        """关闭 JDBC 自动提交，使 ``conn.begin()`` / commit / rollback 语义生效。
        Disable JDBC auto-commit (via the raw Java Connection) so transaction
        semantics work correctly.
        """

        def set_autocommit_off(dbapi_conn):
            try:
                # jaydebeapi 未直接暴露 setAutoCommit，使用底层 Java Connection
                # jaydebeapi does not expose setAutoCommit; use the raw Java Connection
                dbapi_conn.jconn.setAutoCommit(False)
            except Exception:
                pass

        return set_autocommit_off
