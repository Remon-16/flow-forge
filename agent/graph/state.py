"""LangGraph 全局状态 TypedDict — 在主工作流节点间传递。

LangGraph global state TypedDict — passed between nodes in the main workflow.
"""

from typing import Any, Dict, List, TypedDict

from langgraph.graph.message import add_messages
from typing_extensions import Annotated


class GraphState(TypedDict, total=False):
    """用例生成流水线的全局状态，每个 key 由一个节点写入、下游节点读取。

    State carried through the test-case-generation pipeline.
    Each key is written by one node and read by downstream nodes.
    """

    # === 输入 / Input ===
    requirement_paths: List[str]
    api_paths: List[str]
    output_path: str
    plan_only: bool

    # === 输出配置 / Output config ===
    output_dir: str             # Output root directory
    cases_dir: str              # Test case output subdirectory ({output_dir}/cases)
    memory_dir: str             # Agent output subdirectory ({output_dir}/memory)
    debug_snapshots: bool       # Save optional debug snapshots
    output_format: str          # "yaml" | "excel" | "both"
    batch_size: int             # Max cases per batch
    case_format_enabled: bool     # Whether to run case validation
    case_format_max_retries: int # Max case format validation retries
    case_type: str              # "both" | "single" | "biz"

    # === 文档解析 / Document parsing ===
    requirement_texts: List[str]
    interfaces: List[Dict[str, Any]]
    api_raw_text: str          # Raw text of API doc (for --parse-mode raw) — 多文件拼接，供 URL 校验
    api_raw_texts: List[Dict[str, str]]  # 逐文件原文 [{"path": "...", "text": "..."}]，供独立 LLM 分析 / Per-file raw texts for per-file LLM analysis
    parse_mode: str            # "raw" | "rule" | "llm"
    parser_path: str           # Custom parser script path

    # === 需求分析 / Requirement analysis ===
    requirement_analysis: Dict[str, Any]

    # === 计划生成 / Plan generation ===
    plan_outline: Dict[str, Any]   # 测试计划轮廓 JSON / Test plan outline JSON
    plan_md: str
    plan_md_path: str
    plan_parsed: Any  # 从 plan.md 解析的结构化计划 / Structured TestPlan
    user_guidance: str  # 用户通过 --prompt 传入的指导 / User guidance from --prompt

    # === 接口分析 / API Analysis ===
    api_summary: List[Dict[str, Any]]
    api_summary_feedback: str
    api_summary_confirmed: bool

    # === 接口 URL 校验 / Interface URL validation ===
    url_validation_errors: List[Dict[str, Any]]

    # === 自动与审核 / Auto & review ===
    auto_mode: bool  # 自动模式：跳过所有人工审核 / Auto mode: skip all human review
    plan_confirmed: bool
    plan_feedback: str
    plan_feedback_type: str          # "text" | "annotations"
    plan_annotations: List[Dict[str, Any]]  # 解析后的 plan_comments.json

    # === 用例生成 / Case generation ===
    single_cases: List[Dict[str, Any]]
    biz_flows: List[Dict[str, Any]]

    # === 批次追踪 / Batch tracking ===
    batch_state: Dict[str, Any]          # 批次生成进度 / Batch generation progress
    validation_failures: List[Dict]      # 校验失败的用例 / Cases that failed validation

    # === 断点续写 & 增量 / Resume & incremental ===
    resume: bool                         # 从已有 output_dir 跳到批次生成
    resume_overwrite: bool               # 续写时覆盖已有输出
    reference_dir: str                   # 增量更新参考目录

    # === 消息 / Messages ===
    messages: Annotated[List, add_messages]

    # === 错误 / Errors ===
    errors: List[str]
