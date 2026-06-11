"""YAML file writer/reader for interfaces, single cases, and biz flows."""

import logging
from pathlib import Path
from typing import Any, Dict, List

import yaml

logger = logging.getLogger(__name__)


class YamlWriter:
    """Read/write test artifacts as individual YAML files."""

    @staticmethod
    def _ensure_dir(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _to_dict(obj: Any) -> Dict[str, Any]:
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "__dataclass_fields__"):
            from dataclasses import fields
            result = {}
            for f in fields(obj):
                value = getattr(obj, f.name)
                if hasattr(value, "__dataclass_fields__"):
                    result[f.name] = YamlWriter._to_dict(value)
                elif isinstance(value, list):
                    result[f.name] = [
                        YamlWriter._to_dict(v) if hasattr(v, "__dataclass_fields__") else v
                        for v in value
                    ]
                else:
                    result[f.name] = value
            return result
        return obj

    # ---- Write ----

    @staticmethod
    def write_interface(iface: Any, output_dir: str) -> str:
        d = YamlWriter._to_dict(iface)
        test_id = d.get("test_id", "unknown")
        safe_name = test_id.replace("/", "_").replace("\\", "_").replace(":", "_")
        file_path = Path(output_dir) / "interfaces" / f"{safe_name}.yaml"
        YamlWriter._ensure_dir(file_path.parent)
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(d, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        logger.debug("Wrote interface: %s", file_path)
        return str(file_path)

    @staticmethod
    def write_single_case(case: Any, output_dir: str) -> str:
        d = YamlWriter._to_dict(case)
        d["case_type"] = "single"
        test_id = d.get("test_id", "unknown")
        safe_name = test_id.replace("/", "_").replace("\\", "_").replace(":", "_")
        file_path = Path(output_dir) / "single_cases" / f"{safe_name}.yaml"
        YamlWriter._ensure_dir(file_path.parent)
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(d, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        logger.debug("Wrote single case: %s", file_path)
        return str(file_path)

    @staticmethod
    def write_biz_flow(flow: Any, output_dir: str) -> str:
        d = YamlWriter._to_dict(flow)
        d["case_type"] = "biz"
        sheet_name = d.get("sheet_name", "unknown")
        safe_name = sheet_name.replace("/", "_").replace("\\", "_").replace(":", "_")
        file_path = Path(output_dir) / "biz_flows" / f"{safe_name}.yaml"
        YamlWriter._ensure_dir(file_path.parent)
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(d, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        logger.debug("Wrote biz flow: %s", file_path)
        return str(file_path)

    @staticmethod
    def write_failures(failures: List[Dict], output_dir: str) -> str:
        file_path = Path(output_dir) / "failures.yaml"
        YamlWriter._ensure_dir(file_path.parent)
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(failures, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        logger.info("Wrote %d failures to %s", len(failures), file_path)
        return str(file_path)

    # ---- Read ----

    @staticmethod
    def read_interfaces(output_dir: str) -> List[Dict[str, Any]]:
        return YamlWriter._read_dir(Path(output_dir) / "interfaces")

    @staticmethod
    def read_single_cases(output_dir: str) -> List[Dict[str, Any]]:
        return YamlWriter._read_dir(Path(output_dir) / "single_cases")

    @staticmethod
    def read_biz_flows(output_dir: str) -> List[Dict[str, Any]]:
        return YamlWriter._read_dir(Path(output_dir) / "biz_flows")

    @staticmethod
    def _read_dir(dir_path: Path) -> List[Dict[str, Any]]:
        if not dir_path.is_dir():
            return []
        results = []
        for f in sorted(dir_path.glob("*.yaml")):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if isinstance(data, dict):
                    results.append(data)
            except Exception:
                logger.warning("Failed to read YAML: %s", f, exc_info=True)
        return results

    # ---- List ----

    @staticmethod
    def list_interface_ids(output_dir: str) -> List[str]:
        dir_path = Path(output_dir) / "interfaces"
        if not dir_path.is_dir():
            return []
        ids = []
        for f in sorted(dir_path.glob("*.yaml")):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if isinstance(data, dict) and data.get("test_id"):
                    ids.append(data["test_id"])
            except Exception:
                pass
        return ids

    @staticmethod
    def list_generated_case_ids(output_dir: str, case_type: str) -> List[str]:
        subdir = "single_cases" if case_type == "single" else "biz_flows"
        dir_path = Path(output_dir) / subdir
        if not dir_path.is_dir():
            return []
        ids = []
        for f in sorted(dir_path.glob("*.yaml")):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if isinstance(data, dict):
                    tid = data.get("test_id") or data.get("sheet_name")
                    if tid:
                        ids.append(str(tid))
            except Exception:
                pass
        return ids

    @staticmethod
    def count_generated(output_dir: str, case_type: str) -> int:
        subdir = "single_cases" if case_type == "single" else "biz_flows"
        dir_path = Path(output_dir) / subdir
        if not dir_path.is_dir():
            return 0
        return len(list(dir_path.glob("*.yaml")))
