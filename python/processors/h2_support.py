"""H2 JDBC 支持工具：jar 定位、下载与校验。
H2 JDBC support utilities: jar resolution, download and verification.

CLI（tools/h2/init_h2.py）与 SQLAlchemy 方言（processors/h2_dialect.py）共用本模块，
避免重复实现下载、校验与路径探测逻辑。

Shared by the CLI (tools/h2/init_h2.py) and the SQLAlchemy dialect
(processors/h2_dialect.py) to avoid duplicating download/verify/resolve logic.

jar 不提交到仓库，由 CLI 下载到用户目录；方言在连接时按固定顺序自动探测。
The jar is not committed to the repository; the CLI downloads it to a user
directory, and the dialect probes well-known locations when connecting.
"""

import hashlib
import logging
import os
import shutil
import urllib.request
from pathlib import Path
from typing import Optional

from i18n import _

logger = logging.getLogger(__name__)

# H2 版本，与 foli-mall（Spring Boot 3.5.4 BOM）管理版本保持一致。
# Keep in sync with the H2 version managed by foli-mall (Spring Boot 3.5.4 BOM).
H2_VERSION = "2.3.232"

# h2-2.3.232.jar 的 SHA-256（来自 Maven Central 官方构件）。
# SHA-256 of h2-2.3.232.jar (official artifact from Maven Central).
H2_JAR_SHA256 = "8dae62d22db8982c3dcb3826edb9c727c5d302063a67eef7d63d82de401f07d3"

H2_JAR_FILENAME = "h2-%s.jar" % H2_VERSION

# 默认 jar 存放目录（用户主目录下，跨平台）。
# Default jar directory (under the user home, cross-platform).
DEFAULT_H2_DIR = Path.home() / ".flow-forge" / "h2"

# Maven Central 官方下载地址。
# Official download URL on Maven Central.
MAVEN_CENTRAL_URL = (
    "https://repo1.maven.org/maven2/com/h2database/h2/%s/%s"
    % (H2_VERSION, H2_JAR_FILENAME)
)

# 阿里云镜像下载地址（Maven Central 不可达时的备选）。
# Aliyun mirror URL (fallback when Maven Central is unreachable).
ALIYUN_MIRROR_URL = (
    "https://maven.aliyun.com/repository/central/com/h2database/h2/%s/%s"
    % (H2_VERSION, H2_JAR_FILENAME)
)

# 环境变量名称 / Environment variable names
ENV_JAR_PATH = "H2_JAR_PATH"
ENV_JAR_DIR = "H2_JAR_DIR"


def default_jar_path() -> Path:
    """返回默认目录下的 jar 路径。Return the jar path under the default directory."""
    return DEFAULT_H2_DIR / H2_JAR_FILENAME


def _legacy_tools_jar_path() -> Optional[Path]:
    """兼容旧位置：仓库 tools/h2/ 下的 jar（存在才返回）。
    Legacy fallback: the jar under the repo tools/h2/ directory (only if present)."""
    legacy = Path(__file__).resolve().parents[2] / "tools" / "h2" / H2_JAR_FILENAME
    return legacy if legacy.is_file() else None


def resolve_jar_path() -> Optional[Path]:
    """按顺序探测 H2 JDBC jar 的路径，找不到返回 None。

    Resolve the H2 JDBC jar path, probing in order; return None if not found.

    探测顺序 / Probing order:
      1. H2_JAR_PATH 环境变量（完整文件路径）/ env var H2_JAR_PATH (full file path)
      2. H2_JAR_DIR 环境变量（目录）/ env var H2_JAR_DIR (directory)
      3. 默认目录 ~/.flow-forge/h2/ / the default directory ~/.flow-forge/h2/
      4. 仓库旧位置 tools/h2/（向后兼容）/ legacy repo location tools/h2/ (backward compatible)
    """
    candidates = []

    jar_path_env = os.environ.get(ENV_JAR_PATH, "").strip()
    if jar_path_env:
        candidates.append(Path(jar_path_env))

    jar_dir_env = os.environ.get(ENV_JAR_DIR, "").strip()
    if jar_dir_env:
        candidates.append(Path(jar_dir_env) / H2_JAR_FILENAME)

    candidates.append(default_jar_path())

    legacy = _legacy_tools_jar_path()
    if legacy is not None:
        candidates.append(legacy)

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    return None


def verify_sha256(jar_path: Path) -> bool:
    """计算 jar 的 SHA-256 并与内置期望值比对。
    Compute the SHA-256 of the jar and compare it with the expected value."""
    digest = hashlib.sha256()
    with open(jar_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == H2_JAR_SHA256


def download_h2_jar(dest_dir: Optional[Path] = None, force: bool = False) -> Path:
    """下载（或复用）H2 JDBC jar，返回 jar 的绝对路径。

    Download (or reuse) the H2 JDBC jar and return its absolute path.

    - 目标文件已存在且 SHA-256 校验通过时跳过下载（幂等）。
      Skips download when the target file exists and passes SHA-256 (idempotent).
    - force=True 时忽略已有文件并强制重新下载。
      force=True ignores the existing file and forces a fresh download.
    """
    dest = Path(dest_dir).expanduser() if dest_dir is not None else default_jar_path().parent
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / H2_JAR_FILENAME

    if target.is_file() and not force:
        if verify_sha256(target):
            logger.info(_("h2.jar.ready", path=str(target)))
            return target
        logger.warning(_("h2.jar.checksum_failed", path=str(target)))

    tmp_path = target.with_suffix(".jar.tmp")
    last_error = None
    try:
        for url in (MAVEN_CENTRAL_URL, ALIYUN_MIRROR_URL):
            try:
                logger.info(_("h2.jar.downloading", url=url))
                with urllib.request.urlopen(url, timeout=60) as response:
                    with open(tmp_path, "wb") as out:
                        shutil.copyfileobj(response, out)
                break
            except Exception as exc:  # noqa: BLE001 - 逐个源尝试后统一报错
                last_error = exc
                logger.warning(_("h2.jar.download_failed_try", url=url, error=str(exc)))
        else:
            raise last_error
        if not verify_sha256(tmp_path):
            raise RuntimeError(_("h2.jar.checksum_failed_download"))
        os.replace(tmp_path, target)
    finally:
        tmp_path.unlink(missing_ok=True)

    logger.info(_("h2.jar.downloaded", path=str(target)))
    return target
