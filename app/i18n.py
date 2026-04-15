from __future__ import annotations

import contextvars
import gettext
from pathlib import Path

LOCALE_DIR = Path(__file__).parent.parent / "locales"
AVAILABLE_LOCALES = ["es", "en", "fr"]
DEFAULT_LOCALE = "es"

# Per-request locale stored in a ContextVar (works with asyncio)
_current_locale: contextvars.ContextVar[str] = contextvars.ContextVar(
    "_current_locale", default=DEFAULT_LOCALE
)

_translations_cache: dict[str, gettext.NullTranslations] = {}


def load_translations(locale: str) -> gettext.NullTranslations:
    """Load (and cache) compiled .mo translations for the given locale."""
    if locale not in _translations_cache:
        try:
            _translations_cache[locale] = gettext.translation(
                "messages", localedir=str(LOCALE_DIR), languages=[locale]
            )
        except FileNotFoundError:
            _translations_cache[locale] = gettext.NullTranslations()
    return _translations_cache[locale]


def set_locale(locale: str) -> None:
    """Set the locale for the current async task/request context."""
    _current_locale.set(locale if locale in AVAILABLE_LOCALES else DEFAULT_LOCALE)


def get_current_locale() -> str:
    """Return the active locale for the current request context."""
    return _current_locale.get()


def gettext_func(message: str) -> str:
    """gettext function that resolves locale per-request via ContextVar."""
    return load_translations(_current_locale.get()).gettext(message)


def ngettext_func(singular: str, plural: str, n: int) -> str:
    """ngettext function that resolves locale per-request via ContextVar."""
    return load_translations(_current_locale.get()).ngettext(singular, plural, n)


def _(message: str, **kwargs: object) -> str:
    """Translate a backend message in the current request context."""
    translated = gettext_func(message)
    return translated.format(**kwargs) if kwargs else translated


def get_locale_from_accept(accept_language: str | None) -> str:
    """Parse Accept-Language header and return best available locale."""
    if not accept_language:
        return DEFAULT_LOCALE
    for part in accept_language.split(","):
        lang = part.strip().split(";")[0].strip().lower()
        lang_short = lang[:2]
        if lang_short in AVAILABLE_LOCALES:
            return lang_short
    return DEFAULT_LOCALE
