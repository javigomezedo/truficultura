"""Infer plot name and campaign year from an Excel sheet name.

Many growers organise their workbooks with one sheet per (plot, campaign),
e.g. ``"Ingresos CERRELLAR 25-26"``. This module extracts the structured
information from those names so the onboarding flow can populate fixed
column values (e.g. ``bancal``) without asking the user one by one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Words frequently prefixed to a sheet name that don't belong to the plot.
_NOISE_TOKENS: frozenset[str] = frozenset(
    {
        "ingresos",
        "gastos",
        "ventas",
        "compras",
        "produccion",
        "producción",
        "trufa",
        "trufas",
        "campaña",
        "campana",
        "campaign",
        "datos",
        "hoja",
        "sheet",
        "resumen",
        "totales",
        "total",
    }
)

# Patterns recognising campaign suffixes: 25-26, 25/26, 2025-2026, 2025/26.
_CAMPAIGN_RE = re.compile(r"(?P<y1>20\d{2}|\d{2})\s*[-/]\s*(?P<y2>20\d{2}|\d{2})")


def _looks_like_year(token: str) -> bool:
    """True when the token is purely a 2- or 4-digit number (e.g. '25', '2025')."""
    return bool(re.fullmatch(r"20\d{2}|\d{2}", token))


@dataclass(frozen=True)
class SheetMetadata:
    """Structured info extracted from a sheet name."""

    sheet_name: str
    plot_name: str | None
    campaign_year_start: int | None  # e.g. 2025 for "25-26"

    @property
    def campaign_label(self) -> str | None:
        if self.campaign_year_start is None:
            return None
        end = (self.campaign_year_start + 1) % 100
        return f"{self.campaign_year_start}/{end:02d}"


def infer_sheet_metadata(sheet_name: str) -> SheetMetadata:
    """Best-effort extraction of plot + campaign from a sheet title."""
    text = (sheet_name or "").strip()
    campaign: int | None = None

    m = _CAMPAIGN_RE.search(text)
    if m:
        y1 = int(m.group("y1"))
        if y1 < 100:
            y1 += 2000
        campaign = y1
        text = (text[: m.start()] + " " + text[m.end() :]).strip()

    # Strip noise words (case-insensitive) leaving only what looks like a plot.
    tokens = [t for t in re.split(r"[\s_-]+", text) if t]
    plot_tokens = [
        t
        for t in tokens
        if t.lower() not in _NOISE_TOKENS and not _looks_like_year(t)
    ]
    plot_name: str | None = None
    if plot_tokens:
        joined = " ".join(plot_tokens).strip()
        # Title-case when input was ALL CAPS or all lowercase; preserve mixed case.
        if joined.isupper() or joined.islower():
            plot_name = joined.title()
        else:
            plot_name = joined

    return SheetMetadata(
        sheet_name=sheet_name,
        plot_name=plot_name,
        campaign_year_start=campaign,
    )
