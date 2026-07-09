"""Tests for plugins.skill_loader — load_skill_extensions()."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from plugins.skill_loader import load_skill_extensions


class TestLoadSkillExtensions:
    """Tests for load_skill_extensions()."""

    def should_return_empty_when_skills_disabled(self):
        settings = MagicMock()
        settings.enable_skills = False
        result = load_skill_extensions("test_agent", settings, "/fake/dir")
        assert result == []

    def should_return_empty_when_agent_not_in_config(self):
        settings = MagicMock()
        settings.enable_skills = True
        settings.skill_agents = {}
        result = load_skill_extensions("unknown_agent", settings, "/fake/dir")
        assert result == []

    def should_return_empty_when_agent_has_empty_skill_list(self):
        settings = MagicMock()
        settings.enable_skills = True
        settings.skill_agents = {"test_agent": []}
        result = load_skill_extensions("test_agent", settings, "/fake/dir")
        assert result == []

    def should_load_valid_skill_with_prompt_extension(self):
        settings = MagicMock()
        settings.enable_skills = True
        settings.skill_agents = {"test_agent": ["my_skill"]}

        mock_skill = MagicMock()
        mock_skill.prompt_extension = "Do boundary testing for all cases."

        with patch("plugins.skill_loader.SkillRegistry") as MockRegistry:
            mock_registry = MagicMock()
            mock_registry._skills = {"my_skill": mock_skill}
            MockRegistry.return_value = mock_registry

            result = load_skill_extensions("test_agent", settings, "/fake/dir")

        assert result == ["Do boundary testing for all cases."]

    def should_load_multiple_skills(self):
        settings = MagicMock()
        settings.enable_skills = True
        settings.skill_agents = {"test_agent": ["skill_a", "skill_b"]}

        mock_a = MagicMock()
        mock_a.prompt_extension = "Extension A."
        mock_b = MagicMock()
        mock_b.prompt_extension = "Extension B."

        with patch("plugins.skill_loader.SkillRegistry") as MockRegistry:
            mock_registry = MagicMock()
            mock_registry._skills = {"skill_a": mock_a, "skill_b": mock_b}
            MockRegistry.return_value = mock_registry

            result = load_skill_extensions("test_agent", settings, "/fake/dir")

        assert result == ["Extension A.", "Extension B."]

    def should_skip_skill_not_in_registry(self):
        settings = MagicMock()
        settings.enable_skills = True
        settings.skill_agents = {"test_agent": ["missing_skill"]}

        with patch("plugins.skill_loader.SkillRegistry") as MockRegistry:
            mock_registry = MagicMock()
            mock_registry._skills = {}
            MockRegistry.return_value = mock_registry

            result = load_skill_extensions("test_agent", settings, "/fake/dir")

        assert result == []

    def should_skip_skill_without_prompt_extension(self):
        settings = MagicMock()
        settings.enable_skills = True
        settings.skill_agents = {"test_agent": ["empty_skill"]}

        mock_skill = MagicMock()
        mock_skill.prompt_extension = ""

        with patch("plugins.skill_loader.SkillRegistry") as MockRegistry:
            mock_registry = MagicMock()
            mock_registry._skills = {"empty_skill": mock_skill}
            MockRegistry.return_value = mock_registry

            result = load_skill_extensions("test_agent", settings, "/fake/dir")

        assert result == []

    def should_pass_skills_dir_to_registry(self):
        settings = MagicMock()
        settings.enable_skills = True
        settings.skill_agents = {"test_agent": ["skill1"]}

        mock_skill = MagicMock()
        mock_skill.prompt_extension = "ext"

        with patch("plugins.skill_loader.SkillRegistry") as MockRegistry:
            mock_registry = MagicMock()
            mock_registry._skills = {"skill1": mock_skill}
            MockRegistry.return_value = mock_registry

            load_skill_extensions("test_agent", settings, "/custom/dir")

            MockRegistry.assert_called_once_with("/custom/dir", flat=True)
