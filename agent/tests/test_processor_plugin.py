"""Tests for ProcessorPlugin — declaration, routing, skill integration."""

import os
import pytest

from plugins.base import CaseAttributeGenerator, PluginDeclaration


# ============================================================================
# TestProcessorPluginDeclaration — 插件声明
# ============================================================================

class TestProcessorPluginDeclaration:
    """验证 ProcessorPlugin 的 PluginDeclaration 元数据。"""

    def test_declaration_correct_name(self):
        """plugin_name 应为 processor_selection。"""
        from plugins.official.processor_plugin import ProcessorPlugin
        plugin = ProcessorPlugin.__new__(ProcessorPlugin)
        # 直接验证 declaration property 的类型
        # Verify declaration property type
        decl = ProcessorPlugin.declaration.fget(plugin)
        assert isinstance(decl, PluginDeclaration)
        assert decl.plugin_name == "processor_selection"

    def test_declaration_attributes(self):
        """attributes 应包含 preprocessors 和 postprocessors。"""
        from plugins.official.processor_plugin import ProcessorPlugin
        plugin = ProcessorPlugin.__new__(ProcessorPlugin)
        decl = ProcessorPlugin.declaration.fget(plugin)
        assert "preprocessors" in decl.attributes
        assert "postprocessors" in decl.attributes

    def test_declaration_applies_to_both_types(self):
        """应同时应用于单接口用例和业务链路用例。"""
        from plugins.official.processor_plugin import ProcessorPlugin
        plugin = ProcessorPlugin.__new__(ProcessorPlugin)
        decl = ProcessorPlugin.declaration.fget(plugin)
        assert decl.applies_to_single is True
        assert decl.applies_to_biz is True

    def test_declaration_error_strategy_is_warn(self):
        """错误策略应为 warn（处理器分配失败不终止流水线）。"""
        from plugins.official.processor_plugin import ProcessorPlugin
        plugin = ProcessorPlugin.__new__(ProcessorPlugin)
        decl = ProcessorPlugin.declaration.fget(plugin)
        assert decl.error_strategy == "warn"


# ============================================================================
# TestProcessorPluginType — 类型验证
# ============================================================================

class TestProcessorPluginType:
    """验证 ProcessorPlugin 是 CaseAttributeGenerator 的子类。"""

    def test_is_case_attribute_generator(self):
        """ProcessorPlugin 继承自 CaseAttributeGenerator。"""
        from plugins.official.processor_plugin import ProcessorPlugin
        assert issubclass(ProcessorPlugin, CaseAttributeGenerator)

    def test_implements_generate(self):
        """ProcessorPlugin 实现了 generate 方法。"""
        from plugins.official.processor_plugin import ProcessorPlugin
        assert hasattr(ProcessorPlugin, "generate")


# ============================================================================
# TestProcessorPluginRouting — 路由逻辑
# ============================================================================

class TestProcessorPluginRouting:
    """验证 generate() 根据用例类型正确路由到对应的 selector。"""

    def test_empty_cases_returns_empty(self):
        """空列表直接返回。"""
        from plugins.official.processor_plugin import ProcessorPlugin
        plugin = ProcessorPlugin.__new__(ProcessorPlugin)
        result = plugin.generate([], [], [], "")
        assert result == []

    def test_single_case_routes_to_single_selector(self):
        """单接口用例（无 sheet_name）路由到 SingleProcessorSelector。"""
        from plugins.official.processor_plugin import ProcessorPlugin
        plugin = ProcessorPlugin.__new__(ProcessorPlugin)

        # Mock the single selector
        mock_selector = _FakeSelector()
        plugin._single_selector = mock_selector
        plugin._user_guidance = ""

        cases = [{"test_id": "TC_001", "relevance_id": "api_1"}]
        plugin.generate(cases, [], [], "")

        assert mock_selector.called_with_cases == cases
        assert mock_selector.called is True

    def test_biz_flow_routes_to_biz_selector(self):
        """业务流用例（有 sheet_name）路由到 BizProcessorSelector。"""
        from plugins.official.processor_plugin import ProcessorPlugin
        plugin = ProcessorPlugin.__new__(ProcessorPlugin)

        mock_selector = _FakeSelector()
        plugin._biz_selector = mock_selector
        plugin._user_guidance = ""

        cases = [{"sheet_name": "Test Flow", "steps": []}]
        plugin.generate(cases, [], [], "")

        assert mock_selector.called_with_cases == cases
        assert mock_selector.called is True


class _FakeSelector:
    """用于路由测试的假 selector。Fake selector for routing tests."""

    def __init__(self):
        self.called = False
        self.called_with_cases = None

    def fill_batch(self, cases, interfaces, api_summary, user_guidance=""):
        self.called = True
        self.called_with_cases = cases
        return cases


# ============================================================================
# TestDbProcessorsSkill — Skill 文件验证
# ============================================================================

class TestDbProcessorsSkill:
    """验证 db_processors.yaml Skill 文件的格式和内容。"""

    @pytest.fixture
    def skill_data(self):
        import yaml
        skill_path = os.path.join(
            os.path.dirname(__file__),
            "..", "plugins", "official", "skills", "db_processors.yaml",
        )
        with open(skill_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_skill_has_required_fields(self, skill_data):
        """Skill 应包含 name, description, version, target_agents, prompt_extension。"""
        assert "name" in skill_data
        assert skill_data["name"] == "db_processors"
        assert "description" in skill_data
        assert "version" in skill_data
        assert "target_agents" in skill_data
        assert "prompt_extension" in skill_data

    def test_target_agent_is_processor_selector(self, skill_data):
        """target_agents 应包含 processor_selector。"""
        assert "processor_selector" in skill_data["target_agents"]

    def test_prompt_extension_not_empty(self, skill_data):
        """prompt_extension 不能为空。"""
        ext = skill_data["prompt_extension"]
        assert ext is not None
        assert len(ext.strip()) > 0

    def test_prompt_contains_return_order_db(self, skill_data):
        """prompt_extension 应包含 return-order-db 处理器描述。"""
        ext = skill_data["prompt_extension"]
        assert "return-order-db" in ext

    def test_prompt_contains_critical_rules(self, skill_data):
        """prompt_extension 应包含关键规则（禁止编造处理器名）。"""
        ext = skill_data["prompt_extension"]
        assert "NEVER invent" in ext

    def test_prompt_no_overwrite_notice(self, skill_data):
        """prompt_extension 不应包含 OVERWRITE 规则（已移至提示词外）。"""
        ext = skill_data["prompt_extension"]
        assert "OVERWRITE" not in ext
        assert "WINS" not in ext

    def test_prompt_contains_processor_template(self, skill_data):
        """prompt_extension 应包含模板标记（供用户复制扩展）。"""
        ext = skill_data["prompt_extension"]
        assert "COPY this block" in ext or "template" in ext.lower()


# ============================================================================
# TestPrompts — 提示词模板验证
# ============================================================================

class TestPrompts:
    """验证 processor_selection 提示词模板。"""

    def test_single_system_has_json_format_warning(self):
        """单接口系统提示词应包含 JSON 输出格式警告。"""
        from plugins.official.prompts.processor_selection import SINGLE_PROCESSOR_SYSTEM
        assert "json.loads" in SINGLE_PROCESSOR_SYSTEM.lower() or \
               "raw JSON" in SINGLE_PROCESSOR_SYSTEM or \
               "no markdown" in SINGLE_PROCESSOR_SYSTEM.lower()

    def test_single_system_has_no_invent_rule(self):
        """系统提示词应强调不编造处理器名。"""
        from plugins.official.prompts.processor_selection import SINGLE_PROCESSOR_SYSTEM
        assert "invent" in SINGLE_PROCESSOR_SYSTEM.lower()

    def test_single_user_has_cases_template(self):
        """用户提示词应包含 {{cases}} 模板变量。"""
        from plugins.official.prompts.processor_selection import SINGLE_PROCESSOR_USER
        assert "{{cases}}" in SINGLE_PROCESSOR_USER

    def test_biz_system_exists(self):
        """业务流系统提示词应可导入且非空。"""
        from plugins.official.prompts.processor_selection import BIZ_PROCESSOR_SYSTEM
        assert len(BIZ_PROCESSOR_SYSTEM) > 0

    def test_biz_user_has_cases_template(self):
        """业务流用户提示词应包含 {{cases}} 模板变量。"""
        from plugins.official.prompts.processor_selection import BIZ_PROCESSOR_USER
        assert "{{cases}}" in BIZ_PROCESSOR_USER

    def test_no_hardcoded_processor_names_in_single(self):
        """单接口系统提示词不应包含硬编码的处理器名称。"""
        from plugins.official.prompts.processor_selection import SINGLE_PROCESSOR_SYSTEM
        assert "return-order-db" not in SINGLE_PROCESSOR_SYSTEM
        assert "<processor-name>" in SINGLE_PROCESSOR_SYSTEM

    def test_no_hardcoded_processor_names_in_biz(self):
        """业务流系统提示词不应包含硬编码的处理器名称。"""
        from plugins.official.prompts.processor_selection import BIZ_PROCESSOR_SYSTEM
        assert "return-order-db" not in BIZ_PROCESSOR_SYSTEM
        assert "<processor-name>" in BIZ_PROCESSOR_SYSTEM

    def test_no_overwrite_rule_in_prompts(self):
        """提示词不应包含 OVERWRITE 规则。"""
        from plugins.official.prompts.processor_selection import (
            SINGLE_PROCESSOR_SYSTEM,
            BIZ_PROCESSOR_SYSTEM,
        )
        assert "OVERWRITE" not in SINGLE_PROCESSOR_SYSTEM
        assert "OVERWRITE" not in BIZ_PROCESSOR_SYSTEM

    def test_optional_rule_exists(self):
        """提示词应包含处理器是可选的说明。"""
        from plugins.official.prompts.processor_selection import (
            SINGLE_PROCESSOR_SYSTEM,
            BIZ_PROCESSOR_SYSTEM,
        )
        assert "OPTIONAL" in SINGLE_PROCESSOR_SYSTEM
        assert "OPTIONAL" in BIZ_PROCESSOR_SYSTEM

    def test_no_modify_other_fields_rule(self):
        """提示词应包含不得修改其他字段的约束。"""
        from plugins.official.prompts.processor_selection import (
            SINGLE_PROCESSOR_SYSTEM,
            BIZ_PROCESSOR_SYSTEM,
        )
        assert "Do NOT modify" in SINGLE_PROCESSOR_SYSTEM
        assert "Do NOT modify" in BIZ_PROCESSOR_SYSTEM


# ============================================================================
# TestRedisProcessorsSkill — Redis 处理器 skill 验证
# ============================================================================

class TestRedisProcessorsSkill:
    """验证 redis_processors.yaml skill 文件。"""

    @pytest.fixture
    def skill_data(self):
        import yaml
        skill_path = os.path.join(
            os.path.dirname(__file__),
            "..", "plugins", "official", "skills", "redis_processors.yaml",
        )
        with open(skill_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_skill_has_required_fields(self, skill_data):
        assert skill_data["name"] == "redis_processors"
        assert "description" in skill_data
        assert "prompt_extension" in skill_data

    def test_target_agent_is_processor_selector(self, skill_data):
        assert "processor_selector" in skill_data["target_agents"]

    def test_prompt_contains_cache_handler(self, skill_data):
        ext = skill_data["prompt_extension"]
        assert "cache-handler" in ext

    def test_no_output_format_section(self, skill_data):
        ext = skill_data["prompt_extension"]
        assert "How to output" not in ext


# ============================================================================
# TestMqProcessorsSkill — MQ 处理器 skill 验证
# ============================================================================

class TestMqProcessorsSkill:
    """验证 mq_processors.yaml skill 文件。"""

    @pytest.fixture
    def skill_data(self):
        import yaml
        skill_path = os.path.join(
            os.path.dirname(__file__),
            "..", "plugins", "official", "skills", "mq_processors.yaml",
        )
        with open(skill_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_skill_has_required_fields(self, skill_data):
        assert skill_data["name"] == "mq_processors"
        assert "description" in skill_data
        assert "prompt_extension" in skill_data

    def test_target_agent_is_processor_selector(self, skill_data):
        assert "processor_selector" in skill_data["target_agents"]

    def test_prompt_contains_order_publish(self, skill_data):
        ext = skill_data["prompt_extension"]
        assert "order-publish" in ext


# ============================================================================
# TestRocketmqProcessorsSkill — RocketMQ 处理器 skill 验证
# ============================================================================

class TestRocketmqProcessorsSkill:
    """验证 rocketmq_processors.yaml skill 文件。"""

    @pytest.fixture
    def skill_data(self):
        import yaml
        skill_path = os.path.join(
            os.path.dirname(__file__),
            "..", "plugins", "official", "skills", "rocketmq_processors.yaml",
        )
        with open(skill_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_skill_has_required_fields(self, skill_data):
        assert skill_data["name"] == "rocketmq_processors"
        assert "description" in skill_data
        assert "prompt_extension" in skill_data

    def test_prompt_contains_rocketmq_order(self, skill_data):
        ext = skill_data["prompt_extension"]
        assert "rocketmq-order" in ext


# ============================================================================
# TestKafkaProcessorsSkill — Kafka 处理器 skill 验证
# ============================================================================

class TestKafkaProcessorsSkill:
    """验证 kafka_processors.yaml skill 文件。"""

    @pytest.fixture
    def skill_data(self):
        import yaml
        skill_path = os.path.join(
            os.path.dirname(__file__),
            "..", "plugins", "official", "skills", "kafka_processors.yaml",
        )
        with open(skill_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_skill_has_required_fields(self, skill_data):
        """Skill 应包含 name, description, version, target_agents, prompt_extension。"""
        assert skill_data["name"] == "kafka_processors"
        assert "description" in skill_data
        assert "prompt_extension" in skill_data

    def test_target_agent_is_processor_selector(self, skill_data):
        """target_agents 应包含 processor_selector。"""
        assert "processor_selector" in skill_data["target_agents"]

    def test_prompt_contains_kafka_order_event(self, skill_data):
        """prompt_extension 应包含 kafka-order-event 处理器描述。"""
        ext = skill_data["prompt_extension"]
        assert "kafka-order-event" in ext


# ============================================================================
# TestPulsarProcessorsSkill — Pulsar 处理器 skill 验证
# ============================================================================

class TestPulsarProcessorsSkill:
    """验证 pulsar_processors.yaml skill 文件。"""

    @pytest.fixture
    def skill_data(self):
        import yaml
        skill_path = os.path.join(
            os.path.dirname(__file__),
            "..", "plugins", "official", "skills", "pulsar_processors.yaml",
        )
        with open(skill_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_skill_has_required_fields(self, skill_data):
        """Skill 应包含 name, description, version, target_agents, prompt_extension。"""
        assert skill_data["name"] == "pulsar_processors"
        assert "description" in skill_data
        assert "prompt_extension" in skill_data

    def test_prompt_contains_pulsar_order_event(self, skill_data):
        """prompt_extension 应包含 pulsar-order-event 处理器描述。"""
        ext = skill_data["prompt_extension"]
        assert "pulsar-order-event" in ext
