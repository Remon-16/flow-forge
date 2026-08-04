"""国际化模块 — 加载 zh_CN / en_US 翻译表。

i18n module: loads zh_CN / en_US translation tables.
"""

from .loader import _, get_lang, set_lang  # noqa: F401

__all__ = ["_", "get_lang", "set_lang"]
