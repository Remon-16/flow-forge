"""翻译加载器。Translation loader.

Language priority: AGENT_LANG env var > env.yml lang > default "zh_CN".
"""

import json
import os
from pathlib import Path
from typing import Any

_translations: dict[str, Any] = {}
_lang: str = "zh_CN"


def set_lang(lang: str) -> None:
    """设置当前语言并加载对应的翻译文件。

    Set the current language and load the corresponding translation file.
    """
    global _lang, _translations
    lang = lang.strip()
    if lang not in ("zh_CN", "en_US"):
        lang = "zh_CN"
    _lang = lang

    json_path = Path(__file__).resolve().parent / f"{lang}.json"
    try:
        _translations = json.loads(json_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        _translations = {}


def get_lang() -> str:
    """返回当前语言代码。Return the current language code."""
    return _lang


def _(key: str, **kwargs) -> str:
    """翻译指定的 key，支持 str.format(**kwargs) 变量填充。

    Translate the given key, with optional str.format(**kwargs) substitution.
    """
    text = _translations.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text


# Auto-initialize from environment variable on import
_env_lang = os.environ.get("AGENT_LANG", "").strip()
if _env_lang:
    set_lang(_env_lang)
