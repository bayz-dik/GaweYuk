from datetime import datetime, timezone

from onejob.career_twin.ontology import Predicate
from onejob.career_twin.suppression import (
    SuppressionDecision,
    SuppressionRecord,
    SuppressionStrength,
    evaluate_suppression,
    suppression_fingerprint,
)


NOW = datetime(2026, 8, 21, 3, 0, tzinfo=timezone.utc)


def make_record(
    *,
    strength: SuppressionStrength,
    fingerprint: str = "nfp-1",
    evidence_family_scope: str | None = None,
) -> SuppressionRecord:
    return SuppressionRecord(
        suppression_id="supp-1",
        twin_id="twin-1",
        predicate=Predicate.EXPERIENCE_ROLE,
        normalized_value_fingerprint=fingerprint,
        evidence_family_scope=evidence_family_scope,
        strength=strength,
        reason=None,
        created_at=NOW,
    )


# ---------------------------------------------------------------------------
# Fingerprint determinism
# ---------------------------------------------------------------------------


def test_suppression_fingerprint_is_deterministic():
    a = suppression_fingerprint(
        twin_id="twin-1",
        predicate=Predicate.EXPERIENCE_ROLE,
        normalized_value_fingerprint="nfp-1",
    )
    b = suppression_fingerprint(
        twin_id="twin-1",
        predicate=Predicate.EXPERIENCE_ROLE,
        normalized_value_fingerprint="nfp-1",
    )
    assert a == b


def test_suppression_fingerprint_scopes_by_twin_and_predicate():
    a = suppression_fingerprint(
        twin_id="twin-1",
        predicate=Predicate.EXPERIENCE_ROLE,
        normalized_value_fingerprint="nfp-1",
    )
    b = suppression_fingerprint(
        twin_id="twin-2",
        predicate=Predicate.EXPERIENCE_ROLE,
        normalized_value_fingerprint="nfp-1",
    )
    assert a != b


# ---------------------------------------------------------------------------
# Suppression evaluation
# ---------------------------------------------------------------------------


def test_no_active_records_means_not_suppressed():
    decision = evaluate_suppression(
        active_records=[],
        incoming_evidence_family_id="fam-1",
        incoming_evidence_independent=True,
    )
    assert decision.suppressed is False


def test_strong_suppression_blocks_even_new_independent_evidence():
    decision = evaluate_suppression(
        active_records=[make_record(strength=SuppressionStrength.STRONG)],
        incoming_evidence_family_id="fam-new",
        incoming_evidence_independent=True,
    )
    assert decision.suppressed is True
    assert decision.strength is SuppressionStrength.STRONG


def test_soft_suppression_blocks_same_family_evidence():
    decision = evaluate_suppression(
        active_records=[
            make_record(
                strength=SuppressionStrength.SOFT,
                evidence_family_scope="fam-1",
            )
        ],
        incoming_evidence_family_id="fam-1",
        incoming_evidence_independent=False,
    )
    assert decision.suppressed is True
    assert decision.strength is SuppressionStrength.SOFT


def test_soft_suppression_reopens_on_new_independent_evidence():
    decision = evaluate_suppression(
        active_records=[
            make_record(
                strength=SuppressionStrength.SOFT,
                evidence_family_scope="fam-1",
            )
        ],
        incoming_evidence_family_id="fam-2",
        incoming_evidence_independent=True,
    )
    # New, independent evidence family -> SOFT suppression should NOT hide it.
    assert decision.suppressed is False
    assert decision.reopen is True


def test_soft_suppression_does_not_reopen_on_unknown_independence():
    # INDEPENDENCE_UNKNOWN must not count as independent support.
    decision = evaluate_suppression(
        active_records=[
            make_record(
                strength=SuppressionStrength.SOFT,
                evidence_family_scope="fam-1",
            )
        ],
        incoming_evidence_family_id="fam-2",
        incoming_evidence_independent=False,
    )
    assert decision.suppressed is True
    assert decision.reopen is False


def test_strong_outranks_soft_when_both_present():
    decision = evaluate_suppression(
        active_records=[
            make_record(strength=SuppressionStrength.SOFT),
            make_record(strength=SuppressionStrength.STRONG),
        ],
        incoming_evidence_family_id="fam-new",
        incoming_evidence_independent=True,
    )
    assert decision.suppressed is True
    assert decision.strength is SuppressionStrength.STRONG


def test_decision_is_dataclass_like_with_flags():
    decision = evaluate_suppression(
        active_records=[],
        incoming_evidence_family_id="fam-1",
        incoming_evidence_independent=True,
    )
    assert isinstance(decision, SuppressionDecision)
    assert decision.reopen is False
