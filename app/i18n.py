from __future__ import annotations

import contextvars
import gettext
from pathlib import Path

from babel.messages import pofile

LOCALE_DIR = Path(__file__).parent.parent / "locales"
AVAILABLE_LOCALES = ["es", "en", "fr"]
DEFAULT_LOCALE = "es"

# Per-request locale stored in a ContextVar (works with asyncio)
_current_locale: contextvars.ContextVar[str] = contextvars.ContextVar(
    "_current_locale", default=DEFAULT_LOCALE
)

_translations_cache: dict[str, gettext.NullTranslations] = {}


class POTranslations(gettext.NullTranslations):
    """Lightweight translations backed by parsed .po files."""

    def __init__(
        self,
        singular_messages: dict[str, str],
        plural_messages: dict[tuple[str, str], tuple[str, str]],
    ) -> None:
        super().__init__()
        self._singular_messages = singular_messages
        self._plural_messages = plural_messages

    def gettext(self, message: str) -> str:
        return self._singular_messages.get(message, message)

    def ngettext(self, singular: str, plural: str, n: int) -> str:
        forms = self._plural_messages.get((singular, plural))
        if forms:
            return forms[0] if n == 1 else forms[1]
        return singular if n == 1 else plural


def _load_po_translations(locale: str) -> gettext.NullTranslations:
    """Fallback to .po catalogs when compiled .mo files are unavailable."""
    po_path = LOCALE_DIR / locale / "LC_MESSAGES" / "messages.po"
    if not po_path.exists():
        return gettext.NullTranslations()

    with po_path.open("r", encoding="utf-8") as handle:
        catalog = pofile.read_po(handle, locale=locale)

    singular_messages: dict[str, str] = {}
    plural_messages: dict[tuple[str, str], tuple[str, str]] = {}

    for message in catalog:
        if not message.id or not message.string:
            continue

        if isinstance(message.id, tuple):
            singular_id, plural_id = message.id
            if isinstance(message.string, (list, tuple)):
                singular_str = str(message.string[0]) if len(message.string) > 0 else ""
                plural_str = str(message.string[1]) if len(message.string) > 1 else ""
            else:
                singular_str = str(message.string)
                plural_str = ""

            if singular_str or plural_str:
                plural_messages[(singular_id, plural_id)] = (
                    singular_str or singular_id,
                    plural_str or plural_id,
                )
            continue

        singular_messages[str(message.id)] = str(message.string)

    return POTranslations(singular_messages, plural_messages)


def load_translations(locale: str) -> gettext.NullTranslations:
    """Load translations for the locale, preferring .mo and falling back to .po."""
    if locale not in _translations_cache:
        try:
            _translations_cache[locale] = gettext.translation(
                "messages", localedir=str(LOCALE_DIR), languages=[locale]
            )
        except FileNotFoundError:
            _translations_cache[locale] = _load_po_translations(locale)
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
