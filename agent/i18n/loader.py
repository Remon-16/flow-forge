"""i18n 加载器 — 根据语言环境加载翻译表。

i18n loader: loads translation table based on locale.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

_current_lang: str = ""
_translations: Dict[str, str] = {}
_fallback: Dict[str, str] = {}


def _load_translations(lang: str) -> Dict[str, str]:
    """加载指定语言的翻译表。Load translation table for given language."""
    path = Path(__file__).resolve().parent / f"{lang}.json"
    if not path.exists():
        logger.warning("Translation file not found: %s", path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load translations for %s: %s", lang, e)
        return {}


def set_lang(lang: str) -> None:
    """设置当前语言并加载翻译表。Set language and load translations."""
    global _current_lang, _translations, _fallback
    _current_lang = lang
    _translations = _load_translations(lang)
    if lang != "zh_CN":
        _fallback = _load_translations("zh_CN")
    else:
        _fallback = {}


def get_lang() -> str:
    """获取当前语言。Get current language."""
    return _current_lang


def _(key: str, **kwargs) -> str:
    """翻译键名对应的文本。

    Translate key to current language. Falls back to zh_CN, then key itself.
    Usage: _("pipeline.start") → "流水线启动" or "Pipeline started"
    """
    global _current_lang
    if not _current_lang:
        lang = os.getenv("AGENT_LANG", "zh_CN")
        set_lang(lang)

    text = _translations.get(key) or _fallback.get(key) or key
    if kwargs:
        text = text.format(**kwargs)
    return text


def get_language_name() -> str:
    """返回当前语言的人可读名称，用于注入提示词。

    Return a human-readable language name for prompt injection.
    Maps AGENT_LANG env var to a name the LLM understands.
    """
    lang = os.getenv("AGENT_LANG", "zh_CN")
    if lang == "zh_CN":
        return "简体中文 (Simplified Chinese)"
    elif lang == "en_US":
        return "English"
    else:
        return "简体中文 (Simplified Chinese)"


def _step(step_key: str, msg_key: str, **kwargs) -> str:
    """带步骤编号的翻译。Translate with step number prefix.

    Usage: _step("parse_docs", "pipeline.reading_docs")
    → "[1/9] 读取文档..."  or  "[1/9] Reading documents..."
    """
    from i18n.step_order import step_msg

    return step_msg(step_key, _(msg_key, **kwargs))
