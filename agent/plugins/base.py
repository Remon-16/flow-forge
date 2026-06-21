"""自定义用例属性生成器插件的抽象基类。

Abstract base class for custom case-attribute generator plugins.

插件在断言生成之后、YAML/Excel 输出之前运行，可为用例添加任意属性
（最常见的如 ``preprocessors`` 和 ``postprocessors`` 列表）。
Plugins run after assertion generation and before final output,
adding arbitrary attributes to test cases.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class PluginDeclaration:
    """插件元数据 — 描述插件功能和适用范围。Metadata describing what a plugin does and where it applies."""

    plugin_name: str
    """Human-readable name for logging and debugging."""

    attributes: List[str] = field(default_factory=list)
    """Names of the top-level case fields this plugin adds or modifies,
    e.g. ``["preprocessors", "postprocessors"]``."""

    applies_to_single: bool = True
    """Whether this plugin should be run on single-API test cases."""

    applies_to_biz: bool = True
    """Whether this plugin should be run on business-flow test cases."""

    max_retries: int = 1
    """Maximum retries for a batch that fails during ``generate()``."""

    error_strategy: str = "skip"
    """What to do when all retries are exhausted:

    * ``"skip"`` — skip the batch and continue (default)
    * ``"warn"`` — log a warning and continue
    * ``"fail"`` — raise an exception and abort the pipeline
    """


class CaseAttributeGenerator(ABC):
    """用例属性生成器基类 — 为已生成的测试用例补充属性。

    Base class for plugins that enrich generated test cases.

    典型场景 / Typical use cases:
    - 单接口预处理器：分析 request_body/request_head，决定是否添加
      HMAC 签名、参数加密等，写入 preprocessors 字段。
    - 业务链路后处理器：分析流程执行链，决定是否添加 SQL 清理或
      Redis 刷新步骤，写入 postprocessors 字段。

    用户编写子类并通过 ``PLUGIN_MODULES`` 环境变量注册。
    """

    @property
    @abstractmethod
    def declaration(self) -> PluginDeclaration:
        """Return the plugin's metadata declaration."""
        ...

    @abstractmethod
    def generate(
        self,
        cases: List[Dict[str, Any]],
        interfaces: List[Dict[str, Any]],
        api_summary: List[Dict[str, Any]],
        api_doc_text: str,
    ) -> List[Dict[str, Any]]:
        """Generate/update attributes for a batch of test cases.

        Args:
            cases: A batch of completed test cases (single or biz-flow).
                   Each case already has all standard fields filled in
                   (test_id, method, url, request_head, request_body,
                   assert_dict, assert_rules, etc.).
            interfaces: All parsed interface definitions.
            api_summary: API analysis summaries from the analyze_api node.
            api_doc_text: Raw API documentation text.

        Returns:
            The same list of cases with additional attributes added.
            The returned list must have the same length as *cases*.
        """
        ...

    def validate(self, case: Dict[str, Any]) -> List[str]:
        """Optional post-generation validation for a single case.

        Returns a list of human-readable error messages (empty = valid).
        """
        return []
