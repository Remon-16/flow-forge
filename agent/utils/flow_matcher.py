"""Mermaid-to-scenario association utility.
流程图与业务链路场景关联工具 / Mermaid diagram to biz_flow_scenario matcher.

从 skeleton_generator._make_partial_biz_plan 中提取名称匹配逻辑为公共函数。
Extracted from skeleton_generator._make_partial_biz_plan as a public utility.
"""

import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


def match_mermaids_to_scenarios(
    scenarios: List[dict],
    mermaid_flows: Dict[str, str],
) -> Tuple[List[dict], List[str]]:
    """按名称将 mermaid 流程图关联到 biz_flow_scenarios。
    Associate mermaid diagrams with biz_flow_scenarios by name matching.

    对每个 scenario，尝试在 mermaid_flows 中查找同名的流程图。
    匹配逻辑与 skeleton_generator._make_partial_biz_plan 完全一致。
    For each scenario, look up a matching mermaid diagram by name.
    Matching logic is identical to skeleton_generator._make_partial_biz_plan.

    Args:
        scenarios: biz_flow_scenarios 列表，每项含 "name" key。
                   List of biz_flow_scenarios, each with a "name" key.
        mermaid_flows: {flow_name: diagram_text} 字典。
                       Dict of {flow_name: diagram_text}.

    Returns:
        (matched_scenarios, orphaned_names):
        - matched_scenarios: 匹配成功的场景列表 / Successfully matched scenarios.
        - orphaned_names: 在 mermaid_flows 中无对应图的场景 name 列表。
          Scenario names without a matching mermaid diagram.
    """
    matched: List[dict] = []
    orphaned: List[str] = []

    for scenario in scenarios:
        name = scenario.get("name", "")
        if name and name in mermaid_flows:
            matched.append(scenario)
        else:
            orphaned.append(name)

    return matched, orphaned
