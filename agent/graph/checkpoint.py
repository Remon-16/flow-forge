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
import os
import tempfile
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

    @staticmethod
    def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
        """原子写入 JSON：先写临时文件，确保落盘后原子 rename。
        避免崩溃时文件处于部分写入状态，确保读取者要么看到完整新文件，要么看到完整旧文件。

        Atomic JSON write: write to temp file, fsync, then os.replace.
        Prevents partial writes on crash; readers see either complete new or complete old.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.tmp.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())  # 确保数据落盘 / Ensure data is on disk
            os.replace(tmp_path, str(path))  # 原子替换 / Atomic replace
        except Exception:
            # 清理临时文件 / Clean up temp file
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def save_meta(
        self,
        phase: str,
        settings: Dict[str, Any],
        output_dir: str,
        phases: List[str] = None,
        phase_progress: Dict[str, Any] = None,
        phase_status: str = "completed",
    ) -> None:
        """Write checkpoint.json (lightweight metadata).

        写入轻量元数据文件。
        phase_progress: 各阶段执行进度 / per-phase execution progress.
        phase_status:   "completed" | "in_progress".
        """
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {
            "version": CURRENT_VERSION,
            "phase": phase,
            "phase_status": phase_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "settings": settings,
            "output_dir": output_dir,
        }
        if phases is not None:
            payload["phases"] = phases
        if phase_progress is not None:
            payload["phase_progress"] = phase_progress
        self._atomic_write_json(self.meta_path, payload)
        logger.debug("Checkpoint meta saved: phase=%s", phase)

    def save_data(self, phase: str, data: Dict[str, Any]) -> None:
        """Write checkpoint_data.json (bulk case data)."""
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {
            "version": CURRENT_VERSION,
            "phase": phase,
        }
        payload.update(data)
        self._atomic_write_json(self.data_path, payload)
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

        返回下一个未完成的阶段。若当前阶段尚未完成（phase_status="in_progress"），
        则返回当前阶段以便继续处理。用户可手动编辑 meta["phase"] 回滚到更早的阶段。
        Returns the current phase if it's in_progress, otherwise the next phase.
        Users can hand-edit meta["phase"] to roll back to an earlier phase.

        Prefers *phases* list from meta (for dynamic phase names from
        BatchController). Falls back to static _PHASES for backward
        compatibility with checkpoints saved before this fix.
        """
        phase_status = meta.get("phase_status", "completed")
        current = meta.get("phase", "")
        phases = meta.get("phases")
        if phases is None:
            phases = _PHASES

        # 当前阶段未完成 → 返回当前阶段，从断点继续
        # If current phase is in_progress, resume from it
        if phase_status == "in_progress" and current:
            return current

        try:
            idx = phases.index(current)
        except ValueError:
            logger.warning("Unknown phase in checkpoint: %r", current)
            return phases[0]

        next_idx = idx + 1
        if next_idx >= len(phases):
            return "all_complete"
        return phases[next_idx]

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
