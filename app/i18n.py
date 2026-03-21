from __future__ import annotations

import gettext
from pathlib import Path

LOCALE_DIR = Path(__file__).parent.parent / "locales"
AVAILABLE_LOCALES = ["es"]
DEFAULT_LOCALE = "es"


def get_locale(accept_language: str | None) -> str:
    """Parse Accept-Language header and return best available locale."""
    if not accept_language:
        return DEFAULT_LOCALE
    for part in accept_language.split(","):
        lang = part.strip().split(";")[0].strip().lower()
        # Match full code (e.g. "es-ES") or just language (e.g. "es")
        lang_short = lang[:2]
        if lang_short in AVAILABLE_LOCALES:
            return lang_short
    return DEFAULT_LOCALE


def load_translations(locale: str) -> gettext.NullTranslations:
    """Load compiled .mo translations for the given locale, fall back gracefully."""
    try:
        return gettext.translation(
            "messages", localedir=str(LOCALE_DIR), languages=[locale]
        )
    except FileNotFoundError:
        return gettext.NullTranslations()
