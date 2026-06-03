"""SessionLogger: structured session directory with two-level logging.

Directory structure::

    logs/
      2026-06-03_22-30-00/
        session.jsonl        # Event stream (summary, one JSON per line)
        debug.log            # Full LLM I/O + tool call details (only when --debug)
        plan.md              # Generated test plan
        state.json           # Latest GraphState (for checkpoint recovery)
        excel_result.xlsx    # Final output copy
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SessionLogger:
    """Manages a per-run session directory with structured event logging.

    Two log levels:
    - session.jsonl: always written, contains event summaries (no full prompt/response)
    - debug.log: only when debug=True, contains full LLM inputs/outputs and tool call details
    """

    def __init__(self, session_dir: Path, debug: bool = False):
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.debug = debug
        self._start_ts = time.time()
        self._start_time = datetime.now()

        # Write session start
        self.log_event("session_start")

        if self.debug:
            self.log_debug(
                "session_start",
                session_dir=str(self.session_dir),
                debug_enabled=True,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def log_event(self, event_type: str, **kwargs: Any) -> None:
        """Append a summary event to session.jsonl."""
        entry = {
            "ts": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "type": event_type,
            **kwargs,
        }
        self._append_jsonl("session.jsonl", entry)

    def log_debug(self, event_type: str, **kwargs: Any) -> None:
        """Append detailed debug info to debug.log (only when --debug)."""
        if not self.debug:
            return
        elapsed = time.time() - self._start_ts
        line = f"[{elapsed:7.1f}s] {event_type}"
        for key, val in kwargs.items():
            if isinstance(val, str) and len(val) > 200:
                val = val[:200] + f"...<truncated, total {len(val)} chars>"
            line += f"\n  {key}: {val}"
        line += "\n" + "-" * 60
        self._append_text("debug.log", line + "\n")

    def log_llm_call(
        self,
        agent: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        prompt_len: int,
    ) -> None:
        """Log an LLM call (summary to JSONL, full to debug if enabled)."""
        self.log_event(
            "llm_call",
            agent=agent,
            model=model,
            prompt_len=prompt_len,
        )
        if self.debug:
            self.log_debug(
                "llm_call",
                agent=agent,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

    def log_llm_result(
        self,
        agent: str,
        output: str,
        output_len: int,
        duration_ms: int,
    ) -> None:
        """Log an LLM result (summary to JSONL, full response to debug if enabled)."""
        self.log_event(
            "llm_result",
            agent=agent,
            output_len=output_len,
            duration_ms=duration_ms,
        )
        if self.debug:
            self.log_debug("llm_result", agent=agent, output=output)

    def log_tool_call(
        self, tool_name: str, tool_input: str, result_len: int
    ) -> None:
        """Log a tool call (summary to JSONL, full input/output to debug)."""
        self.log_event(
            "tool_call",
            tool=tool_name,
            tool_input=tool_input[:120],
            output_len=result_len,
        )
        if self.debug:
            self.log_debug(
                "tool_call",
                tool=tool_name,
                tool_input=tool_input,
                output_len=result_len,
            )

    def save_state(self, state: Dict[str, Any]) -> None:
        """Write the current GraphState to state.json."""
        # Filter out non-serializable items (messages, etc.)
        safe = {}
        for k, v in state.items():
            try:
                json.dumps(v, ensure_ascii=False, default=str)
                safe[k] = v
            except (TypeError, ValueError):
                safe[k] = str(v)
        self._write_json("state.json", safe)
        self.log_event("state_save", path="state.json")

    def save_plan(self, plan_md: str) -> Path:
        """Write the test plan to plan.md, return path."""
        path = self.session_dir / "plan.md"
        path.write_text(plan_md, encoding="utf-8")
        self.log_event("file_write", path=str(path), size=len(plan_md))
        return path

    def save_excel(self, src_path: str) -> Optional[Path]:
        """Copy the final Excel file into the session directory."""
        src = Path(src_path)
        if not src.exists():
            logger.warning("Excel source not found: %s", src)
            return None
        dst = self.session_dir / "excel_result.xlsx"
        shutil.copy2(src, dst)
        self.log_event("excel_save", path=str(dst), size=src.stat().st_size)
        return dst

    def log_file_read(self, path: str, size: int) -> None:
        """Log a file read operation."""
        self.log_event("file_read", path=path, size=size)

    def log_node_start(self, node: str, step: str) -> None:
        """Log workflow node start."""
        self.log_event("node_start", node=node, step=step)

    def log_node_end(self, node: str) -> None:
        """Log workflow node end."""
        self.log_event("node_end", node=node)

    def log_session_end(self, status: str = "completed") -> None:
        """Log session completion."""
        duration_ms = int((time.time() - self._start_ts) * 1000)
        self.log_event("session_end", status=status, duration_ms=duration_ms)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _append_jsonl(self, filename: str, entry: Dict[str, Any]) -> None:
        path = self.session_dir / filename
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _append_text(self, filename: str, text: str) -> None:
        path = self.session_dir / filename
        with path.open("a", encoding="utf-8") as f:
            f.write(text)

    def _write_json(self, filename: str, data: Dict[str, Any]) -> None:
        path = self.session_dir / filename
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
