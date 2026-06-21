"""国际化支持。Internationalization support.

Usage:
    from i18n import _, get_lang, set_lang
    set_lang("zh_CN")  # or "en_US"
    print(_("report.environment"))
"""

from i18n.loader import _, get_lang, set_lang

__all__ = ["_", "get_lang", "set_lang"]
