"""BaseAgent — foundation class for all LLM-powered agents."""

from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from openai import OpenAI

import httpx

from prompts.compression import COMPRESSION_SYSTEM, DEFAULT_CHUNK_NOTICE
from prompts.json_fix import JSON_FIX_PROMPT

logger = logging.getLogger(__name__)


def _short_error(exc: Exception) -> str:
    """Return a short human-readable error summary (class name + brief message)."""
    msg = str(exc).strip()
    if len(msg) > 80:
        msg = msg[:77] + "..."
    return f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__


class ConvergenceError(Exception):
    """Raised when an agent exceeds its max_steps limit."""


class BaseAgent:
    """Base class for all LLM-powered agents.

    Provides:
    - OpenAI-compatible LLM call
    - Automatic retry with exponential backoff
    - Structured JSON output parsing
    - Step counter with max_steps guard
    """

    # Global rate limiting: shared across all instances
    _last_call_time: float = 0.0
    _call_lock = threading.Lock()
    _concurrency_semaphore: threading.Semaphore | None = None

    # Shared OpenAI client — avoids multiple httpx connection pools
    # that can cause providers (e.g. GLM) to misdetect concurrency
    _shared_client: Any = None
    _shared_client_lock = threading.Lock()

    # Class-level defaults — injected by nodes.configure() from Settings
    _default_rate_limit_delay: float = 0.0
    _default_retry_base_delay: float = 2.0
    _default_max_concurrency: int = 1
    _default_request_timeout: float = 600.0
    _default_extra_params: Dict[str, Any] | None = None

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        temperature: float = 0.3,
        max_retries: int = 3,
        max_steps: int = 10,
        base_url: str = "",
        context_window: int = 128000,
        max_output_tokens: int = 4096,
        compression_threshold: float = 0.9,
        rate_limit_delay: float | None = None,
        retry_base_delay: float | None = None,
        max_concurrency: int | None = None,
        request_timeout: float | None = None,
        skill_extensions: List[str] | None = None,
        extra_params: Dict[str, Any] | None = None,
    ):
        # Use shared client to avoid creating multiple httpx connection pools.
        # Each pool maintains keep-alive connections; with 10+ agent instances,
        # providers like GLM may see many open TCP connections and misdetect
        # concurrency, triggering rate-limit errors.
        if BaseAgent._shared_client is None:
            with BaseAgent._shared_client_lock:
                if BaseAgent._shared_client is None:
                    _timeout = (
                        request_timeout if request_timeout is not None
                        else BaseAgent._default_request_timeout
                    )
                    client_kwargs = {
                        "api_key": api_key,
                        "max_retries": 0,
                        "timeout": httpx.Timeout(_timeout, connect=5.0),
                    }
                    if base_url:
                        client_kwargs["base_url"] = base_url
                    BaseAgent._shared_client = OpenAI(**client_kwargs)
        self._client = BaseAgent._shared_client
        self._model = model
        self._temperature = temperature
        self._max_retries = max_retries
        self._max_steps = max_steps
        self._rate_limit_delay = (
            rate_limit_delay if rate_limit_delay is not None
            else BaseAgent._default_rate_limit_delay
        )
        self._retry_base_delay = (
            retry_base_delay if retry_base_delay is not None
            else BaseAgent._default_retry_base_delay
        )
        self._request_timeout = (
            request_timeout if request_timeout is not None
            else BaseAgent._default_request_timeout
        )
        _mc = (
            max_concurrency if max_concurrency is not None
            else BaseAgent._default_max_concurrency
        )

        # Initialize global concurrency semaphore (once, shared across all instances)
        if BaseAgent._concurrency_semaphore is None and _mc > 0:
            BaseAgent._concurrency_semaphore = threading.Semaphore(_mc)
        self._step_count = 0
        self._progress_getter: Callable[[], str] | None = None
        self._last_progress: str | None = None

        # Context window management
        self._context_window = context_window
        self._max_output_tokens = max_output_tokens
        self._compression_threshold = compression_threshold
        from utils.token_counter import TokenCounter
        self._token_counter = TokenCounter(model)

        # Multi-round conversation state (per-instance, isolated)
        self._conversation_tokens: int = 0
        self._conversation_summary: str = ""
        self._round_count: int = 0

        # Skill extensions — injected by plugin loader, appended to system_msg on each call
        self._skill_extensions: List[str] = skill_extensions or []

        # Extra API params — injected via configure() from settings.llm_extra_params
        self._extra_params: Dict[str, Any] = (
            extra_params if extra_params is not None
            else BaseAgent._default_extra_params or {}
        )

    def set_progress_getter(
        self, getter: Callable[[], str], max_no_progress: int = 5
    ) -> None:
        """Enable progress-based step counting.

        When set, check_step() compares the current progress string against
        the previous call. If progress changed, the step counter resets to 1.
        If progress is unchanged, the step counter increments. Raises
        ConvergenceError after max_no_progress consecutive no-progress calls.

        Call with getter=None to revert to legacy counting.
        """
        self._progress_getter = getter
        self._last_progress = None
        self._max_steps = max_no_progress

    def check_step(self) -> None:
        """Increment step counter, raise if max_steps exceeded.

        If a progress getter is configured, uses progress-based counting:
        same progress = increment, different progress = reset to 1.
        This allows models that make steady progress to continue
        indefinitely, while catching models that make zero progress quickly.
        """
        if self._progress_getter:
            current = self._progress_getter()
            if self._last_progress is not None and current == self._last_progress:
                self._step_count += 1
            else:
                self._step_count = 1
            self._last_progress = current
        else:
            self._step_count += 1

        if self._step_count > self._max_steps:
            raise ConvergenceError(
                f"Agent exceeded max_steps ({self._max_steps})"
            )

    def reset_steps(self) -> None:
        self._step_count = 0

    # ------------------------------------------------------------------
    # Context window management
    # ------------------------------------------------------------------

    def _estimate_input_tokens(self, system_msg: str, prompt: str) -> int:
        """Estimate input tokens for this call (system + user + history summary)."""
        total = self._token_counter.count(system_msg)
        total += self._token_counter.count(prompt)
        if self._conversation_summary:
            total += self._token_counter.count(self._conversation_summary)
        return total

    def _context_usage_ratio(self, system_msg: str, prompt: str) -> float:
        """Return current input as a fraction of context window (0.0 ~ 1.0+)."""
        estimated = self._estimate_input_tokens(system_msg, prompt)
        return estimated / self._context_window

    def _check_context_fit(self, system_msg: str, prompt: str) -> bool:
        """Check whether input fits within the context window.

        Uses the configurable _compression_threshold (default 0.9).
        Returns False if input exceeds the context window.
        Logs a warning when the threshold is exceeded.
        """
        ratio = self._context_usage_ratio(system_msg, prompt)
        if ratio >= 1.0:
            return False
        if ratio >= self._compression_threshold:
            logger.warning(
                "Context usage at %.0f%%, exceeding compression threshold %.0f%%",
                ratio * 100, self._compression_threshold * 100,
            )
        return True

    def reset_conversation(self) -> None:
        """Reset multi-round conversation token state."""
        self._conversation_tokens = 0
        self._conversation_summary = ""
        self._round_count = 0

    def _compress_conversation(self, system_msg: str) -> str:
        """压缩累积的对话历史为关键要点摘要。

        Compress accumulated conversation history into a concise summary.

        仅压缩 _conversation_summary（累积的块处理结果）。system_msg 参数
        仅作为压缩 LLM 调用的上下文传入 —— 它不会被存储、累积或压缩。
        系统提示词和 Skill 内容在所有轮次中保持完整。

        Only compresses _conversation_summary (accumulated chunk results).
        The system_msg parameter is used solely as context for the compression
        LLM call — it is NEVER stored, accumulated, or compressed. System
        prompts and skill content remain intact across all rounds.
        """
        if not self._conversation_summary and self._round_count <= 1:
            return ""

        compress_prompt = COMPRESSION_SYSTEM.format(history=self._conversation_summary)
        try:
            summary = self.call_llm(compress_prompt, system_msg)
            self._conversation_summary = summary
            self._conversation_tokens = self._token_counter.count(summary)
            logger.info(
                "Conversation compressed to %d tokens", self._conversation_tokens
            )
            return summary
        except Exception as e:
            logger.warning("Context compression failed: %s", e)
            return self._conversation_summary

    # ------------------------------------------------------------------
    # Long text chunking
    # ------------------------------------------------------------------

    def _chunk_text(self, text: str, max_chunk_tokens: int) -> list:
        """Split long text into chunks respecting token budget.

        Chunks are split at paragraph / sentence boundaries when possible.
        """
        if not text:
            return [""]

        chunks: list = []
        paragraphs = text.split("\n\n")
        current = ""

        for para in paragraphs:
            candidate = current + ("\n\n" if current else "") + para
            if self._token_counter.count(candidate) <= max_chunk_tokens:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                # If a single paragraph exceeds budget, split by sentences
                if self._token_counter.count(para) > max_chunk_tokens:
                    sub_chunks = self._chunk_by_sentences(para, max_chunk_tokens)
                    chunks.extend(sub_chunks)
                else:
                    current = para

        if current:
            chunks.append(current)

        return chunks if chunks else [text]

    def _chunk_by_sentences(self, text: str, max_chunk_tokens: int) -> list:
        """Split a long paragraph into sentence-level chunks."""
        import re
        sentences = re.split(r"(?<=[。.!！?？])\s*", text)
        chunks: list = []
        current = ""
        for sent in sentences:
            candidate = current + sent
            if self._token_counter.count(candidate) <= max_chunk_tokens:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = sent
        if current:
            chunks.append(current)
        return chunks if chunks else [text]

    def _process_long_text(
        self,
        text: str,
        system_msg: str,
        chunk_processor: Callable[[str, str], Any],
        result_merger: Callable[[list, str], Any],
        chunk_overlap: int = 200,
        chunk_notice: str = "",
    ) -> Any:
        """Process a long text through multiple LLM rounds.

        1. Compute available token budget
        2. Split text into chunks
        3. Process each chunk, passing accumulated context
        4. Before each call: check context usage, compress if needed
        5. Merge all results

 Args:
            text: The full text to process.
            system_msg: System prompt for each LLM call.
            chunk_processor: Called with (chunk, accumulated_summary) → result.
            result_merger: Called with (list_of_results, system_msg) → final.
            chunk_overlap: Token overlap between chunks.
            chunk_notice: Notice added to each chunk (e.g. "Part 2/5").
        """
        output_reserve = max(self._max_output_tokens, 4096)
        max_chunk = self._context_window - self._token_counter.count(system_msg) - output_reserve - chunk_overlap
        if max_chunk < 1000:
            max_chunk = 1000

        chunks = self._chunk_text(text, max_chunk)
        total = len(chunks)

        if total <= 1:
            return chunk_processor(text, "")

        logger.info("Processing long text in %d chunks (budget=%d tokens/chunk)", total, max_chunk)
        self.reset_conversation()

        results = []
        accumulated = ""
        for i, chunk in enumerate(chunks):
            notice = chunk_notice or DEFAULT_CHUNK_NOTICE.format(i=i + 1, total=total)
            chunk_with_notice = f"{notice}\n\n{chunk}"

            # Check context before each round
            if not self._check_context_fit(system_msg, chunk_with_notice):
                self._compress_conversation(system_msg)
                if self._conversation_summary:
                    chunk_with_notice = (
                        f"[Previous Summary]\n{self._conversation_summary}\n\n"
                        f"{chunk_with_notice}"
                    )

            try:
                result = chunk_processor(chunk_with_notice, accumulated)
                results.append(result)
                # Update accumulated context
                accumulated = json.dumps(results[-3:], ensure_ascii=False, default=str) if len(results) > 1 else ""
                self._round_count += 1
                self._conversation_tokens += self._token_counter.count(chunk_with_notice)
            except Exception as e:
                logger.error("Chunk %d/%d failed: %s", i + 1, total, e)
                results.append({"error": str(e), "chunk_index": i})

        return result_merger(results, system_msg)

    # ------------------------------------------------------------------
    # Pre-search helpers (shared by SkeletonGenerator / DataFiller)
    # ------------------------------------------------------------------

    def _fuzzy_match_interface(
        self,
        url: str,
        api_name: str,
        http_method: str,
        interfaces: list,
    ) -> dict | None:
        """Find the closest matching interface when relevance_id lookup fails.

        Uses URL path segments, api_name, and HTTP method for fuzzy scoring.
        Returns the best match if similarity exceeds threshold, otherwise None.
        """
        if not interfaces:
            return None

        # Extract path segments from the URL
        segments = [s.lower() for s in url.split("/") if s and len(s) >= 3]

        scored = []
        for iface in interfaces:
            if isinstance(iface, dict):
                iface_url = (iface.get("url") or "").lower()
                iface_name = (iface.get("api_name") or "").lower()
                iface_method = (iface.get("method") or "").upper()
            elif hasattr(iface, "url"):
                iface_url = (getattr(iface, "url", "") or "").lower()
                iface_name = (getattr(iface, "api_name", "") or "").lower()
                iface_method = (getattr(iface, "method", "") or "").upper()
            else:
                continue

            score = 0
            # URL segment matches
            for seg in segments:
                if seg in iface_url:
                    score += 3
            # API name overlap
            name_segments = api_name.lower().split()
            for ns in name_segments:
                if ns and len(ns) >= 2 and ns in iface_name:
                    score += 2
            # HTTP method match
            if http_method.upper() == iface_method:
                score += 4

            if score > 0:
                scored.append((score, iface))

        if not scored:
            return None

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_iface = scored[0]
        if best_score >= 3:
            logger.info(
                "Fuzzy matched interface: score=%d url=%s",
                best_score,
                best_iface.get("url") if isinstance(best_iface, dict) else getattr(best_iface, "url", ""),
            )
            return best_iface
        return None

    def _fuzzy_search_api_doc(
        self,
        url: str,
        http_method: str = "",
        api_doc_text: str = "",
        max_snippet_tokens: int = 3000,
    ) -> str:
        """Search API doc for sections relevant to a URL using fuzzy matching.

        Does NOT depend on interfaces list — only uses the raw API doc text.
        This is the fallback when all other lookup strategies fail.

        Strategy:
        1. Extract meaningful path segments from the URL
        2. Substring-match each segment against doc lines (case-insensitive)
        3. Score lines by segment hit count, take top matches
        4. Expand to surrounding context lines
        5. Merge overlapping windows, truncate to token budget
        """
        if not api_doc_text or not url:
            return api_doc_text[:2000] if api_doc_text else ""

        segments = [
            s.lower() for s in url.split("/")
            if s and len(s) >= 3 and not s.isdigit()
        ]
        if not segments:
            return api_doc_text[:2000]

        lines = api_doc_text.split("\n")
        scored_lines = []
        for idx, line in enumerate(lines):
            line_lower = line.lower()
            score = sum(1 for seg in segments if seg in line_lower)
            if score > 0:
                scored_lines.append((score, idx))

        if not scored_lines:
            # Fallback: try HTTP method filtering
            if http_method:
                method_lines = [
                    (0, idx) for idx, line in enumerate(lines)
                    if http_method.upper() in line.upper()
                ]
                if method_lines:
                    scored_lines = method_lines
                else:
                    return api_doc_text[:2000]
            else:
                return api_doc_text[:2000]

        scored_lines.sort(key=lambda x: x[0], reverse=True)
        top_indices = {idx for _, idx in scored_lines[:20]}

        # Expand to context windows (±5 lines)
        context_indices = set()
        for idx in top_indices:
            for ci in range(max(0, idx - 5), min(len(lines), idx + 6)):
                context_indices.add(ci)

        # Build snippet from contiguous ranges
        sorted_indices = sorted(context_indices)
        ranges = []
        start_range = sorted_indices[0]
        end_range = start_range
        for idx in sorted_indices[1:]:
            if idx <= end_range + 1:
                end_range = idx
            else:
                ranges.append((start_range, end_range))
                start_range = idx
                end_range = idx
        ranges.append((start_range, end_range))

        snippets = []
        total_tokens = 0
        for r_start, r_end in ranges:
            block = "\n".join(lines[r_start:r_end + 1])
            block_tokens = self._token_counter.count(block)
            if total_tokens + block_tokens > max_snippet_tokens:
                remaining = max_snippet_tokens - total_tokens
                if remaining > 200:
                    snippets.append(block[:remaining * 4])
                break
            snippets.append(block)
            total_tokens += block_tokens

        return "\n---\n".join(snippets) if snippets else api_doc_text[:2000]

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    def call_llm(
        self,
        prompt: str,
        system_msg: str = "You are a helpful assistant.",
        response_format: Optional[str] = None,
    ) -> str:
        """Call LLM with retry, global rate limiting, and concurrency control."""
        self.check_step()

        # Append skill extensions to system prompt
        if self._skill_extensions:
            system_msg = system_msg + "\n\n" + "\n\n".join(self._skill_extensions)

        # Context window check
        if not self._check_context_fit(system_msg, prompt):
            ratio = self._context_usage_ratio(system_msg, prompt)
            if ratio >= 1.0:
                raise ValueError(
                    f"Input exceeds context window: "
                    f"{self._estimate_input_tokens(system_msg, prompt)} / "
                    f"{self._context_window} tokens"
                )
            # 接近上下文限制 — 压缩累积历史以释放空间给后续轮次。
            # 不会修改当前请求的 system_msg 或用户指导（prompt 参数）。
            # Near limit — compress accumulated history to free space for
            # subsequent rounds. Does NOT modify the current request's
            # system_msg or user guidance (the prompt parameter).
            if self._round_count > 0:
                self._compress_conversation(system_msg)

        # Concurrency control — ensure at most max_concurrency requests in flight
        if BaseAgent._concurrency_semaphore:
            BaseAgent._concurrency_semaphore.acquire()

        try:
            last_error = None
            for attempt in range(1, self._max_retries + 1):
                # Global rate limiting: enforce minimum interval between calls
                # across ALL BaseAgent instances (class-level _last_call_time)
                with BaseAgent._call_lock:
                    if self._rate_limit_delay > 0:
                        elapsed = time.time() - BaseAgent._last_call_time
                        if elapsed < self._rate_limit_delay:
                            time.sleep(self._rate_limit_delay - elapsed)

                try:
                    kwargs: dict = {
                        "model": self._model,
                        "temperature": self._temperature,
                        "max_tokens": self._max_output_tokens,
                        "messages": [
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": prompt},
                        ],
                    }

                    if response_format == "json_object":
                        kwargs["response_format"] = {"type": "json_object"}

                    # 合并额外参数（如思考模式等厂商特定配置）
                    # Merge extra params (e.g. thinking mode, vendor-specific config)
                    if self._extra_params:
                        kwargs.update(self._extra_params)

                    response = self._client.chat.completions.create(**kwargs)
                    content = response.choices[0].message.content or ""
                    with BaseAgent._call_lock:
                        BaseAgent._last_call_time = time.time()
                    return content

                except Exception as e:
                    last_error = e
                    # Update timestamp even on failure — failed requests
                    # still consume rate-limit quota on providers like GLM
                    with BaseAgent._call_lock:
                        BaseAgent._last_call_time = time.time()
                    logger.warning(
                        "LLM call attempt %d/%d failed: %s",
                        attempt, self._max_retries, e,
                    )
                    if attempt < self._max_retries:
                        logger.info(
                            "LLM call attempt %d/%d failed (%s), retrying in %.1fs (attempt %d)...",
                            attempt, self._max_retries,
                            _short_error(e),
                            self._retry_base_delay, attempt + 1,
                        )
                        time.sleep(self._retry_base_delay)

            raise RuntimeError(
                f"LLM call failed after {self._max_retries} attempts: {last_error}"
            )
        finally:
            if BaseAgent._concurrency_semaphore:
                BaseAgent._concurrency_semaphore.release()

    def call_llm_json(
        self,
        prompt: str,
        system_msg: str = "You are a helpful assistant.",
    ) -> Any:
        """Call LLM and parse response as JSON.

        On parse failure, retries once with a fix-prompt asking the
        model to output valid JSON only.
        """
        text = self.call_llm(prompt, system_msg, response_format="json_object")
        try:
            return self._extract_json(text)
        except ValueError:
            logger.warning(
                "JSON parse failed (len=%d), retrying with fix prompt",
                len(text),
            )
            fix_prompt = (
                f"{JSON_FIX_PROMPT}\n\n"
                f"Original task:\n{prompt[:2000]}\n\n"
                f"The invalid JSON (may be truncated):\n{text[:3000]}"
            )
            retry_text = self.call_llm(
                fix_prompt, system_msg, response_format="json_object"
            )
            return self._extract_json(retry_text)

    def call_llm_json_object(
        self,
        prompt: str,
        system_msg: str = "You are a helpful assistant.",
        json_key: str = "result",
    ) -> dict:
        """调用 LLM 并解析 JSON 响应，确保返回 dict。
        Call LLM and parse JSON response, ensuring the result is a dict.

        非 OpenAI 兼容 API 可能返回裸数组，此方法自动包装为 {json_key: array}。
        Non-OpenAI APIs may return bare arrays; wraps them as {json_key: array}.

        Args:
            prompt: 用户提示词 / User prompt.
            system_msg: 系统消息 / System message.
            json_key: 包装裸数组时使用的 key / Key used when wrapping bare arrays.

        Returns:
            dict: 解析后的 JSON 对象 / Parsed JSON object.
        """
        result = self.call_llm_json(prompt, system_msg)
        # 防护：非 OpenAI 兼容 API 可能返回裸数组 / Guard: bare array from non-OpenAI APIs
        if isinstance(result, list):
            result = {json_key: result}
        return result

    @staticmethod
    def _extract_json_by_brace_count(text: str) -> str | None:
        """Extract the outermost JSON object/array using brace counting.

        Unlike greedy regex, this handles nested structures correctly
        and stops at the matching close-brace. Returns None if no
        balanced braces are found (truncated JSON).
        """
        start_obj = text.find("{")
        start_arr = text.find("[")

        if start_obj == -1 and start_arr == -1:
            return None

        if start_obj != -1 and (start_arr == -1 or start_obj < start_arr):
            start = start_obj
            open_char, close_char = "{", "}"
        else:
            start = start_arr
            open_char, close_char = "[", "]"

        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == open_char:
                depth += 1
            elif ch == close_char:
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

        return None

    @staticmethod
    def _extract_json(text: str) -> Any:
        """Extract and parse JSON from LLM response.

        Handles responses wrapped in ```json fences or plain text.
        Uses brace counting for precise extraction of nested structures.
        """
        text = text.strip()

        # Try direct parse first
        try:
            return json.loads(text)
        except (json.JSONDecodeError, RecursionError):
            pass

        # Try extracting from ```json ... ``` fence
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except (json.JSONDecodeError, RecursionError):
                pass

        # Try extracting from ``` ... ``` fence
        match = re.search(r"```\s*([\s\S]*?)\s*```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except (json.JSONDecodeError, RecursionError):
                pass

        # Brace-counting extraction (replaces greedy regex)
        extracted = BaseAgent._extract_json_by_brace_count(text)
        if extracted is not None:
            try:
                return json.loads(extracted)
            except (json.JSONDecodeError, RecursionError):
                pass

        # Detect truncation
        last_char = text.rstrip()[-1] if text.rstrip() else ""
        if last_char not in ("}", "]", '"'):
            logger.warning(
                "JSON response may be truncated (ends with %r), length=%d",
                last_char, len(text),
            )

        raise ValueError(
            f"Failed to parse JSON from LLM response len: {len(text)} "
            f"text:\n{text[:500]}"
        )


