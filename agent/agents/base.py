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
        self._step_count = 0

    def check_step(self) -> None:
        """Increment step counter, raise if max_steps exceeded."""
        self._step_count += 1
        if self._step_count > self._max_steps:
            raise ConvergenceError(
                f"Agent exceeded max_steps ({self._max_steps})"
            )

    def reset_steps(self) -> None:
        self._step_count = 0

    def call_llm(
        self,
        prompt: str,
        system_msg: str = "You are a helpful assistant.",
        response_format: Optional[str] = None,
    ) -> str:
        """Call LLM with retry. Returns raw text response."""
        self.check_step()

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
                return content

            except Exception as e:
                last_error = e
                logger.warning(
                    "LLM call attempt %d/%d failed: %s",
                    attempt, self._max_retries, e,
                )
                if attempt < self._max_retries:
                    time.sleep(2 ** attempt)

        raise RuntimeError(
            f"LLM call failed after {self._max_retries} attempts: {last_error}"
        )

    def call_llm_json(
        self,
        prompt: str,
        system_msg: str = "You are a helpful assistant.",
    ) -> Any:
        """Call LLM and parse response as JSON."""
        text = self.call_llm(prompt, system_msg, response_format="json_object")
        return self._extract_json(text)

    @staticmethod
    def _extract_json(text: str) -> Any:
        """Extract and parse JSON from LLM response.

        Handles responses wrapped in ```json fences or plain text.
        """
        # Try direct parse first
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from ```json ... ``` fence
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try extracting from ``` ... ``` fence
        match = re.search(r"```\s*([\s\S]*?)\s*```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find a JSON object/array in the text
        brace_match = re.search(r'\{[\s\S]*\}', text)
        bracket_match = re.search(r'\[[\s\S]*\]', text)

        for m in (brace_match, bracket_match):
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    continue

        raise ValueError(f"Failed to parse JSON from LLM response:\n{text[:500]}")


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
