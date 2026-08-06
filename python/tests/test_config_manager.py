"""config_manager 配置校验测试。Config manager validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from config.config_manager import ConfigError, initialize


def _write_env(tmp_path: Path, base: dict, env_local: dict | None = None) -> Path:
    """写入临时 env.yml（可选 env-local.yml）。Write temp env.yml (optionally env-local.yml)."""
    (tmp_path / "env.yml").write_text(
        yaml.safe_dump(base, allow_unicode=True), encoding="utf-8"
    )
    if env_local is not None:
        (tmp_path / "env-local.yml").write_text(
            yaml.safe_dump(env_local, allow_unicode=True), encoding="utf-8"
        )
    return tmp_path / "env.yml"


@pytest.fixture(autouse=True)
def reset_config_state():
    """每个用例前后重置模块级配置状态。Reset module-level config state around each test."""
    import config.config_manager as cm

    cm._initialized = False
    cm._config = {}
    cm._apps = {}
    yield
    cm._initialized = False
    cm._config = {}
    cm._apps = {}


def test_yaml_files_skips_case_file_path_requirement(tmp_path: Path):
    """提供 --yamlFiles 时不再要求 caseFilePath。caseFilePath not required when --yamlFiles is given."""
    yml = _write_env(tmp_path, {"envName": "local"}, env_local={})
    initialize(str(yml), {"yamlFiles": ["TC_001.yaml"]})

    import config.config_manager as cm

    assert cm.get("envName") == "local"
    # 校验专用键不写入最终配置 / Validation-only keys are not stored into final config
    assert "yamlFiles" not in cm._config
    assert "yamlDir" not in cm._config


def test_yaml_dir_skips_case_file_path_requirement(tmp_path: Path):
    """提供 --yamlDir 时同样不要求 caseFilePath。caseFilePath not required when --yamlDir is given."""
    yml = _write_env(tmp_path, {"envName": "local"}, env_local={})
    initialize(str(yml), {"yamlDir": str(tmp_path / "cases")})


def test_missing_case_file_path_raises_without_yaml_input(tmp_path: Path):
    """无 YAML 输入且缺少 caseFilePath 时报错。Missing caseFilePath raises when no YAML input is given."""
    yml = _write_env(tmp_path, {"envName": "local"}, env_local={})
    with pytest.raises(ConfigError) as exc:
        initialize(str(yml), {})
    assert "caseFilePath" in str(exc.value)


def test_missing_env_name_raises(tmp_path: Path):
    """缺少 envName 始终报错。Missing envName always raises."""
    yml = _write_env(tmp_path, {"caseFilePath": "cases.xlsx"})
    with pytest.raises(ConfigError) as exc:
        initialize(str(yml), {})
    assert "envName" in str(exc.value)


def test_case_file_path_required_when_present(tmp_path: Path):
    """Excel 模式下提供 caseFilePath 可正常初始化。Excel mode with caseFilePath initializes fine."""
    yml = _write_env(tmp_path, {"envName": "local", "caseFilePath": "cases.xlsx"}, env_local={})
    initialize(str(yml), {})

    import config.config_manager as cm

    assert cm.get("caseFilePath") == "cases.xlsx"
