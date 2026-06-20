"""BaseAgent + ReAct agent factory with termination protection."""

from __future__ import annotations

import json
import hashlib
import logging
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from openai import OpenAI
from typing_extensions import Annotated

from models.state import AgentConfig, ReActTerminationConfig

logger = logging.getLogger(__name__)


class ConvergenceError(Exception):
    """Raised when an agent exceeds its max_steps limit."""


class ReActTerminationReason(Enum):
    MAX_ITERATIONS = "max_iterations"
    MAX_TOOL_CALLS = "max_tool_calls"
    TIMEOUT = "timeout"
    TOKEN_BUDGET = "token_budget"
    NO_PROGRESS = "no_progress"
    COMPLETED = "completed"


# ---------------------------------------------------------------------------
# ReAct State
# ---------------------------------------------------------------------------
class ReActState(TypedDict, total=False):
    messages: Annotated[List, add_messages]
    iteration_count: int
    tool_call_count: int
    start_time: float
    last_tool_name: str
    last_tool_result_hash: str
    consecutive_same_tool: int
    consecutive_same_result: int
    termination_reason: str
    result: Any


# ---------------------------------------------------------------------------
# BaseAgent (preserved for backward compatibility)
# ---------------------------------------------------------------------------
class BaseAgent:
    """Base class for all LLM-powered agents.

    Provides:
    - OpenAI-compatible LLM call
    - Automatic retry with exponential backoff
    - Structured JSON output parsing
    - Step counter with max_steps guard
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        max_retries: int = 3,
        max_steps: int = 10,
        base_url: str = "",
        context_window: int = 128000,
        max_output_tokens: int = 4096,
        compression_threshold: float = 0.9,
        rate_limit_delay: float = 0.0,
        retry_base_delay: float = 2.0,
    ):
        client_kwargs: Dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = OpenAI(**client_kwargs)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._max_steps = max_steps
        self._rate_limit_delay = rate_limit_delay
        self._retry_base_delay = retry_base_delay
        self._last_call_time: float = 0.0
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
        """Compress accumulated conversation history into a concise summary.

        Calls the LLM to distill prior rounds into key points, replacing
        verbose history with a compact summary.  Updates _conversation_summary
        and resets _conversation_tokens.
        """
        if not self._conversation_summary and self._round_count <= 1:
            return ""

        compress_prompt = (
            "请将以下对话历史和中间结果精简为关键要点摘要，"
            "保留所有重要的数据、结论和决策。"
            "丢弃重复内容和不必要的细节。"
            f"\n\n历史内容:\n{self._conversation_summary}"
        )
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
            notice = chunk_notice or f"[这是第 {i + 1}/{total} 块，后面还有内容，请继续处理]"
            chunk_with_notice = f"{notice}\n\n{chunk}"

            # Check context before each round
            if not self._check_context_fit(system_msg, chunk_with_notice):
                self._compress_conversation(system_msg)
                if self._conversation_summary:
                    chunk_with_notice = (
                        f"[前文摘要]\n{self._conversation_summary}\n\n"
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
        """Call LLM with retry and context window awareness. Returns raw text response."""
        self.check_step()

        # Context window check
        if not self._check_context_fit(system_msg, prompt):
            ratio = self._context_usage_ratio(system_msg, prompt)
            if ratio >= 1.0:
                raise ValueError(
                    f"Input exceeds context window: "
                    f"{self._estimate_input_tokens(system_msg, prompt)} / "
                    f"{self._context_window} tokens"
                )
            # Near limit — try compression for multi-round scenarios
            if self._round_count > 0:
                self._compress_conversation(system_msg)

        # Rate limiting: enforce minimum interval between calls
        if self._rate_limit_delay > 0:
            elapsed = time.time() - self._last_call_time
            if elapsed < self._rate_limit_delay:
                time.sleep(self._rate_limit_delay - elapsed)

        last_error = None
        for attempt in range(1, self._max_retries + 1):
            try:
                kwargs: dict = {
                    "model": self._model,
                    "temperature": self._temperature,
                    "max_tokens": self._max_tokens,
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt},
                    ],
                }

                if response_format == "json_object":
                    kwargs["response_format"] = {"type": "json_object"}

                response = self._client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content or ""
                self._last_call_time = time.time()
                return content

            except Exception as e:
                last_error = e
                logger.warning(
                    "LLM call attempt %d/%d failed: %s",
                    attempt, self._max_retries, e,
                )
                if attempt < self._max_retries:
                    time.sleep(self._retry_base_delay ** attempt)

        raise RuntimeError(
            f"LLM call failed after {self._max_retries} attempts: {last_error}"
        )

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
                "你上一次的回复不是合法的 JSON。请严格只输出一个 JSON 对象，"
                "不要包含任何 markdown 标记、解释文字或其他非 JSON 内容。"
            )
            retry_text = self.call_llm(
                fix_prompt, system_msg, response_format="json_object"
            )
            return self._extract_json(retry_text)

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


# =========================================================================
# ReAct Agent Factory (with multi-layer termination protection)
# =========================================================================

def create_react_agent(
    llm: Any,
    tools: List[Any],
    system_prompt: str,
    termination: ReActTerminationConfig | None = None,
) -> StateGraph:
    """Create a ReAct sub-graph with termination protection.

    The returned subgraph alternates between an *agent* node (LLM with bound
    tools) and a *tools* node (executes tool calls).  Every iteration is
    checked against the termination config; when a limit is hit the graph
    is routed to a *forced_termination* node that applies a graceful
    degradation strategy instead of crashing.

    Args:
        llm: A LangChain ChatModel (e.g. ChatOpenAI).
        tools: List of LangChain tools (or BaseTool instances).
        system_prompt: System prompt for the LLM.
        termination: Optional termination config (uses defaults if None).

    Returns:
        A compiled StateGraph (subgraph).
    """
    if termination is None:
        termination = ReActTerminationConfig()

    graph = StateGraph(ReActState)

    graph.add_node("agent", _make_agent_node(llm, tools, system_prompt))
    graph.add_node("tools", _make_tool_node(tools))
    graph.add_node("forced_termination", _make_termination_node(llm))

    graph.set_entry_point("agent")

    graph.add_conditional_edges(
        "agent",
        lambda s: _route_with_termination_check(s, termination),
        {
            "call_tools": "tools",
            "end": END,
            "forced_termination": "forced_termination",
        },
    )
    graph.add_edge("tools", "agent")
    graph.add_edge("forced_termination", END)

    return graph.compile()


# ------------------------------------------------------------------
# Node factories
# ------------------------------------------------------------------

def _make_agent_node(llm, tools, system_prompt):
    """Return a callable that invokes the LLM with tools bound."""

    def agent_node(state: ReActState) -> ReActState:
        messages = state.get("messages", [])
        # Insert system prompt if this is the first call
        if not messages or messages[0].get("role") != "system":
            from langchain_core.messages import SystemMessage

            messages = [SystemMessage(content=system_prompt)] + list(messages)

        # Bind tools
        llm_with_tools = llm.bind_tools(tools) if tools else llm
        response = llm_with_tools.invoke(messages)

        new_state: ReActState = {
            "messages": [response],
            "iteration_count": state.get("iteration_count", 0),
            "tool_call_count": state.get("tool_call_count", 0),
            "start_time": state.get("start_time", time.time()),
            "last_tool_name": state.get("last_tool_name", ""),
            "last_tool_result_hash": state.get("last_tool_result_hash", ""),
            "consecutive_same_tool": state.get("consecutive_same_tool", 0),
            "consecutive_same_result": state.get("consecutive_same_result", 0),
            "termination_reason": state.get("termination_reason", ""),
        }
        return new_state

    return agent_node


def _make_tool_node(tools):
    """Return a callable that executes tool calls from the last message."""
    from langchain_core.messages import ToolMessage

    tool_map = {t.name: t for t in tools}

    def tool_node(state: ReActState) -> ReActState:
        last_msg = state["messages"][-1]
        tool_calls = getattr(last_msg, "tool_calls", []) or []

        results = []
        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("args", {})
            tid = tc.get("id", "")
            tool = tool_map.get(name)
            if tool:
                try:
                    result = str(tool.invoke(args))
                except Exception as e:
                    result = f"ERROR: {e}"
            else:
                result = f"ERROR: unknown tool '{name}'"
            results.append(ToolMessage(content=result, tool_call_id=tid))

        # Detect no-progress
        last_hash = state.get("last_tool_result_hash", "")
        new_hash = _hash_results(results)
        same_tool = (
            tool_calls
            and state.get("last_tool_name") == tool_calls[0].get("name")
        )

        return {
            "messages": results,
            "tool_call_count": state.get("tool_call_count", 0) + len(tool_calls),
            "last_tool_name": tool_calls[0].get("name") if tool_calls else "",
            "last_tool_result_hash": new_hash,
            "consecutive_same_tool": (state.get("consecutive_same_tool", 0) + 1)
            if same_tool
            else 0,
            "consecutive_same_result": (state.get("consecutive_same_result", 0) + 1)
            if new_hash == last_hash
            else 0,
        }

    return tool_node


def _make_termination_node(llm):
    """Graceful degradation — ask LLM for final answer based on history."""

    def termination_node(state: ReActState) -> ReActState:
        reason = state.get("termination_reason", "")
        logger.warning("ReAct terminated: %s", reason)

        from langchain_core.messages import HumanMessage

        final_prompt = (
            "根据以上所有信息和工具调用结果，请给出你当前的最佳答案。"
            "不要再调用工具，直接输出最终结果。"
        )
        messages = list(state.get("messages", []))
        try:
            response = llm.invoke(messages + [HumanMessage(content=final_prompt)])
            state["messages"] = [response]
            state["result"] = response.content
        except Exception:
            # LLM also failed — just return last non-tool message
            for m in reversed(messages):
                if not hasattr(m, "tool_calls") or not getattr(m, "tool_calls", None):
                    state["result"] = getattr(m, "content", "")
                    break

        return state

    return termination_node


# ------------------------------------------------------------------
# Routing
# ------------------------------------------------------------------

def _route_with_termination_check(
    state: ReActState,
    config: ReActTerminationConfig,
) -> str:
    """Check all termination layers and return the next route."""
    from langchain_core.messages import AIMessage

    last_msg = state.get("messages", [None])[-1] if state.get("messages") else None
    has_tool_calls = bool(getattr(last_msg, "tool_calls", None))

    # Normal completion — LLM returned final answer
    if not has_tool_calls:
        state["termination_reason"] = ReActTerminationReason.COMPLETED.value
        return "end"

    # Layer 1 — hard limits
    state["iteration_count"] = state.get("iteration_count", 0) + 1
    if state["iteration_count"] > config.max_iterations:
        state["termination_reason"] = ReActTerminationReason.MAX_ITERATIONS.value
        return "forced_termination"

    if state.get("tool_call_count", 0) > config.max_tool_calls_total:
        state["termination_reason"] = ReActTerminationReason.MAX_TOOL_CALLS.value
        return "forced_termination"

    elapsed = time.time() - state.get("start_time", time.time())
    if elapsed > config.max_time_seconds:
        state["termination_reason"] = ReActTerminationReason.TIMEOUT.value
        return "forced_termination"

    # Layer 2 — token budget (rough estimate)
    estimated = _estimate_token_count(state.get("messages", []))
    if estimated > config.max_input_tokens:
        state["termination_reason"] = ReActTerminationReason.TOKEN_BUDGET.value
        return "forced_termination"

    # Layer 3 — no-progress
    if state.get("consecutive_same_tool", 0) > config.max_consecutive_same_tool:
        state["termination_reason"] = ReActTerminationReason.NO_PROGRESS.value
        return "forced_termination"

    if state.get("consecutive_same_result", 0) > config.max_consecutive_no_result_change:
        state["termination_reason"] = ReActTerminationReason.NO_PROGRESS.value
        return "forced_termination"

    return "call_tools"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _estimate_token_count(messages: List) -> int:
    """Rough token count estimator: ~4 chars per token."""
    total = 0
    for m in messages:
        content = getattr(m, "content", "") or ""
        total += len(content) // 4
    return total


def _hash_results(results: List) -> str:
    """Stable hash of tool result strings."""
    h = hashlib.md5()
    for r in results:
        h.update(getattr(r, "content", "").encode("utf-8", errors="replace"))
    return h.hexdigest()
