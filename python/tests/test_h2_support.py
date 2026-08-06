"""Tests for processors.h2_support — jar resolution, verification and download."""

import hashlib
import io
from pathlib import Path
from unittest.mock import patch

import pytest

from processors import h2_support
from processors.h2_support import (
    ENV_JAR_DIR,
    ENV_JAR_PATH,
    H2_JAR_FILENAME,
    download_h2_jar,
    resolve_jar_path,
    verify_sha256,
)


class TestResolveJarPath:
    """验证 jar 路径探测顺序。Verify the jar path probing order."""

    def test_returns_none_when_nothing_found(self, monkeypatch, tmp_path):
        monkeypatch.delenv(ENV_JAR_PATH, raising=False)
        monkeypatch.delenv(ENV_JAR_DIR, raising=False)
        monkeypatch.setattr(h2_support, "DEFAULT_H2_DIR", tmp_path)
        monkeypatch.setattr(h2_support, "_legacy_tools_jar_path", lambda: None)
        assert resolve_jar_path() is None

    def test_jar_path_env_wins(self, monkeypatch, tmp_path):
        jar = tmp_path / "custom.jar"
        jar.write_bytes(b"fake")
        monkeypatch.setenv(ENV_JAR_PATH, str(jar))
        monkeypatch.delenv(ENV_JAR_DIR, raising=False)
        monkeypatch.setattr(h2_support, "DEFAULT_H2_DIR", tmp_path / "nope")
        monkeypatch.setattr(h2_support, "_legacy_tools_jar_path", lambda: None)
        assert resolve_jar_path() == jar

    def test_jar_dir_env_used(self, monkeypatch, tmp_path):
        jar_dir = tmp_path / "dir"
        jar_dir.mkdir()
        jar = jar_dir / H2_JAR_FILENAME
        jar.write_bytes(b"fake")
        monkeypatch.delenv(ENV_JAR_PATH, raising=False)
        monkeypatch.setenv(ENV_JAR_DIR, str(jar_dir))
        monkeypatch.setattr(h2_support, "DEFAULT_H2_DIR", tmp_path / "nope")
        monkeypatch.setattr(h2_support, "_legacy_tools_jar_path", lambda: None)
        assert resolve_jar_path() == jar

    def test_default_dir_used(self, monkeypatch, tmp_path):
        jar = tmp_path / H2_JAR_FILENAME
        jar.write_bytes(b"fake")
        monkeypatch.delenv(ENV_JAR_PATH, raising=False)
        monkeypatch.delenv(ENV_JAR_DIR, raising=False)
        monkeypatch.setattr(h2_support, "DEFAULT_H2_DIR", tmp_path)
        monkeypatch.setattr(h2_support, "_legacy_tools_jar_path", lambda: None)
        assert resolve_jar_path() == jar

    def test_legacy_tools_fallback(self, monkeypatch, tmp_path):
        jar = tmp_path / H2_JAR_FILENAME
        jar.write_bytes(b"fake")
        monkeypatch.delenv(ENV_JAR_PATH, raising=False)
        monkeypatch.delenv(ENV_JAR_DIR, raising=False)
        monkeypatch.setattr(h2_support, "DEFAULT_H2_DIR", tmp_path / "nope")
        monkeypatch.setattr(h2_support, "_legacy_tools_jar_path", lambda: jar)
        assert resolve_jar_path() == jar


class TestVerifySha256:
    """验证 SHA-256 校验逻辑。Verify the SHA-256 check logic."""

    def test_passes_when_digest_matches(self, monkeypatch, tmp_path):
        jar = tmp_path / H2_JAR_FILENAME
        jar.write_bytes(b"content")
        monkeypatch.setattr(h2_support, "H2_JAR_SHA256", hashlib.sha256(b"content").hexdigest())
        assert verify_sha256(jar) is True

    def test_fails_when_digest_differs(self, monkeypatch, tmp_path):
        jar = tmp_path / H2_JAR_FILENAME
        jar.write_bytes(b"content")
        monkeypatch.setattr(h2_support, "H2_JAR_SHA256", "0" * 64)
        assert verify_sha256(jar) is False


class TestDownloadH2Jar:
    """验证下载、幂等与校验失败行为。Verify download, idempotency and checksum failure."""

    def test_downloads_when_missing(self, tmp_path):
        jar = tmp_path / H2_JAR_FILENAME
        with patch("urllib.request.urlopen", return_value=io.BytesIO(b"jar-bytes")), \
             patch.object(h2_support, "verify_sha256", return_value=True):
            result = download_h2_jar(dest_dir=tmp_path)
        assert result == jar
        assert jar.read_bytes() == b"jar-bytes"

    def test_skips_when_present_and_valid(self, tmp_path):
        jar = tmp_path / H2_JAR_FILENAME
        jar.write_bytes(b"existing")
        with patch("urllib.request.urlopen") as mock_urlopen, \
             patch.object(h2_support, "verify_sha256", return_value=True):
            result = download_h2_jar(dest_dir=tmp_path)
        mock_urlopen.assert_not_called()
        assert result == jar
        assert jar.read_bytes() == b"existing"

    def test_forces_redownload(self, tmp_path):
        jar = tmp_path / H2_JAR_FILENAME
        jar.write_bytes(b"existing")
        with patch("urllib.request.urlopen", return_value=io.BytesIO(b"new-bytes")), \
             patch.object(h2_support, "verify_sha256", return_value=True):
            result = download_h2_jar(dest_dir=tmp_path, force=True)
        assert result == jar
        assert jar.read_bytes() == b"new-bytes"

    def test_raises_when_checksum_fails(self, tmp_path):
        with patch("urllib.request.urlopen", return_value=io.BytesIO(b"bad")), \
             patch.object(h2_support, "verify_sha256", return_value=False):
            with pytest.raises(RuntimeError):
                download_h2_jar(dest_dir=tmp_path)
        assert not (tmp_path / H2_JAR_FILENAME).exists()
        assert not (tmp_path / (H2_JAR_FILENAME + ".tmp")).exists()

    def test_falls_back_to_mirror(self, tmp_path):
        jar = tmp_path / H2_JAR_FILENAME

        def flaky_urlopen(url, *args, **kwargs):
            if url == h2_support.MAVEN_CENTRAL_URL:
                raise OSError("network unreachable")
            return io.BytesIO(b"mirror-bytes")

        with patch("urllib.request.urlopen", side_effect=flaky_urlopen), \
             patch.object(h2_support, "verify_sha256", return_value=True):
            result = download_h2_jar(dest_dir=tmp_path)
        assert result == jar
        assert jar.read_bytes() == b"mirror-bytes"
