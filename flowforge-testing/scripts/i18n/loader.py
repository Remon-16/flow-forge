"""i18n 加载器 — 根据语言环境加载翻译表。

i18n loader: loads translation tables based on the configured locale.
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_current_lang: str = ""
_translations: dict = {}
_fallback: dict = {}


def _load_translations(lang: str) -> dict:
    """加载指定语言的翻译表。Load translation table for the given locale."""
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
    """设置当前语言并加载翻译表。Set the language and load translations."""
    global _current_lang, _translations, _fallback
    _current_lang = lang
    _translations = _load_translations(lang)
    _fallback = _load_translations("zh_CN") if lang != "zh_CN" else {}


def get_lang() -> str:
    """获取当前语言。Get the current language."""
    return _current_lang


def _(msg_key: str, **kwargs) -> str:
    """翻译键名对应的文本，缺省回退到 zh_CN 再到键名本身。

    Translate a key to the current language, falling back to zh_CN and then
    the raw key. Usage: _("tool.execute_start") -> localized message.
    """
    if not _current_lang:
        set_lang(os.getenv("FF_LANG", "zh_CN"))
    text = _translations.get(msg_key) or _fallback.get(msg_key) or msg_key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text
