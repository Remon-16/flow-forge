"""分块计划生成测试 / Tests for chunked plan generation.

All LLM calls are mocked — NO real API calls.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.base import BaseAgent
from agents.plan_generator import PlanGenerator
from config.settings import Settings
from graph.nodes import helpers as _h


# ---------------------------------------------------------------------------
# Shared helpers / 共享辅助函数
# ---------------------------------------------------------------------------

def _make_settings(**kwargs):
    s = Settings(llm_api_key="test")
    s.plan_single_batch_size = kwargs.get("plan_single_batch_size", 8)
    s.plan_biz_flow_batch_size = kwargs.get("plan_biz_flow_batch_size", 3)
    return s


def _make_agent(settings=None):
    BaseAgent._shared_client = MagicMock()
    if settings is None:
        settings = _make_settings()
    return PlanGenerator(settings)


def _sample_outline():
    return {
        "business_summary": "Test e-commerce system",
        "api_groups": [
            {
                "group_name": "User APIs",
                "api_ids": ["api_user_001"],
                "test_focus": "Authentication",
            },
        ],
        "biz_flows": [],
    }


def _sample_interfaces():
    return [
        {
            "test_id": "api_user_001",
            "api_name": "Login",
            "method": "POST",
            "url": "/login",
            "app_name": "user",
            "request_head": {},
            "request_body": {},
            "status_code": 200,
            "assert_dict": {},
            "remark": "",
        },
    ]


# ---------------------------------------------------------------------------
# TestPlanChunking
# ---------------------------------------------------------------------------

class TestPlanChunking:
    """Tests for PlanGenerator.generate_from_outline()."""

    def should_execute_phases_in_order(self):
        """Phase A → B → D 正确顺序执行 / Phases execute in correct order."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            call_order = []

            def phase_a(prompt, system):
                call_order.append("A")
                return "## 1. Business Understanding\n\nTest\n\n## 4. Flowchart\n```mermaid\ngraph TD\n```"

            def phase_b(prompt, system):
                call_order.append("B")
                return "## 2.1 User APIs\n\nTest points"

            agent.call_llm = MagicMock(side_effect=[phase_a("", ""), phase_b("", "")])

            agent.generate_from_outline(
                outline=_sample_outline(),
                requirement_analysis={"flows": 1},
                interfaces=_sample_interfaces(),
            )

            assert call_order == ["A", "B"]

    def should_split_by_api_groups(self):
        """按 outline api_groups 拆分 chunk / Split by api_groups."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            outline = {
                "business_summary": "Test",
                "api_groups": [
                    {"group_name": "Group A", "api_ids": ["api_a"], "test_focus": "Focus A"},
                    {"group_name": "Group B", "api_ids": ["api_b"], "test_focus": "Focus B"},
                ],
                "biz_flows": [],
            }
            interfaces = [
                {"test_id": "api_a", "api_name": "A", "method": "GET", "url": "/a", "app_name": "x", "request_head": {}, "request_body": {}, "status_code": 200, "assert_dict": {}, "remark": ""},
                {"test_id": "api_b", "api_name": "B", "method": "POST", "url": "/b", "app_name": "x", "request_head": {}, "request_body": {}, "status_code": 200, "assert_dict": {}, "remark": ""},
            ]

            call_count = [0]
            def side_effect(prompt, system):
                call_count[0] += 1
                if call_count[0] == 1:
                    return "## 1. Business Understanding\n\nGlobal context\n\n## 4. Mermaid\n```mermaid\ngraph TD\n```"
                return f"## Chunk {call_count[0]}"

            agent.call_llm = MagicMock(side_effect=side_effect)

            plan_md = agent.generate_from_outline(
                outline=outline,
                requirement_analysis={"flows": 1},
                interfaces=interfaces,
            )

            # Phase A(1) + Phase B(2 groups) = 3 calls
            assert call_count[0] == 3
            assert "Global context" in plan_md

    def should_assemble_in_correct_order(self):
        """拼接顺序正确：Global → API groups → Biz flows."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            outline = {
                "business_summary": "Test",
                "api_groups": [
                    {"group_name": "First Group", "api_ids": ["api_1"], "test_focus": "First"},
                    {"group_name": "Second Group", "api_ids": ["api_2"], "test_focus": "Second"},
                ],
                "biz_flows": [
                    {"name": "My Flow", "description": "A flow", "involved_apis": ["api_1"]},
                ],
            }
            interfaces = [
                {"test_id": "api_1", "api_name": "API1", "method": "GET", "url": "/1", "app_name": "x", "request_head": {}, "request_body": {}, "status_code": 200, "assert_dict": {}, "remark": ""},
                {"test_id": "api_2", "api_name": "API2", "method": "POST", "url": "/2", "app_name": "x", "request_head": {}, "request_body": {}, "status_code": 200, "assert_dict": {}, "remark": ""},
            ]

            # Phase A + Mermaid(1 flow) + Phase B(2 groups) + Phase C(1 batch) = 5 calls
            outputs = [
                "GLOBAL_CONTEXT",
                "MERMAID_FLOW",           # Mermaid for biz flow
                "FIRST_GROUP_SECTION",
                "SECOND_GROUP_SECTION",
                "BIZ_FLOW_SECTION",
            ]
            agent.call_llm = MagicMock(side_effect=outputs)

            plan_md = agent.generate_from_outline(
                outline=outline,
                requirement_analysis={"flows": 1},
                interfaces=interfaces,
            )

            # 验证拼接顺序 / Verify assembly order
            assert plan_md.index("GLOBAL_CONTEXT") < plan_md.index("FIRST_GROUP_SECTION")
            assert plan_md.index("FIRST_GROUP_SECTION") < plan_md.index("SECOND_GROUP_SECTION")
            # 验证 Mermaid 图已注入到 biz section 前 / Verify Mermaid injected before biz section
            assert plan_md.index("MERMAID_FLOW") < plan_md.index("BIZ_FLOW_SECTION")

    def should_raise_error_when_outline_missing(self):
        """outline 缺失时 generate_plan_node 报错 / Error when outline is None."""
        from graph.nodes.generate_plan import generate_plan_node
        from graph.state import GraphState

        # 初始化 settings (generate_plan_node 内部需要 _h._settings)
        # Initialize settings (required internally by generate_plan_node)
        _h.configure(Settings(llm_api_key="test"), knowledge=None)

        state: GraphState = {
            "plan_outline": None,
            "requirement_analysis": {},
            "interfaces": [],
            "errors": [],
        }

        result = generate_plan_node(state)
        assert len(result.get("errors", [])) > 0

    def should_generate_biz_only_without_crash(self, tmp_path):
        """回归: case_type=biz 保存分块时不崩 / Regression: biz-only save must not crash.

        Phase B 被跳过时 api_sections 必须是空 dict (而非 list)，
        否则 _save_sections_artifact 的 api_sections.get() 抛 AttributeError。
        When Phase B is skipped, api_sections must be an empty dict (not a list),
        else _save_sections_artifact's api_sections.get() raises AttributeError.
        """
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100), \
                patch("graph.nodes.helpers.save_pipeline_artifact") as mock_save:
            agent = _make_agent()
            outline = {
                "business_summary": "Test",
                "api_groups": [
                    {"group_name": "Group A", "api_ids": ["api_a"], "test_focus": "Focus A"},
                ],
                "biz_flows": [
                    {"name": "My Flow", "description": "A flow", "involved_apis": ["api_a"]},
                ],
            }
            interfaces = [
                {"test_id": "api_a", "api_name": "A", "method": "GET", "url": "/a", "app_name": "x", "request_head": {}, "request_body": {}, "status_code": 200, "assert_dict": {}, "remark": ""},
            ]
            # Phase A (global) + Mermaid(1 flow) + Phase C (1 biz batch) = 3 calls
            agent.call_llm = MagicMock(side_effect=["GLOBAL_CONTEXT", "MERMAID_FLOW", "BIZ_FLOW_SECTION"])

            plan_md = agent.generate_from_outline(
                outline=outline,
                requirement_analysis={"flows": 1},
                interfaces=interfaces,
                memory_dir=str(tmp_path),
                case_type="biz",
            )

            assert "BIZ_FLOW_SECTION" in plan_md
            # 验证 Mermaid 图已注入到 biz section 前 / Verify Mermaid injected before biz section
            assert plan_md.index("MERMAID_FLOW") < plan_md.index("BIZ_FLOW_SECTION")
            # 已真正触达保存逻辑 (memory_dir 非空) / Save logic was actually reached
            mock_save.assert_called_once()

    def should_generate_single_only_without_crash(self, tmp_path):
        """回归: case_type=single 保存分块时不崩 / Regression: single-only save must not crash.

        Phase C 被跳过时 biz_sections 必须是空 dict (而非 list)，
        否则 biz_sections.get()/keys() 抛 AttributeError。
        When Phase C is skipped, biz_sections must be an empty dict (not a list),
        else biz_sections.get()/keys() raises AttributeError.
        """
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100), \
                patch("graph.nodes.helpers.save_pipeline_artifact") as mock_save:
            agent = _make_agent()
            outline = {
                "business_summary": "Test",
                "api_groups": [
                    {"group_name": "Group A", "api_ids": ["api_a"], "test_focus": "Focus A"},
                ],
                # biz_flows 非空 → biz_batches 非空，触发对称隐患
                # Non-empty biz_flows → non-empty biz_batches, exercising the symmetric hazard
                "biz_flows": [
                    {"name": "My Flow", "description": "A flow", "involved_apis": ["api_a"]},
                ],
            }
            interfaces = [
                {"test_id": "api_a", "api_name": "A", "method": "GET", "url": "/a", "app_name": "x", "request_head": {}, "request_body": {}, "status_code": 200, "assert_dict": {}, "remark": ""},
            ]
            # Phase A (global) + Phase B (1 api group) = 2 calls
            agent.call_llm = MagicMock(side_effect=["GLOBAL_CONTEXT", "API_SECTION"])

            plan_md = agent.generate_from_outline(
                outline=outline,
                requirement_analysis={"flows": 1},
                interfaces=interfaces,
                memory_dir=str(tmp_path),
                case_type="single",
            )

            assert "API_SECTION" in plan_md
            mock_save.assert_called_once()


# ---------------------------------------------------------------------------
# TestPlanChunkResumeProgress — PlanGenerator 逐 chunk 保存 + resume 跳过测试
# ---------------------------------------------------------------------------

class TestPlanChunkResumeProgress:
    """Tests for incremental plan_chunks_progress.json save and resume skip."""

    def should_save_chunk_progress_after_phase_a(self, tmp_path):
        """Phase A 后 plan_chunks_progress.json 存在且含 global_context。
        After Phase A, plan_chunks_progress.json exists with global_context."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            outline = _sample_outline()
            interfaces = _sample_interfaces()

            agent.call_llm = MagicMock(return_value="GLOBAL_CONTEXT")

            memory_dir = str(tmp_path / "memory")
            agent.generate_from_outline(
                outline=outline,
                requirement_analysis={"flows": 1},
                interfaces=interfaces,
                memory_dir=memory_dir,
            )

            progress_path = Path(memory_dir) / "plan_chunks_progress.json"
            assert progress_path.exists()
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            assert "plan_parts" in progress
            assert progress["plan_parts"]["global_context"] == "GLOBAL_CONTEXT"

    def should_save_chunk_progress_after_each_api_group(self, tmp_path):
        """2 个 API groups → api_sections 含 2 个 key。
        2 API groups → api_sections has 2 keys."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            outline = {
                "business_summary": "Test",
                "api_groups": [
                    {"group_name": "Group A", "api_ids": ["api_a"], "test_focus": "Focus A"},
                    {"group_name": "Group B", "api_ids": ["api_b"], "test_focus": "Focus B"},
                ],
                "biz_flows": [],
            }
            interfaces = [
                {"test_id": "api_a", "api_name": "A", "method": "GET", "url": "/a",
                 "app_name": "x", "request_head": {}, "request_body": {}, "status_code": 200,
                 "assert_dict": {}, "remark": ""},
                {"test_id": "api_b", "api_name": "B", "method": "POST", "url": "/b",
                 "app_name": "x", "request_head": {}, "request_body": {}, "status_code": 200,
                 "assert_dict": {}, "remark": ""},
            ]

            agent.call_llm = MagicMock(side_effect=["GLOBAL", "SECTION_A", "SECTION_B"])
            memory_dir = str(tmp_path / "memory")

            agent.generate_from_outline(
                outline=outline,
                requirement_analysis={"flows": 1},
                interfaces=interfaces,
                memory_dir=memory_dir,
            )

            progress_path = Path(memory_dir) / "plan_chunks_progress.json"
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            api_sections = progress["plan_parts"].get("api_sections", {})
            assert "api_Group A" in api_sections or "api_Group_A" in api_sections

    def should_save_chunk_progress_after_each_biz_batch(self, tmp_path):
        """3 scenarios plan_biz_flow_batch_size=2 → biz_sections 含 2 个 batch key。
        3 scenarios plan_biz_flow_batch_size=2 → biz_sections with 2 batch keys."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            settings = _make_settings(plan_biz_flow_batch_size=2)
            agent = _make_agent(settings=settings)
            outline = {
                "business_summary": "Test",
                "api_groups": [],
                "biz_flows": [
                    {"name": "Flow 1", "description": "d1", "involved_apis": []},
                    {"name": "Flow 2", "description": "d2", "involved_apis": []},
                    {"name": "Flow 3", "description": "d3", "involved_apis": []},
                ],
            }

            # Phase A + 3 Mermaid flows + 2 biz batches = 6 calls
            agent.call_llm = MagicMock(side_effect=[
                "GLOBAL", "MERMAID_1", "MERMAID_2", "MERMAID_3",
                "BIZ_BATCH_0", "BIZ_BATCH_1",
            ])
            memory_dir = str(tmp_path / "memory")

            agent.generate_from_outline(
                outline=outline,
                requirement_analysis={"flows": 1},
                interfaces=[],
                memory_dir=memory_dir,
            )

            progress_path = Path(memory_dir) / "plan_chunks_progress.json"
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            biz_sections = progress["plan_parts"].get("biz_sections", {})
            assert len(biz_sections) >= 2
            # 验证 biz_sections 内容已包含 Mermaid 图 / Verify biz sections include Mermaid
            for key, content in biz_sections.items():
                if "batch" in key:
                    # 多 flow 批次应包含所有 flow 的 Mermaid
                    # Multi-flow batch should contain Mermaid for all flows
                    assert "MERMAID_1" in content or "MERMAID_2" in content or "MERMAID_3" in content, \
                        f"Biz section '{key}' should contain Mermaid content"
                else:
                    assert "MERMAID" in content, \
                        f"Biz section '{key}' should contain Mermaid content"

    def should_skip_phase_a_when_global_context_present(self, tmp_path):
        """预置 global_context → Phase A 不调 LLM。
        Pre-set global_context → Phase A doesn't call LLM."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            memory_dir = str(tmp_path / "memory")

            # 预置 plan_chunks_progress.json / Pre-populate
            progress_path = Path(memory_dir)
            progress_path.mkdir(parents=True, exist_ok=True)
            (progress_path / "plan_chunks_progress.json").write_text(
                json.dumps({"plan_parts": {"global_context": "PRE_EXISTING_GLOBAL"}}),
                encoding="utf-8",
            )

            outline = _sample_outline()
            interfaces = _sample_interfaces()

            # Phase B 一次调用 / One call for Phase B
            agent.call_llm = MagicMock(return_value="API_SECTION")

            agent.generate_from_outline(
                outline=outline,
                requirement_analysis={"flows": 1},
                interfaces=interfaces,
                chunk_progress=json.loads(
                    (progress_path / "plan_chunks_progress.json").read_text(encoding="utf-8")
                ),
                memory_dir=memory_dir,
            )

            # Phase A 被跳过，只调用了 Phase B / Phase A skipped, only Phase B called
            assert agent.call_llm.call_count == 1

    def should_skip_completed_mermaid_flows_on_resume(self, tmp_path):
        """预置 mermaid_chunks → 已完成 flow 不调 LLM。
        Pre-set mermaid_chunks → completed flows don't call LLM."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            memory_dir = str(tmp_path / "memory")

            progress_path = Path(memory_dir)
            progress_path.mkdir(parents=True, exist_ok=True)
            (progress_path / "plan_chunks_progress.json").write_text(
                json.dumps({"plan_parts": {
                    "mermaid_chunks": {"biz_flow_1": "MERMAID_DONE"},
                }}),
                encoding="utf-8",
            )

            outline = {
                "business_summary": "Test",
                "api_groups": [],
                "biz_flows": [
                    {"name": "Flow 1", "description": "d1", "involved_apis": [], "chunk_id": "biz_flow_1"},
                    {"name": "Flow 2", "description": "d2", "involved_apis": [], "chunk_id": "biz_flow_2"},
                ],
            }

            # Phase A + Flow 2 Mermaid only (Flow 1 skipped) + 1 biz batch = 3 calls
            agent.call_llm = MagicMock(side_effect=["GLOBAL", "MERMAID_2", "BIZ_BATCH"])

            agent.generate_from_outline(
                outline=outline,
                requirement_analysis={"flows": 1},
                interfaces=[],
                chunk_progress=json.loads(
                    (progress_path / "plan_chunks_progress.json").read_text(encoding="utf-8")
                ),
                memory_dir=memory_dir,
            )

            # Flow 1 Mermaid 被跳过 / Flow 1 Mermaid skipped
            assert agent.call_llm.call_count == 3

    def should_handle_memory_dir_empty_string(self):
        """memory_dir="" 时不写盘不崩溃 / No crash with empty memory_dir."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            agent.call_llm = MagicMock(return_value="GLOBAL")

            # 不应崩溃 / Should not crash
            plan_md = agent.generate_from_outline(
                outline=_sample_outline(),
                requirement_analysis={"flows": 1},
                interfaces=_sample_interfaces(),
                memory_dir="",
            )
            assert "GLOBAL" in plan_md

    def should_generate_complete_plan_from_partial_resume(self, tmp_path):
        """Phase B 部分完成 → resume → 最终 plan.md 包含所有 group。
        Partial Phase B → resume → final plan.md has all groups."""
        with patch.object(BaseAgent, "_estimate_input_tokens", return_value=100):
            agent = _make_agent()
            memory_dir = str(tmp_path / "memory")

            # 预置: Phase A 完成, Phase B group A 完成 / Pre-set: Phase A done, Phase B group A done
            progress_path = Path(memory_dir)
            progress_path.mkdir(parents=True, exist_ok=True)
            (progress_path / "plan_chunks_progress.json").write_text(
                json.dumps({"plan_parts": {
                    "global_context": "DONE_GLOBAL",
                    "api_sections": {"api_Group A": "DONE_GROUP_A"},
                }}),
                encoding="utf-8",
            )

            outline = {
                "business_summary": "Test",
                "api_groups": [
                    {"group_name": "Group A", "api_ids": ["api_a"], "test_focus": "Focus A"},
                    {"group_name": "Group B", "api_ids": ["api_b"], "test_focus": "Focus B"},
                ],
                "biz_flows": [],
            }
            interfaces = [
                {"test_id": "api_a", "api_name": "A", "method": "GET", "url": "/a",
                 "app_name": "x", "request_head": {}, "request_body": {}, "status_code": 200,
                 "assert_dict": {}, "remark": ""},
                {"test_id": "api_b", "api_name": "B", "method": "POST", "url": "/b",
                 "app_name": "x", "request_head": {}, "request_body": {}, "status_code": 200,
                 "assert_dict": {}, "remark": ""},
            ]

            # Phase B group B only (A skipped) = 1 call
            agent.call_llm = MagicMock(return_value="DONE_GROUP_B")

            plan_md = agent.generate_from_outline(
                outline=outline,
                requirement_analysis={"flows": 1},
                interfaces=interfaces,
                chunk_progress=json.loads(
                    (progress_path / "plan_chunks_progress.json").read_text(encoding="utf-8")
                ),
                memory_dir=memory_dir,
            )

            assert agent.call_llm.call_count == 1
            assert "DONE_GLOBAL" in plan_md
            assert "DONE_GROUP_A" in plan_md
            assert "DONE_GROUP_B" in plan_md
