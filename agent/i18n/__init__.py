"""国际化支持 — 根据 AGENT_LANG 环境变量切换语言。

Internationalization: switch language based on AGENT_LANG env var.
默认中文 (zh_CN)，可通过 AGENT_LANG=en_US 切换为英文。
"""

from .loader import _, get_lang, set_lang

__all__ = ["_", "get_lang", "set_lang"]
