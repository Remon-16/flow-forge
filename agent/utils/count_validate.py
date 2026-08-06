"""公共工具 — LLM 调用 + 数量校验 / Shared utility — LLM call + count validation.

被骨架生成器和插件 agent 共用。
Shared by skeleton generators and plugin agents.
"""

import logging
from typing import Dict, List

from i18n import _

logger = logging.getLogger(__name__)


def count_validate(
    agent: "BaseAgent",
    prompt: str,
    system_msg: str,
    json_key: str,
    expected_count: int,
    label: str,
    strategy: str = "fail",
    max_retries: int = None,
) -> List[Dict]:
    """调用 LLM 并校验返回数量，按策略处理不匹配与异常。
    Call LLM, extract list from JSON, validate count with configurable strategy.

    调用方通过 get_strategy(self._case_gen_validation, "check_name") 传入 strategy，
    值来自 env.yaml validation 规则（"fail" / "warn" / "skip"）。
    Callers pass strategy via get_strategy(self._case_gen_validation, "check_name"),
    derived from env.yaml validation rules ("fail" / "warn" / "skip").

    Args:
        agent: BaseAgent 实例（用于 call_llm_json_object）/ BaseAgent instance.
        prompt: 用户 prompt / User prompt.
        system_msg: 系统 prompt / System prompt.
        json_key: 从结果 dict 中提取的 JSON key / JSON key to extract from result dict.
        expected_count: 预期数量 / Expected number of items.
        label: 日志标签 / Human-readable label for log messages.
        strategy: "fail"（抛异常）/ "warn"（警告继续）/ "skip"（跳过校验）。
        max_retries: 最大重试次数 / Max retries. None → 回退到 agent._max_retries.

    Returns:
        从 JSON 响应中提取的列表 / List of items from the JSON response.

    Raises:
        ValueError: 仅当 strategy 为 "fail" 且所有重试耗尽时。
    """
    items = []
    agent.reset_steps()  # 每批重置步数计数器 / Reset step counter per batch

    # 解析重试次数 / Resolve retry count
    if max_retries is None:
        max_retries = agent._max_retries

    # 跳过校验：调用一次直接返回，不重试 / Skip validation: one call, no retries
    if strategy == "skip":
        try:
            result = agent.call_llm_json_object(prompt, system_msg, json_key)
            items = result.get(json_key, [])
        except Exception as e:
            logger.warning(_("count_validate.llm_error", label=label, error=str(e)))
            return []
        logger.info(_("skel_gen.count_check_skipped", label=label, count=len(items)))
        return items

    for attempt in range(max_retries + 1):
        try:
            result = agent.call_llm_json_object(prompt, system_msg, json_key)
            items = result.get(json_key, [])
        except Exception as e:
            if attempt >= max_retries:
                if strategy == "fail":
                    raise  # 严格模式：向上抛 / Strict mode: propagate
                logger.warning(_("count_validate.llm_exhausted", label=label, error=str(e)))
                return []  # warn（兜底）：返回空 / warn fallback: return empty
            logger.warning(_("count_validate.llm_retry", label=label, attempt=attempt + 1, error=str(e)))
            continue

        if len(items) == expected_count:
            logger.info(_("skel_gen.batch_progress", count=len(items), label=label))
            return items
        logger.warning(
            _("skel_gen.count_mismatch", label=label,
              attempt=attempt + 1, total=max_retries + 1,
              expected=expected_count, actual=len(items)),
        )

    last_count = len(items)
    # 警告但继续 / Warn but continue
    if strategy == "warn":
        logger.warning(
            _("skel_gen.count_mismatch_final", label=label,
              retries=max_retries + 1, expected=expected_count, actual=last_count),
        )
        return items
    # 严格模式：抛异常 / Strict mode: raise error
    else:
        raise ValueError(
            f"{label} count validation failed after {agent._max_retries + 1} "
            f"attempts: expected {expected_count}, got {last_count}"
        )
