from __future__ import annotations

from app.models.incident import (
    INCIDENT_CATEGORIES,
    INCIDENT_CATEGORY_LABELS,
    INCIDENT_SEVERITIES,
    INCIDENT_SEVERITY_LABELS,
    Incident,
)


# ---------------------------------------------------------------------------
# category_label property
# ---------------------------------------------------------------------------


def test_category_label_known_values() -> None:
    for cat, expected in INCIDENT_CATEGORY_LABELS.items():
        inc = Incident(title="T", description="D", category=cat, severity="media")
        assert inc.category_label == expected


def test_category_label_unknown_falls_back_to_raw() -> None:
    inc = Incident(title="T", description="D", category="categoria_rara", severity="media")
    assert inc.category_label == "categoria_rara"


# ---------------------------------------------------------------------------
# severity_label property
# ---------------------------------------------------------------------------


def test_severity_label_known_values() -> None:
    for sev, expected in INCIDENT_SEVERITY_LABELS.items():
        inc = Incident(title="T", description="D", category="otro", severity=sev)
        assert inc.severity_label == expected


def test_severity_label_unknown_falls_back_to_raw() -> None:
    inc = Incident(title="T", description="D", category="otro", severity="extrema")
    assert inc.severity_label == "extrema"


# ---------------------------------------------------------------------------
# Constants completeness
# ---------------------------------------------------------------------------


def test_all_categories_have_labels() -> None:
    for cat in INCIDENT_CATEGORIES:
        assert cat in INCIDENT_CATEGORY_LABELS, f"Falta label para categoría: {cat}"


def test_all_severities_have_labels() -> None:
    for sev in INCIDENT_SEVERITIES:
        assert sev in INCIDENT_SEVERITY_LABELS, f"Falta label para severidad: {sev}"


def test_incident_explicit_fields() -> None:
    """Fields set explicitly in the constructor are stored correctly."""
    inc = Incident(
        title="Test",
        description="Desc",
        category="otro",
        severity="media",
        resolved=False,
    )
    assert inc.resolved is False
    assert inc.category == "otro"
    assert inc.severity == "media"
    assert inc.attachment_data is None
    assert inc.admin_response is None
