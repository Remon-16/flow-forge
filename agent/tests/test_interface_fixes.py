"""多文档接口解析修复测试 — test_id 生成 & 文件碰撞处理。
Multi-doc interface parsing fix tests — test_id generation & file collision.

所有 LLM 调用 mock，无真实 API 调用 / All LLM calls mocked, no real API.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# 确保 agent/ 在 sys.path 中 / Ensure agent/ is on sys.path
_AGENT_DIR = Path(__file__).resolve().parent.parent
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))


# ============================================================================
# 共享辅助 / Shared helpers
# ============================================================================


def _make_mock_settings():
    """构造测试用 Settings 对象 / Build test Settings instance."""
    from config.settings import Settings
    return Settings(
        llm_api_key="test-key",
        llm_model="test-model",
        llm_base_url="http://localhost",
        llm_context_window=128000,
        llm_max_output_tokens=4096,
        llm_context_compression_threshold=0.75,
        max_retries=2,
        max_steps=1,
    )


# ============================================================================
# 修改 1 测试：DocParserAgent test_id 始终从 URL 生成
# Change 1 tests: DocParserAgent always derives test_id from URL
# ============================================================================


class TestDocParserTestId:
    """验证 _parse_response 忽略 LLM 提供的 test_id，始终从 URL 生成。
    Verify _parse_response ignores LLM-provided test_id, always derives from URL."""

    def test_test_id_from_url_simple_path(self):
        """简单路径 → api_{path}_{method} / Simple path → api_{path}_{method}."""
        from doc_parser.llm_parser import DocParserAgent
        settings = _make_mock_settings()
        agent = DocParserAgent(settings)

        result = agent._parse_response({
            "interfaces": [
                {
                    "test_id": "API_001",
                    "api_name": "User Login",
                    "method": "POST",
                    "url": "/api/auth/login",
                },
            ],
        })
        assert len(result) == 1
        assert result[0].test_id == "api_api_auth_login_post"

    def test_test_id_ignores_llm_provided_id(self):
        """LLM 提供的 test_id 被忽略 / LLM-provided test_id ignored."""
        from doc_parser.llm_parser import DocParserAgent
        settings = _make_mock_settings()
        agent = DocParserAgent(settings)

        result = agent._parse_response({
            "interfaces": [
                {
                    "test_id": "custom_custom_login_v1",
                    "api_name": "User Login",
                    "method": "POST",
                    "url": "/api/auth/login",
                },
            ],
        })
        # 应使用 URL-based ID，而非 LLM 提供的 custom_custom_login_v1
        # Should use URL-based ID, not LLM-provided custom_custom_login_v1
        assert result[0].test_id == "api_api_auth_login_post"

    def test_test_id_unique_across_different_urls(self):
        """不同 URL 生成不同 test_id / Different URLs → different test_ids."""
        from doc_parser.llm_parser import DocParserAgent
        settings = _make_mock_settings()
        agent = DocParserAgent(settings)

        result = agent._parse_response({
            "interfaces": [
                {"method": "GET", "url": "/api/products"},
                {"method": "POST", "url": "/api/products"},
                {"method": "GET", "url": "/api/cart"},
                {"method": "PUT", "url": "/api/orders/{id}/pay"},
                {"method": "DELETE", "url": "/api/cart/{id}"},
            ],
        })
        assert len(result) == 5
        test_ids = [iface.test_id for iface in result]
        # 所有 test_id 应唯一 / All test_ids should be unique
        assert len(test_ids) == len(set(test_ids)), f"Duplicate IDs: {test_ids}"
        # 验证具体格式 / Verify specific formats
        assert "api_api_products_get" in test_ids
        assert "api_api_products_post" in test_ids
        assert "api_api_cart_get" in test_ids
        assert "api_api_orders_id_pay_put" in test_ids
        assert "api_api_cart_id_delete" in test_ids

    def test_test_id_with_empty_url_fallback(self):
        """URL 为空时 fallback 到 api_extracted_{idx}_{method}。
        Empty URL → fallback to api_extracted_{idx}_{method}."""
        from doc_parser.llm_parser import DocParserAgent
        settings = _make_mock_settings()
        agent = DocParserAgent(settings)

        result = agent._parse_response({
            "interfaces": [
                {"method": "POST"},
            ],
        })
        assert len(result) == 1
        assert result[0].test_id == "api_extracted_0_post"

    def test_test_id_special_chars_sanitized(self):
        """URL 中特殊字符被正确 sanitize / Special chars in URL sanitized."""
        from doc_parser.llm_parser import DocParserAgent
        settings = _make_mock_settings()
        agent = DocParserAgent(settings)

        result = agent._parse_response({
            "interfaces": [
                {
                    "method": "GET",
                    "url": "/api/messages/conversation/{conversationId}",
                },
            ],
        })
        assert result[0].test_id == "api_api_messages_conversation_conversationid_get"


# ============================================================================
# 修改 2 测试：YamlWriter.write_interface() 碰撞处理
# Change 2 tests: YamlWriter.write_interface() collision handling
# ============================================================================


class TestWriteInterfaceCollision:
    """验证 write_interface() 文件碰撞时正确版本化。
    Verify write_interface() correctly versions on file collision."""

    def test_write_interface_without_collision(self):
        """无碰撞时正常写入 / Normal write without collision."""
        from writers.yaml_writer import YamlWriter
        with tempfile.TemporaryDirectory() as tmpdir:
            iface = {
                "test_id": "api_user_login_post",
                "api_name": "Login",
                "method": "POST",
                "url": "/api/user/login",
            }
            path = YamlWriter.write_interface(iface, tmpdir)
            expected = Path(tmpdir) / "interfaces" / "api_user_login_post.yaml"
            assert Path(path) == expected
            assert expected.exists()

    def test_write_interface_with_collision_versions(self):
        """碰撞时添加 _v2 后缀 / Append _v2 suffix on collision."""
        from writers.yaml_writer import YamlWriter
        with tempfile.TemporaryDirectory() as tmpdir:
            iface1 = {
                "test_id": "API_001",
                "api_name": "Register",
                "method": "POST",
                "url": "/api/auth/register",
            }
            iface2 = {
                "test_id": "API_001",
                "api_name": "Login",
                "method": "POST",
                "url": "/api/auth/login",
            }
            path1 = YamlWriter.write_interface(iface1, tmpdir)
            path2 = YamlWriter.write_interface(iface2, tmpdir)
            assert Path(path1).name == "API_001.yaml"
            assert Path(path2).name == "API_001_v2.yaml"
            assert Path(path1).exists()
            assert Path(path2).exists()
            # 验证文件内容不同 / Verify files have different content
            import yaml
            d1 = yaml.safe_load(Path(path1).read_text(encoding="utf-8"))
            d2 = yaml.safe_load(Path(path2).read_text(encoding="utf-8"))
            assert d1["api_name"] == "Register"
            assert d2["api_name"] == "Login"
            # _v2 的 test_id 也应更新 / _v2 test_id should be updated
            assert d2["test_id"] == "API_001_v2"

    def test_write_interface_multiple_collisions(self):
        """多次碰撞时依次递增版本号 / Sequential version increment."""
        from writers.yaml_writer import YamlWriter
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(4):
                iface = {
                    "test_id": "SAME_ID",
                    "api_name": f"Interface {i}",
                    "method": "GET",
                    "url": f"/api/endpoint_{i}",
                }
                YamlWriter.write_interface(iface, tmpdir)
            interfaces_dir = Path(tmpdir) / "interfaces"
            files = sorted(interfaces_dir.glob("*.yaml"))
            assert len(files) == 4
            names = [f.stem for f in files]
            assert names == ["SAME_ID", "SAME_ID_v2", "SAME_ID_v3", "SAME_ID_v4"]

    def test_write_interface_preserves_test_id_in_yaml(self):
        """碰撞版本化后 test_id 在 YAML 内容中更新。
        Versioned test_id is updated in YAML content."""
        from writers.yaml_writer import YamlWriter
        import yaml
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(2):
                iface = {
                    "test_id": "DUP_001",
                    "api_name": f"API {i}",
                    "method": "GET",
                    "url": f"/api/path_{i}",
                }
                YamlWriter.write_interface(iface, tmpdir)
            # 读取碰撞后的文件 / Read the versioned file
            v2_path = Path(tmpdir) / "interfaces" / "DUP_001_v2.yaml"
            data = yaml.safe_load(v2_path.read_text(encoding="utf-8"))
            assert data["test_id"] == "DUP_001_v2"
