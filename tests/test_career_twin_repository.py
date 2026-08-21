from datetime import datetime, timezone

import pytest

from onejob.career_twin.models import (
    ApprovalState,
    CareerClaim,
    CareerEntity,
    ClaimLifecycle,
    EntityLifecycle,
)
from onejob.career_twin.ontology import (
    EntityType,
    ONTOLOGY_VERSION,
    Predicate,
)
from onejob.career_twin.repositories import (
    ActiveClaimConflict,
    CareerClaimRepository,
    CareerEntityRepository,
    CareerTwinRepository,
)
from onejob.persistence.db import Database


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


def make_claim(
    *,
    claim_id: str,
    value: str,
    family_id: str = "family-role-1",
) -> CareerClaim:
    return CareerClaim(
        claim_id=claim_id,
        claim_family_id=family_id,
        twin_id="twin-1",
        subject_entity_id="experience-1",
        predicate=Predicate.EXPERIENCE_ROLE,
        object_kind="ENTITY_REF",
        value=value,
        value_type="ROLE_REF",
        approval_state=ApprovalState.APPROVED,
        lifecycle_state=ClaimLifecycle.ACTIVE,
        ontology_version=ONTOLOGY_VERSION,
        created_at=NOW,
        approved_at=NOW,
    )


def setup_subject(conn):
    twins = CareerTwinRepository()
    entities = CareerEntityRepository()

    twins.ensure_twin(
        conn,
        "twin-1",
        "user-1",
        ONTOLOGY_VERSION,
    )

    entities.insert(
        conn,
        CareerEntity(
            entity_id="experience-1",
            twin_id="twin-1",
            entity_type=EntityType.EXPERIENCE,
            lifecycle_state=EntityLifecycle.ACTIVE,
            created_at=NOW,
        ),
    )


def test_claim_repository_appends_and_reads_active_claim(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    claims = CareerClaimRepository()

    with db.transaction() as conn:
        setup_subject(conn)
        claims.append(
            conn,
            make_claim(
                claim_id="claim-1",
                value="role-stamping-operator",
            ),
        )

    with db.connection() as conn:
        current = claims.active_for_family(
            conn,
            "twin-1",
            "experience-1",
            Predicate.EXPERIENCE_ROLE,
        )
        history = claims.history_for_family(
            conn,
            "family-role-1",
        )

    assert current is not None
    assert current.claim_id == "claim-1"
    assert current.value == "role-stamping-operator"
    assert [item.claim_id for item in history] == ["claim-1"]


def test_singular_predicate_rejects_second_active_claim(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    claims = CareerClaimRepository()

    with db.transaction() as conn:
        setup_subject(conn)

        claims.append(
            conn,
            make_claim(
                claim_id="claim-1",
                value="role-stamping-operator",
            ),
        )

        with pytest.raises(ActiveClaimConflict):
            claims.append(
                conn,
                make_claim(
                    claim_id="claim-2",
                    value="role-production-operator",
                    family_id="family-role-2",
                ),
            )


def test_entity_repository_gets_and_lists_only_active_entities(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()

    twins = CareerTwinRepository()
    entities = CareerEntityRepository()

    active = CareerEntity(
        entity_id="experience-active",
        twin_id="twin-1",
        entity_type=EntityType.EXPERIENCE,
        lifecycle_state=EntityLifecycle.ACTIVE,
        created_at=NOW,
    )

    retired = CareerEntity(
        entity_id="experience-retired",
        twin_id="twin-1",
        entity_type=EntityType.EXPERIENCE,
        lifecycle_state=EntityLifecycle.RETIRED,
        created_at=NOW,
        retired_at=NOW,
    )

    with db.transaction() as conn:
        twins.ensure_twin(
            conn,
            "twin-1",
            "user-1",
            ONTOLOGY_VERSION,
        )
        entities.insert(conn, active)
        entities.insert(conn, retired)

    with db.connection() as conn:
        loaded = entities.get(
            conn,
            "experience-active",
        )
        listed = entities.list_active(
            conn,
            "twin-1",
        )

    assert loaded == active
    assert [item.entity_id for item in listed] == [
        "experience-active"
    ]


def test_evidence_repository_inserts_and_links_to_claim(tmp_path):
    from onejob.career_twin.models import CareerEvidence
    from onejob.career_twin.ontology import PrivacyClass
    from onejob.career_twin.repositories import (
        CareerEvidenceRepository,
    )

    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()

    claims = CareerClaimRepository()
    evidence_repo = CareerEvidenceRepository()

    evidence = CareerEvidence(
        evidence_id="evidence-1",
        twin_id="twin-1",
        source_type="USER_INPUT",
        source_reference="profile-form",
        evidence_family_id="family-evidence-1",
        observed_at=NOW,
        extractor_version=None,
        payload_reference=None,
        payload_fingerprint="payload-sha256-1",
        trust_tier="USER_ASSERTED",
        independence_status="INDEPENDENT",
        privacy_class=PrivacyClass.PUBLIC_SAFE,
    )

    with db.transaction() as conn:
        setup_subject(conn)

        claim = make_claim(
            claim_id="claim-1",
            value="role-stamping-operator",
        )
        claims.append(conn, claim)

        evidence_repo.insert(
            conn,
            evidence,
        )

        evidence_repo.link_to_claim(
            conn,
            claim_id="claim-1",
            evidence_id="evidence-1",
            support_type="SUPPORTS",
            confidence=0.90,
        )

    with db.connection() as conn:
        stored = conn.execute(
            """
            SELECT *
            FROM career_evidence
            WHERE evidence_id = ?
            """,
            ("evidence-1",),
        ).fetchone()

        link = conn.execute(
            """
            SELECT *
            FROM career_claim_evidence
            WHERE claim_id = ?
              AND evidence_id = ?
            """,
            (
                "claim-1",
                "evidence-1",
            ),
        ).fetchone()

    assert stored is not None
    assert stored["source_type"] == "USER_INPUT"
    assert stored["evidence_family_id"] == (
        "family-evidence-1"
    )
    assert stored["privacy_class"] == "PUBLIC_SAFE"

    assert link is not None
    assert link["support_type"] == "SUPPORTS"
    assert link["confidence"] == pytest.approx(0.90)


def test_claim_assessment_repository_is_append_only_and_returns_latest(tmp_path):
    from onejob.career_twin.models import ClaimAssessment
    from onejob.career_twin.repositories import (
        ClaimAssessmentRepository,
    )

    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()

    claims = CareerClaimRepository()
    assessments = ClaimAssessmentRepository()

    first = ClaimAssessment(
        assessment_id="assessment-1",
        claim_id="claim-1",
        provenance_trust_tier="USER_ASSERTED",
        claim_confidence=0.60,
        evidence_fingerprint="evidence-set-v1",
        assessed_at=datetime(
            2026,
            8,
            21,
            1,
            0,
            tzinfo=timezone.utc,
        ),
        algorithm_version="claim-assessment-v1",
    )

    second = ClaimAssessment(
        assessment_id="assessment-2",
        claim_id="claim-1",
        provenance_trust_tier="MULTI_SOURCE",
        claim_confidence=0.90,
        evidence_fingerprint="evidence-set-v2",
        assessed_at=datetime(
            2026,
            8,
            21,
            2,
            0,
            tzinfo=timezone.utc,
        ),
        algorithm_version="claim-assessment-v1",
    )

    with db.transaction() as conn:
        setup_subject(conn)

        claims.append(
            conn,
            make_claim(
                claim_id="claim-1",
                value="role-stamping-operator",
            ),
        )

        assessments.append(conn, first)
        assessments.append(conn, second)

    with db.connection() as conn:
        latest = assessments.latest_for_claim(
            conn,
            "claim-1",
        )

        rows = conn.execute(
            """
            SELECT assessment_id
            FROM career_claim_assessments
            WHERE claim_id = ?
            ORDER BY assessed_at, assessment_id
            """,
            ("claim-1",),
        ).fetchall()

    assert latest is not None
    assert latest.assessment_id == "assessment-2"
    assert latest.claim_confidence == pytest.approx(0.90)

    assert [
        row["assessment_id"]
        for row in rows
    ] == [
        "assessment-1",
        "assessment-2",
    ]


def test_claim_repository_lists_only_active_claims_for_twin(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    claims = CareerClaimRepository()

    with db.transaction() as conn:
        setup_subject(conn)

        claims.append(
            conn,
            make_claim(
                claim_id="claim-active",
                value="role-stamping-operator",
            ),
        )

    with db.connection() as conn:
        listed = claims.list_active_for_twin(
            conn,
            "twin-1",
        )

    assert [
        claim.claim_id
        for claim in listed
    ] == ["claim-active"]


def test_mark_superseded_removes_claim_from_active_projection(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    claims = CareerClaimRepository()

    with db.transaction() as conn:
        setup_subject(conn)

        claims.append(
            conn,
            make_claim(
                claim_id="claim-1",
                value="role-stamping-operator",
            ),
        )

        claims.mark_superseded(
            conn,
            "claim-1",
            now=NOW,
        )

    with db.connection() as conn:
        active = claims.active_for_family(
            conn,
            "twin-1",
            "experience-1",
            Predicate.EXPERIENCE_ROLE,
        )

        history = claims.history_for_family(
            conn,
            "family-role-1",
        )

    assert active is None

    assert history[0].lifecycle_state is (
        ClaimLifecycle.SUPERSEDED
    )

    assert history[0].retired_at == NOW
