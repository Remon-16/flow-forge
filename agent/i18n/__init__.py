"""国际化支持 — 根据 AGENT_LANG 环境变量切换语言。

Internationalization: switch language based on AGENT_LANG env var.
默认中文 (zh_CN)，可通过 AGENT_LANG=en_US 切换为英文。
"""

from .loader import _, _step, get_lang, set_lang, get_language_name
from .step_order import step_label, STEP_ORDER

__all__ = ["_", "_step", "get_lang", "set_lang", "get_language_name", "step_label", "STEP_ORDER"]
