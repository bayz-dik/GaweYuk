from datetime import datetime, timezone

import pytest

from onejob.ingestion.consensus import resolve_field_consensus
from onejob.job_verification.corroboration import (
    CorroborationSummary,
    EvidenceAuthority,
    summarize_corroboration,
)


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


def _evidence(evidence_id, family, source, authoritative=False):
    return EvidenceAuthority(
        evidence_id=evidence_id,
        evidence_family_id=family,
        source_id=source,
        authoritative=authoritative,
        conflicting=False,
    )


def _row(source, value, family, confidence):
    return {
        "evidence_id": f"e-{source}",
        "value": value,
        "evidence_family_id": family,
        "confidence": confidence,
    }


def test_three_mirrors_from_one_family_count_as_one_independent_source():
    summary = summarize_corroboration(
        (
            _evidence("e1", family="family-ats", source="src-ats"),
            _evidence("e2", family="family-ats", source="src-board-a"),
            _evidence("e3", family="family-ats", source="src-board-b"),
        )
    )
    assert summary.appearance_count == 3
    assert summary.independent_family_count == 1


def test_distinct_families_increase_independent_count():
    summary = summarize_corroboration(
        (
            _evidence("e1", family="family-a", source="src-a"),
            _evidence("e2", family="family-b", source="src-b"),
        )
    )
    assert summary.appearance_count == 2
    assert summary.independent_family_count == 2


def test_authoritative_family_count_tracked():
    summary = summarize_corroboration(
        (
            _evidence("e1", family="family-a", source="src-a", authoritative=True),
            _evidence("e2", family="family-b", source="src-b"),
        )
    )
    assert summary.authoritative_family_count == 1


def test_one_authoritative_family_can_outrank_many_low_authority_mirrors():
    consensus = resolve_field_consensus(
        "location_text",
        [
            _row("official", "Bekasi", "official-family", 0.98),
            _row("mirror-1", "Jakarta", "mirror-family", 0.55),
            _row("mirror-2", "Jakarta", "mirror-family", 0.55),
        ],
    )
    assert consensus.selected_value == "Bekasi"


def test_empty_evidence_summary_is_zero():
    summary = summarize_corroboration(())
    assert summary.appearance_count == 0
    assert summary.independent_family_count == 0
    assert isinstance(summary, CorroborationSummary)
