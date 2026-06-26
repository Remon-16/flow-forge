"""YAML test case parser — reads .yml/.yaml files and produces executor-compatible dicts."""

import logging
from pathlib import Path
from typing import Any, Dict, List

import yaml

logger = logging.getLogger(__name__)


class YamlParser:
    """Parse YAML test case files into the same dict structure as ExcelParser.

    Returns ``{"single_cases": [...], "biz_flows": [...]}`` for direct
    consumption by SingleCaseExecutor / BizFlowExecutor.
    """

    @staticmethod
    def parse_directory(dir_path: str, api_mode: str = "all") -> Dict[str, List[Dict]]:
        """Recursively scan *dir_path* for ``*.yml`` / ``*.yaml`` files.

        Args:
            dir_path: Root directory to scan.
            api_mode: ``"single"``, ``"biz"``, or ``"all"``.

        Returns:
            Dict with ``single_cases`` and ``biz_flows`` lists.
        """
        root = Path(dir_path)
        if not root.is_dir():
            logger.warning("YAML directory not found: %s", dir_path)
            return {"single_cases": [], "biz_flows": []}

        yaml_files = sorted([p for p in root.rglob("*") if p.suffix.lower() in (".yaml", ".yml")])
        logger.info("Found %d YAML files under %s", len(yaml_files), dir_path)
        return YamlParser._load_and_sort(yaml_files, api_mode)

    @staticmethod
    def parse_files(file_paths: str, api_mode: str = "all") -> Dict[str, List[Dict]]:
        """Parse a comma-separated list of YAML file paths.

        Args:
            file_paths: Comma-separated file paths.
            api_mode: ``"single"``, ``"biz"``, or ``"all"``.

        Returns:
            Dict with ``single_cases`` and ``biz_flows`` lists.
        """
        paths: List[Path] = []
        for raw in file_paths.split(","):
            raw = raw.strip()
            if raw:
                p = Path(raw)
                if p.is_file():
                    paths.append(p)
                else:
                    logger.warning("YAML file not found, skipped: %s", raw)

        logger.info("Parsing %d YAML files", len(paths))
        return YamlParser._load_and_sort(paths, api_mode)

    @staticmethod
    def _load_and_sort(
        paths: List[Path], api_mode: str
    ) -> Dict[str, List[Dict]]:
        singles: List[Dict] = []
        biz_flows: List[Dict] = []

        for p in paths:
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
            except Exception:
                logger.warning("Failed to read YAML, skipped: %s", p, exc_info=True)
                continue

            if data is None:
                continue

            items = data if isinstance(data, list) else [data]

            for item in items:
                if not isinstance(item, dict):
                    continue
                case_type = item.get("case_type", "")

                if case_type == "single" and api_mode in ("single", "all"):
                    if not item.get("test_id") or not item.get("method") or not item.get("url"):
                        logger.warning("Skipping single case with missing required fields "
                                       "(test_id, method, url) in: %s", p)
                        continue
                    singles.append(item)
                elif case_type == "biz" and api_mode in ("biz", "all"):
                    if not item.get("sheet_name"):
                        logger.warning("Skipping biz flow with missing sheet_name in: %s", p)
                        continue
                    steps = item.get("steps")
                    if not steps or not isinstance(steps, list):
                        logger.warning("Skipping biz flow with missing or empty steps in: %s", p)
                        continue
                    biz_flows.append(item)
                elif not case_type:
                    # Infer from structure
                    if "steps" in item and api_mode in ("biz", "all"):
                        if not item.get("sheet_name"):
                            logger.warning("Skipping biz flow with missing sheet_name in: %s", p)
                            continue
                        steps = item.get("steps")
                        if not steps or not isinstance(steps, list):
                            logger.warning("Skipping biz flow with missing or empty steps in: %s", p)
                            continue
                        item["case_type"] = "biz"
                        biz_flows.append(item)
                    elif "test_id" in item and api_mode in ("single", "all"):
                        if not item.get("method") or not item.get("url"):
                            logger.warning("Skipping single case with missing required fields "
                                           "(method, url) in: %s", p)
                            continue
                        item["case_type"] = "single"
                        singles.append(item)
                    else:
                        logger.warning("Cannot determine case_type, skipped: %s", p)

        logger.info(
            "Loaded %d single cases, %d biz flows", len(singles), len(biz_flows)
        )
        return {"single_cases": singles, "biz_flows": biz_flows}
