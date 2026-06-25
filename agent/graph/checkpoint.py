"""断点续写管理器 — 支持分批生成的断点续写。

Checkpoint manager for resumable batch generation.

在 {memory_dir}/ 下写入两个文件：
  - checkpoint.json      — 轻量元数据（阶段、设置、计数）；
                           足够小，用户可手动编辑以回滚。
  - checkpoint_data.json — 批量用例数据；仅机器读写。
"""

import importlib.util
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CURRENT_VERSION = 1

_PHASES = [
    "skeletons_generated",
    "data_filled_single",
    "data_filled_biz",
    "assertions_generated_single",
    "assertions_generated_biz",
    "plugins_applied",
]


class CheckpointManager:
    """断点文件读写管理器。Read / write batch-generation checkpoint files."""

    def __init__(self, memory_dir: str) -> None:
        base = Path(memory_dir)
        self.meta_path = base / "checkpoint.json"
        self.data_path = base / "checkpoint_data.json"

    # ------------------------------------------------------------------
    # existence
    # ------------------------------------------------------------------

    def exists(self) -> bool:
        return self.meta_path.exists() and self.data_path.exists()

    # ------------------------------------------------------------------
    # save
    # ------------------------------------------------------------------

    def save_meta(
        self,
        phase: str,
        settings: Dict[str, Any],
        counts: Dict[str, Any],
        output_dir: str,
    ) -> None:
        """Write checkpoint.json (lightweight metadata)."""
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {
            "version": CURRENT_VERSION,
            "phase": phase,
            "phase_status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "settings": settings,
            "counts": counts,
            "output_dir": output_dir,
        }
        self.meta_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        logger.debug("Checkpoint meta saved: phase=%s", phase)

    def save_data(self, phase: str, data: Dict[str, Any]) -> None:
        """Write checkpoint_data.json (bulk case data)."""
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {
            "version": CURRENT_VERSION,
            "phase": phase,
        }
        payload.update(data)
        self.data_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        logger.debug("Checkpoint data saved: phase=%s", phase)

    # ------------------------------------------------------------------
    # load
    # ------------------------------------------------------------------

    def load_meta(self) -> Optional[Dict[str, Any]]:
        """Read and validate checkpoint.json. Returns None on any error."""
        try:
            text = self.meta_path.read_text(encoding="utf-8")
            data = json.loads(text)
        except FileNotFoundError:
            logger.debug("Checkpoint meta not found: %s", self.meta_path)
            return None
        except json.JSONDecodeError as e:
            logger.warning("Checkpoint meta JSON corrupt: %s", e)
            return None

        if data.get("version") != CURRENT_VERSION:
            logger.warning(
                "Checkpoint version mismatch: got %s, expected %s",
                data.get("version"), CURRENT_VERSION,
            )
            return None

        return data

    def load_data(self) -> Optional[Dict[str, Any]]:
        """Read and validate checkpoint_data.json. Returns None on any error."""
        try:
            text = self.data_path.read_text(encoding="utf-8")
            data = json.loads(text)
        except FileNotFoundError:
            logger.debug("Checkpoint data not found: %s", self.data_path)
            return None
        except json.JSONDecodeError as e:
            logger.warning("Checkpoint data JSON corrupt: %s", e)
            return None

        if data.get("version") != CURRENT_VERSION:
            logger.warning(
                "Checkpoint data version mismatch: got %s, expected %s",
                data.get("version"), CURRENT_VERSION,
            )
            return None

        return data

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_restart_phase(meta: Dict[str, Any]) -> str:
        """Return the next incomplete phase.

        If meta says phase X is completed, restart_phase is the *next* phase.
        Users can hand-edit meta["phase"] to roll back to an earlier phase.
        """
        current = meta.get("phase", "")
        try:
            idx = _PHASES.index(current)
        except ValueError:
            logger.warning("Unknown phase in checkpoint: %r", current)
            return _PHASES[0]

        next_idx = idx + 1
        if next_idx >= len(_PHASES):
            return "all_complete"
        return _PHASES[next_idx]

    @staticmethod
    def validate_plugins(meta: Dict[str, Any]) -> List[str]:
        """Check that every plugin recorded in the checkpoint still exists.

        Returns a list of missing plugin module paths (empty = all present).
        """
        settings = meta.get("settings", {})
        paths = [p.strip() for p in settings.get("plugin_modules", []) if p.strip()]
        missing: List[str] = []
        for path in paths:
            if importlib.util.find_spec(path) is None:
                missing.append(path)
        return missing
