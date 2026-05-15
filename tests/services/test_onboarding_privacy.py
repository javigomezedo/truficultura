"""Tests for the onboarding privacy / anonymisation helpers."""

from __future__ import annotations

from app.services.onboarding.privacy import anonymize_sample


def test_anonymize_classifies_each_kind() -> None:
    rows = [
        ["2025-01-01", 21.5, "Pienso perros", None, ""],
        ["14/02/2025", "1.250,50", "x", True, "Una descripción algo más larga para forzar el bucket medio"],
    ]
    out = anonymize_sample(rows)
    assert len(out) == 2
    assert out[0] == ["<date>", "<number>", "<text:medium>", "", ""]
    assert out[1][0] == "<date>"
    assert out[1][1] == "<number>"
    assert out[1][2] == "<text:short>"
    assert out[1][3] == "<bool>"
    assert out[1][4] == "<text:long>"


def test_anonymize_preserves_shape() -> None:
    rows = [["a", 1], ["b", 2], ["c", 3]]
    out = anonymize_sample(rows)
    assert len(out) == 3
    for row in out:
        assert len(row) == 2
