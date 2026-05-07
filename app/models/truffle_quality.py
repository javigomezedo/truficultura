from __future__ import annotations

from enum import Enum


class TruffleQuality(str, Enum):
    """Closed list of commercial quality categories for black truffle (Tuber melanosporum).

    Ordered from highest to lowest market value.
    """

    EXTRA = "extra"
    PRIMERA = "primera"
    SEGUNDA = "segunda"
    BLANDA = "blanda"
    AGUSANADA = "agusanada"
