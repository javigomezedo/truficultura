"""Privacy helpers for the onboarding agent.

Sample rows are sent to a third-party LLM to help with entity detection and
column mapping. We never need the actual *values* — only the column structure
and the *kind* of data each cell holds. This module produces an anonymised
sample where literal strings/numbers are replaced by deterministic placeholders
that preserve type and approximate length.

The original (non-anonymised) sample stays in the local DB and is shown to the
user in the UI.
"""

from __future__ import annotations

import re
from typing import Any

_DATE_RE = re.compile(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}")
_NUMBER_RE = re.compile(r"^-?\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d+)?$|^-?\d+(?:[.,]\d+)?$")


def _classify(value: Any) -> str:
    """Return a short placeholder describing the kind of value."""
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "<bool>"
    if isinstance(value, (int, float)):
        return "<number>"
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        if _DATE_RE.match(stripped):
            return "<date>"
        if _NUMBER_RE.match(stripped.replace(" ", "")):
            return "<number>"
        # Short text → keep length hint
        length = len(stripped)
        if length <= 10:
            return "<text:short>"
        if length <= 40:
            return "<text:medium>"
        return "<text:long>"
    return "<unknown>"


def anonymize_sample(rows: list[list[Any]]) -> list[list[str]]:
    """Return a structurally identical sample where every cell is a placeholder.

    The shape is preserved (same number of rows and columns); only the literal
    contents are scrubbed. Headers should NOT be passed through this helper —
    column names are needed verbatim for the LLM to do its job.
    """
    return [[_classify(cell) for cell in row] for row in rows]
