"""多 API 文档独立分析测试 / Multi-API-doc independent analysis tests.

覆盖 / Covers:
  - parse_docs_node 构建 api_raw_texts / parse_docs_node builds api_raw_texts
  - analyze_api_node 逐文件分析 / analyze_api_node per-file analysis
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
    属性写入 BaseAgent 类变量后污染后续测试（如 _default_max_concurrency）。

    Use a real Settings instance instead of MagicMock so configure()
    writes proper values (not MagicMock proxies) to BaseAgent class
    variables, avoiding test pollution across modules.
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


def _make_mock_analyze_raw_text(mock_results):
    """构造 mock analyze_raw_text，按顺序返回结果。

    Build a mock analyze_raw_text that returns results in order.
    使用 MagicMock(side_effect=...) 以支持 call_count 断言。
    """
    return MagicMock(side_effect=list(mock_results))


# ============================================================================
# parse_docs_node — api_raw_texts 构建 / api_raw_texts construction
# ============================================================================

class TestParseDocsApiRawTexts:
    """测试 parse_docs_node 构建 api_raw_texts 字段。"""

    def should_build_api_raw_texts_for_multiple_files(self, tmp_path):
        """多个 API 文件时，api_raw_texts 包含逐文件原文。
        With multiple API files, api_raw_texts includes per-file raw texts.
        """
        from graph.nodes.parse_docs import parse_docs_node
        from graph.nodes.helpers import configure

        # 创建多个临时 API 文档 / Create multiple temp API docs
        file1 = tmp_path / "api_a.md"
        file1.write_text("# Auth API\nPOST /auth/login\nGET /auth/logout", encoding="utf-8")
        file2 = tmp_path / "api_b.md"
        file2.write_text("# Order API\nPOST /orders\nGET /orders/{id}", encoding="utf-8")

        mock_settings = _make_mock_settings()
        configure(mock_settings, None)

        state = {
            "requirement_paths": [],
            "api_paths": [str(file1), str(file2)],
            "parse_mode": "raw",
            "output_dir": str(tmp_path),
            "cases_dir": str(tmp_path),
            "memory_dir": str(tmp_path),
        }

        result = parse_docs_node(state)

        # 校验 api_raw_texts / Verify api_raw_texts
        assert "api_raw_texts" in result
        assert len(result["api_raw_texts"]) == 2
        assert result["api_raw_texts"][0]["path"] == str(file1)
        assert result["api_raw_texts"][0]["text"] == "# Auth API\nPOST /auth/login\nGET /auth/logout"
        assert result["api_raw_texts"][1]["path"] == str(file2)
        assert result["api_raw_texts"][1]["text"] == "# Order API\nPOST /orders\nGET /orders/{id}"

        # 校验 api_raw_text（拼接文本仍保留） / Verify api_raw_text (merged text still present)
        assert "---" in result["api_raw_text"]
        assert "# Auth API" in result["api_raw_text"]
        assert "# Order API" in result["api_raw_text"]

    def should_build_api_raw_texts_for_single_file(self, tmp_path):
        """单个 API 文件时，api_raw_texts 包含一项。
        With a single API file, api_raw_texts has one entry.
        """
        from graph.nodes.parse_docs import parse_docs_node
        from graph.nodes.helpers import configure

        file1 = tmp_path / "api.md"
        file1.write_text("# Single API", encoding="utf-8")

        mock_settings = _make_mock_settings()
        configure(mock_settings, None)

        state = {
            "requirement_paths": [],
            "api_paths": [str(file1)],
            "parse_mode": "raw",
            "output_dir": str(tmp_path),
            "cases_dir": str(tmp_path),
            "memory_dir": str(tmp_path),
        }

        result = parse_docs_node(state)

        assert "api_raw_texts" in result
        assert len(result["api_raw_texts"]) == 1
        assert result["api_raw_texts"][0]["text"] == "# Single API"

    def should_have_empty_api_raw_texts_when_no_api_files(self, tmp_path):
        """无 API 文件时，api_raw_texts 为空列表。
        With no API files, api_raw_texts is an empty list.
        """
        from graph.nodes.parse_docs import parse_docs_node
        from graph.nodes.helpers import configure

        mock_settings = _make_mock_settings()
        configure(mock_settings, None)

        state = {
            "requirement_paths": [],
            "api_paths": [],
            "parse_mode": "raw",
            "output_dir": str(tmp_path),
            "cases_dir": str(tmp_path),
            "memory_dir": str(tmp_path),
        }

        result = parse_docs_node(state)

        assert "api_raw_texts" in result
        assert result["api_raw_texts"] == []


# ============================================================================
# analyze_api_node — 逐文件分析 / per-file analysis
# ============================================================================

class TestAnalyzeApiPerFile:
    """测试 analyze_api_node 在 raw 模式下的逐文件分析行为。"""

    def should_analyze_each_file_independently(self):
        """多文件时，每个文件独立调用 analyze_raw_text。
        With multiple files, each file gets its own analyze_raw_text call.
        """
        from graph.nodes.analyze_api import analyze_api_node
        from graph.nodes.helpers import configure

        mock_settings = _make_mock_settings()
        configure(mock_settings, None)

        file1_summary = [
            {"api_path": "/auth/login", "method": "POST", "description": "Login",
             "auth_type": "none", "need_token": False, "request_summary": "",
             "response_summary": "", "notes": ""},
        ]
        file2_summary = [
            {"api_path": "/orders", "method": "POST", "description": "Create order",
             "auth_type": "bearer", "need_token": True, "request_summary": "",
             "response_summary": "", "notes": ""},
        ]

        with patch("agents.api_analyzer.ApiAnalyzer") as MockAnalyzer:
            mock_agent = MagicMock()
            mock_agent.analyze_raw_text = _make_mock_analyze_raw_text([file1_summary, file2_summary])
            mock_agent._merge_raw_results = MagicMock(return_value=file1_summary + file2_summary)
            mock_agent.revise = MagicMock()
            MockAnalyzer.return_value = mock_agent

            state = {
                "errors": [],
                "interfaces": [],
                "api_raw_text": "/auth/login\n/orders",  # 保留用于其他逻辑 / kept for other logic
                "api_raw_texts": [
                    {"path": "/fake/api_a.md", "text": "file1 text"},
                    {"path": "/fake/api_b.md", "text": "file2 text"},
                ],
                "api_summary": [],
                "api_summary_feedback": "",
                "api_summary_confirmed": False,
                "api_paths": ["/fake/api_a.md", "/fake/api_b.md"],
                "auto_mode": True,
                "output_dir": "/tmp",
                "cases_dir": "/tmp/cases",
                "memory_dir": "",
            }

            result = analyze_api_node(state)

            # 验证调用次数 / Verify call count
            assert mock_agent.analyze_raw_text.call_count == 2

            # 验证每次调用的参数 / Verify each call's parameters
            calls = mock_agent.analyze_raw_text.call_args_list
            assert calls[0][0][0] == "file1 text"  # 第一个参数 raw_text
            assert calls[0][0][1] == "api_a.md"     # 第二个参数 file_name
            assert calls[1][0][0] == "file2 text"
            assert calls[1][0][1] == "api_b.md"

            # 验证合并 / Verify merge
            mock_agent._merge_raw_results.assert_called_once()
            assert len(result["api_summary"]) == 2

    def should_make_single_call_for_single_file(self):
        """单文件时，仍为 1 次 LLM 调用，不增加开销。
        Single file still gets 1 LLM call — no overhead added.
        """
        from graph.nodes.analyze_api import analyze_api_node
        from graph.nodes.helpers import configure

        mock_settings = _make_mock_settings()
        configure(mock_settings, None)

        single_summary = [
            {"api_path": "/api/test", "method": "GET", "description": "Test",
             "auth_type": "none", "need_token": False, "request_summary": "",
             "response_summary": "", "notes": ""},
        ]

        with patch("agents.api_analyzer.ApiAnalyzer") as MockAnalyzer:
            mock_agent = MagicMock()
            mock_agent.analyze_raw_text = _make_mock_analyze_raw_text([single_summary])
            mock_agent._merge_raw_results = MagicMock()
            mock_agent.revise = MagicMock()
            MockAnalyzer.return_value = mock_agent

            state = {
                "errors": [],
                "interfaces": [],
                "api_raw_text": "/api/test",
                "api_raw_texts": [
                    {"path": "/fake/api.md", "text": "single file text"},
                ],
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

            assert mock_agent.analyze_raw_text.call_count == 1
            mock_agent._merge_raw_results.assert_not_called()
            assert mock_agent.analyze_raw_text.call_args[0][0] == "single file text"
            assert mock_agent.analyze_raw_text.call_args[0][1] == "api.md"

    def should_fallback_to_merged_text_when_no_api_raw_texts(self):
        """无 api_raw_texts 时回退到合并文本（兼容旧数据）。
        Fallback to merged api_raw_text when api_raw_texts is missing (legacy compat).
        """
        from graph.nodes.analyze_api import analyze_api_node
        from graph.nodes.helpers import configure

        mock_settings = _make_mock_settings()
        configure(mock_settings, None)

        single_summary = [
            {"api_path": "/api/old", "method": "GET", "description": "Old",
             "auth_type": "none", "need_token": False, "request_summary": "",
             "response_summary": "", "notes": ""},
        ]

        with patch("agents.api_analyzer.ApiAnalyzer") as MockAnalyzer:
            mock_agent = MagicMock()
            mock_agent.analyze_raw_text = _make_mock_analyze_raw_text([single_summary])
            mock_agent._merge_raw_results = MagicMock()
            mock_agent.revise = MagicMock()
            MockAnalyzer.return_value = mock_agent

            state = {
                "errors": [],
                "interfaces": [],
                "api_raw_text": "/api/old",
                "api_raw_texts": [],  # 缺失 / missing
                "api_summary": [],
                "api_summary_feedback": "",
                "api_summary_confirmed": False,
                "api_paths": ["/fake/old_api.md"],
                "auto_mode": True,
                "output_dir": "/tmp",
                "cases_dir": "/tmp/cases",
                "memory_dir": "",
            }

            result = analyze_api_node(state)

            assert mock_agent.analyze_raw_text.call_count == 1
            # 回退到拼接文本 + 第一个文件名 / Fallback to merged text + first filename
            assert mock_agent.analyze_raw_text.call_args[0][0] == "/api/old"
            assert mock_agent.analyze_raw_text.call_args[0][1] == "old_api.md"


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

        # Mock 骨架生成器和 BatchController 避免实际 LLM 调用
        # Mock skeleton generators and BatchController to avoid real LLM calls
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
                "api_raw_text": "",  # 空：触发 fallback / empty: trigger fallback
                "api_raw_texts": [],
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

            # 调用不会因 actual BatchController 逻辑而失败 / Call won't fail on real BatchController logic
            batch_controller_node(state)

            # 验证 extract_text 被调用了两次 / Verify extract_text was called twice
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
                "api_raw_texts": [],
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
