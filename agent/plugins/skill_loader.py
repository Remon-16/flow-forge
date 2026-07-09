"""Skill 加载辅助函数 — 从 Settings 读取 Skill 配置并加载扩展。

Skill loader: reads Skill config from Settings and loads prompt extensions.
"""

import logging
from typing import List

from skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


def load_skill_extensions(agent_name: str, settings, skills_dir: str) -> List[str]:
    """从 Settings 读取 Skill 配置，加载指定 Agent 的 Skill 扩展。

    加载链：settings.enable_skills → settings.skill_agents[agent_name] → YAML 文件
    返回 prompt_extension 字符串列表，可直接传入 BaseAgent(skill_extensions=...)

    Reads skill config from Settings, loads prompt extensions for the given agent.
    Chain: settings.enable_skills → settings.skill_agents[agent_name] → YAML files
    Returns prompt_extension strings for BaseAgent(skill_extensions=...)
    """
    if not settings.enable_skills:
        logger.info("Skills disabled (enable_skills=false)")
        return []

    agent_skills = settings.skill_agents.get(agent_name, [])
    if not agent_skills:
        return []

    registry = SkillRegistry(skills_dir, flat=True)
    extensions = []
    for skill_name in agent_skills:
        skill = registry._skills.get(skill_name)
        if skill and skill.prompt_extension:
            extensions.append(skill.prompt_extension)
            logger.info("Loaded skill '%s' for agent '%s'", skill_name, agent_name)
        else:
            logger.warning(
                "Skill '%s' not found or has no prompt_extension", skill_name
            )

    return extensions
