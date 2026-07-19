"""多 API 文档解析测试 / Multi-API-doc parsing tests.

覆盖 / Covers:
  - parse_docs_node 构建 api_raw_text / parse_docs_node builds api_raw_text
  - analyze_api_node 统一路径（analyze）/ analyze_api_node unified path (analyze)
  - batch.py fallback 读取全部文件 / batch.py fallback reads all files

所有 LLM 调用均已 mock，不发生实际费用。
All LLM calls are mocked — no real API costs incurred.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 确保 agent/ 在 sys.path 中 / Ensure agent/ is on sys.path
_AGENT_DIR = Path(__file__).resolve().parent.parent
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))


# ============================================================================
# 辅助函数 / Helpers
# ============================================================================

def _make_mock_settings():
    """构造测试用 Settings 对象。

    使用真实 Settings 实例而非 MagicMock，以防 configure() 将 MagicMock
    属性写入 BaseAgent 类变量后污染后续测试。

    Use a real Settings instance instead of MagicMock so configure()
    writes proper values to BaseAgent class variables.
    """
    from config.settings import Settings
    return Settings(
        llm_api_key="test-key",
        llm_model="test-model",
        llm_base_url="http://localhost",
        llm_context_window=128000,
        llm_max_output_tokens=4096,
        llm_context_compression_threshold=0.75,
        max_retries=3,
        max_steps=50,
        url_doc_match_max_retries=3,
        url_doc_match_strategy="warn",
        url_doc_match_enabled=True,
        enable_plugins=False,
        plugin_batch_size=10,
        skeleton_batch_size=10,
        plan_single_batch_size=10,
        consecutive_batch_failure_limit=3,
        llm_rate_limit_delay=0.0,
        llm_max_concurrency=1,
        llm_retry_base_delay=2.0,
        llm_request_timeout=600.0,
    )


# ============================================================================
# parse_docs_node — api_raw_text 构建 / api_raw_text construction
# ============================================================================

class TestParseDocsLLMMode:
    """测试 parse_docs_node 在默认 llm 模式下的行为。"""

    @patch("graph.nodes.parse_docs.DocParserAgent")
    def should_merge_raw_texts_for_multiple_files(self, MockDocParser, tmp_path):
        """多个 API 文件时，api_raw_text 拼接所有文件的原文。
        With multiple API files, api_raw_text merges all files' raw text.
        """
        from graph.nodes.parse_docs import parse_docs_node
        from graph.nodes.helpers import configure

        # Mock DocParserAgent 避免实际 LLM 调用 / Mock to avoid real LLM calls
        mock_parser = MagicMock()
        mock_parser.parse.return_value = []
        MockDocParser.return_value = mock_parser

        file1 = tmp_path / "api_a.md"
        file1.write_text("# Auth API\nPOST /auth/login\nGET /auth/logout", encoding="utf-8")
        file2 = tmp_path / "api_b.md"
        file2.write_text("# Order API\nPOST /orders\nGET /orders/{id}", encoding="utf-8")

        mock_settings = _make_mock_settings()
        configure(mock_settings, None)

        state = {
            "requirement_paths": [],
            "api_paths": [str(file1), str(file2)],
            "parse_mode": "llm",
            "output_dir": str(tmp_path),
            "cases_dir": str(tmp_path),
            "memory_dir": str(tmp_path),
        }

        result = parse_docs_node(state)

        # 校验 api_raw_text 拼接 / Verify api_raw_text merge
        assert result["api_raw_text"] != ""
        assert "# Auth API" in result["api_raw_text"]
        assert "# Order API" in result["api_raw_text"]

        # 校验 interface_extraction_method / Verify interface_extraction_method
        assert result["interface_extraction_method"] == "llm"

    @patch("graph.nodes.parse_docs.DocParserAgent")
    def should_build_api_raw_text_for_single_file(self, MockDocParser, tmp_path):
        """单个 API 文件时，api_raw_text 包含该文件内容。
        With a single API file, api_raw_text contains that file's content.
        """
        from graph.nodes.parse_docs import parse_docs_node
        from graph.nodes.helpers import configure

        mock_parser = MagicMock()
        mock_parser.parse.return_value = []
        MockDocParser.return_value = mock_parser

        file1 = tmp_path / "api.md"
        file1.write_text("# Single API\nGET /users", encoding="utf-8")

        mock_settings = _make_mock_settings()
        configure(mock_settings, None)

        state = {
            "requirement_paths": [],
            "api_paths": [str(file1)],
            "parse_mode": "llm",
            "output_dir": str(tmp_path),
            "cases_dir": str(tmp_path),
            "memory_dir": str(tmp_path),
        }

        result = parse_docs_node(state)

        assert "# Single API" in result["api_raw_text"]
        assert result["interface_extraction_method"] == "llm"

    @patch("graph.nodes.parse_docs.DocParserAgent")
    def should_interfaces_be_empty_when_doc_parser_returns_nothing(self, MockDocParser, tmp_path):
        """DocParserAgent 无接口返回时，interfaces 为空。
        When DocParserAgent returns nothing, interfaces is empty.
        """
        from graph.nodes.parse_docs import parse_docs_node
        from graph.nodes.helpers import configure

        mock_parser = MagicMock()
        mock_parser.parse.return_value = []
        MockDocParser.return_value = mock_parser

        file1 = tmp_path / "api.md"
        file1.write_text("# No API here\nJust some text", encoding="utf-8")

        mock_settings = _make_mock_settings()
        configure(mock_settings, None)

        state = {
            "requirement_paths": [],
            "api_paths": [str(file1)],
            "parse_mode": "llm",
            "output_dir": str(tmp_path),
            "cases_dir": str(tmp_path),
            "memory_dir": str(tmp_path),
        }

        result = parse_docs_node(state)

        assert result["interfaces"] == []

    def should_have_empty_api_raw_text_when_no_api_files(self, tmp_path):
        """无 API 文件时，api_raw_text 为空字符串。
        With no API files, api_raw_text is empty.
        """
        from graph.nodes.parse_docs import parse_docs_node
        from graph.nodes.helpers import configure

        mock_settings = _make_mock_settings()
        configure(mock_settings, None)

        state = {
            "requirement_paths": [],
            "api_paths": [],
            "parse_mode": "llm",
            "output_dir": str(tmp_path),
            "cases_dir": str(tmp_path),
            "memory_dir": str(tmp_path),
        }

        result = parse_docs_node(state)

        assert result["api_raw_text"] == ""
        assert result["interfaces"] == []
        assert result["interface_extraction_method"] == "none"


# ============================================================================
# analyze_api_node — 统一路径 / unified path
# ============================================================================

class TestAnalyzeApiUnified:
    """测试 analyze_api_node 在去掉 raw 后的统一 analyze 路径。"""

    def should_call_analyze_not_analyze_raw_text(self):
        """正常路径应调用 agent.analyze(interfaces)，而非 analyze_raw_text。
        Normal path should call agent.analyve(interfaces), not analyze_raw_text.
        """
        from graph.nodes.analyze_api import analyze_api_node
        from graph.nodes.helpers import configure

        mock_settings = _make_mock_settings()
        configure(mock_settings, None)

        summary = [
            {"api_path": "/api/login", "method": "POST", "description": "Login",
             "auth_type": "none", "need_token": False, "request_summary": "",
             "response_summary": "", "notes": ""},
        ]

        with patch("agents.api_analyzer.ApiAnalyzer") as MockAnalyzer:
            mock_agent = MagicMock()
            mock_agent.analyze = MagicMock(return_value=summary)
            mock_agent.revise = MagicMock()
            MockAnalyzer.return_value = mock_agent

            state = {
                "errors": [],
                "interfaces": [{"test_id": "api_login", "method": "POST", "url": "/api/login"}],
                "api_raw_text": "/api/login",
                "api_summary": [],
                "api_summary_feedback": "",
                "api_summary_confirmed": False,
                "api_paths": ["/fake/api.md"],
                "auto_mode": True,
                "output_dir": "/tmp",
                "cases_dir": "/tmp/cases",
                "memory_dir": "",
            }

            result = analyze_api_node(state)

            # 应该调用 analyze 而非 analyze_raw_text / Should call analyze, not analyze_raw_text
            mock_agent.analyze.assert_called_once()
            assert len(result["api_summary"]) == 1

    def should_call_revise_when_feedback_present(self):
        """有反馈时应调用 agent.revise。
        Should call agent.revise when feedback is present.
        """
        from graph.nodes.analyze_api import analyze_api_node
        from graph.nodes.helpers import configure

        mock_settings = _make_mock_settings()
        configure(mock_settings, None)

        revised = [
            {"api_path": "/api/login", "method": "POST", "description": "Updated",
             "auth_type": "bearer", "need_token": True, "request_summary": "",
             "response_summary": "", "notes": ""},
        ]

        with patch("agents.api_analyzer.ApiAnalyzer") as MockAnalyzer:
            mock_agent = MagicMock()
            mock_agent.analyze = MagicMock()
            mock_agent.revise = MagicMock(return_value=revised)
            MockAnalyzer.return_value = mock_agent

            state = {
                "errors": [],
                "interfaces": [{"test_id": "api_login", "method": "POST", "url": "/api/login"}],
                "api_raw_text": "/api/login",
                "api_summary": [{"api_path": "/api/login", "method": "POST"}],
                "api_summary_feedback": "fix auth",
                "api_summary_confirmed": False,
                "api_paths": ["/fake/api.md"],
                "auto_mode": True,
                "output_dir": "/tmp",
                "cases_dir": "/tmp/cases",
                "memory_dir": "",
            }

            result = analyze_api_node(state)

            mock_agent.revise.assert_called_once()
            mock_agent.analyze.assert_not_called()
            assert result["api_summary"] == revised

    def should_skip_llm_on_resume_with_existing_summary(self):
        """resume 且有 api_summary 无 feedback 时跳过 LLM。
        On resume with existing api_summary and no feedback, skip LLM.
        """
        from graph.nodes.analyze_api import analyze_api_node
        from graph.nodes.helpers import configure

        mock_settings = _make_mock_settings()
        configure(mock_settings, None)

        existing = [{"api_path": "/api/login", "method": "POST"}]

        with patch("agents.api_analyzer.ApiAnalyzer") as MockAnalyzer:
            mock_agent = MagicMock()
            mock_agent.analyze = MagicMock()
            mock_agent.revise = MagicMock()
            MockAnalyzer.return_value = mock_agent

            state = {
                "errors": [],
                "interfaces": [],
                "api_raw_text": "",
                "api_summary": existing,
                "api_summary_feedback": "",
                "api_summary_confirmed": False,
                "auto_mode": True,
                "output_dir": "/tmp",
                "cases_dir": "/tmp/cases",
                "memory_dir": "",
            }

            result = analyze_api_node(state)

            # resume 场景：不调用 LLM / Resume scenario: no LLM call
            mock_agent.analyze.assert_not_called()
            mock_agent.revise.assert_not_called()
            assert result["api_summary"] == existing


# ============================================================================
# batch.py fallback — 读取全部文件 / reads all files
# ============================================================================

class TestBatchFallbackMultiFile:
    """测试 batch.py 的 api_doc_text fallback 逻辑。"""

    @patch("doc_parser.text_extractor.extract_text")
    @patch("graph.nodes.batch.BizSkeletonGenerator")
    @patch("graph.nodes.batch.SingleSkeletonGenerator")
    def should_read_all_files_when_api_raw_text_empty(self, mock_single_gen, mock_biz_gen, mock_extract):
        """api_raw_text 为空时，应提取全部文件的文本并合并。
        When api_raw_text is empty, should extract and merge text from all files.
        """
        from graph.nodes.batch import batch_controller_node
        from graph.nodes.helpers import configure
        from agents.batch_controller import BatchController

        mock_settings = _make_mock_settings()
        configure(mock_settings, None)

        mock_extract.side_effect = lambda p: {
            "file1": "# Doc 1\n/api/a\n/api/b",
            "file2": "# Doc 2\n/api/c\n/api/d",
        }.get(Path(p).name, "")

        mock_single_gen.return_value = MagicMock()
        mock_biz_gen.return_value = MagicMock()

        with patch.object(BatchController, "run", return_value={"single_cases": [], "biz_flows": [], "failures": []}):
            state = {
                "errors": [],
                "interfaces": [
                    {"test_id": "test1", "api_path": "/api/a", "method": "GET", "url": "/api/a"},
                    {"test_id": "test2", "api_path": "/api/c", "method": "POST", "url": "/api/c"},
                ],
                "api_paths": ["/fake/file1", "/fake/file2"],
                "api_raw_text": "",
                "requirement_texts": [],
                "plan_md": "",
                "plan_parsed": MagicMock(),
                "output_dir": "/tmp",
                "cases_dir": "/tmp/cases",
                "memory_dir": "",
                "output_format": "yaml",
                "batch_size": 10,
                "debug_snapshots": False,
                "user_guidance": "",
                "reference_dir": "",
                "auto_mode": True,
                "case_type": "both",
                "resume": False,
                "resume_overwrite": False,
            }

            batch_controller_node(state)

            assert mock_extract.call_count == 2

    @patch("doc_parser.text_extractor.extract_text")
    @patch("graph.nodes.batch.BizSkeletonGenerator")
    @patch("graph.nodes.batch.SingleSkeletonGenerator")
    def should_still_work_with_single_file_fallback(self, mock_single_gen, mock_biz_gen, mock_extract):
        """回退逻辑对单文件场景仍正常工作（无回归）。
        Fallback logic still works correctly for single file (no regression).
        """
        from graph.nodes.batch import batch_controller_node
        from graph.nodes.helpers import configure
        from agents.batch_controller import BatchController

        mock_settings = _make_mock_settings()
        configure(mock_settings, None)

        mock_extract.return_value = "# Single Doc\n/api/x"
        mock_single_gen.return_value = MagicMock()
        mock_biz_gen.return_value = MagicMock()

        with patch.object(BatchController, "run", return_value={"single_cases": [], "biz_flows": [], "failures": []}):
            state = {
                "errors": [],
                "interfaces": [
                    {"test_id": "test1", "api_path": "/api/x", "method": "GET", "url": "/api/x"},
                ],
                "api_paths": ["/fake/single_file"],
                "api_raw_text": "",
                "requirement_texts": [],
                "plan_md": "",
                "plan_parsed": MagicMock(),
                "output_dir": "/tmp",
                "cases_dir": "/tmp/cases",
                "memory_dir": "",
                "output_format": "yaml",
                "batch_size": 10,
                "debug_snapshots": False,
                "user_guidance": "",
                "reference_dir": "",
                "auto_mode": True,
                "case_type": "both",
                "resume": False,
                "resume_overwrite": False,
            }

            batch_controller_node(state)

            assert mock_extract.call_count == 1
