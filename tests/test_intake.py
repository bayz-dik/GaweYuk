from datetime import datetime, timezone

from onejob.career_twin.intake import (
    CandidateProposal,
    IntakeService,
    IntakeRequest,
    ProposedFact,
    ProposedEvidence,
)
from onejob.career_twin.ontology import (
    EntityType,
    ONTOLOGY_VERSION,
    Predicate,
    PrivacyClass,
)
from onejob.career_twin.repositories import (
    CandidateEntityRepository,
    CareerClaimRepository,
    CareerTwinRepository,
    SuggestionBatchRepository,
    SuggestionRepository,
)
from onejob.career_twin.suggestions import (
    BatchLifecycle,
    DecisionState,
    Disposition,
)
from onejob.persistence.db import Database


NOW = datetime(2026, 8, 21, 3, 0, tzinfo=timezone.utc)


class SequentialIds:
    def __init__(self):
        self.counts = {}

    def __call__(self, kind: str) -> str:
        number = self.counts.get(kind, 0) + 1
        self.counts[kind] = number
        return f"{kind}-{number}"


def make_db(tmp_path) -> Database:
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    with db.transaction() as conn:
        CareerTwinRepository().ensure_twin(
            conn, "twin-1", "user-1", ONTOLOGY_VERSION
        )
    return db


def sample_request() -> IntakeRequest:
    return IntakeRequest(
        twin_id="twin-1",
        source_type="LEGACY_PROFILE",
        source_reference="legacy-import-1",
        intake_version="intake-v1",
        evidence_family_id="fam-1",
        proposals=[
            CandidateProposal(
                proposed_entity_type=EntityType.EXPERIENCE,
                display_hint="Operator Stamping @ PT Example",
                facts=[
                    ProposedFact(
                        predicate=Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
                        value="PERMANENT",
                        value_type="TEXT",
                    ),
                    ProposedFact(
                        predicate=Predicate.EXPERIENCE_LOCATION,
                        value="Cikarang",
                        value_type="TEXT",
                    ),
                ],
                evidence=[
                    ProposedEvidence(
                        source_type="LEGACY_PROFILE",
                        trust_tier="TIER_SELF",
                        independence_status="INDEPENDENT",
                        privacy_class=PrivacyClass.CAREER_PRIVATE,
                        payload_fingerprint="pfp-1",
                    )
                ],
            )
        ],
    )


def test_intake_creates_batch_candidate_and_suggestions(tmp_path):
    db = make_db(tmp_path)
    service = IntakeService(db, id_factory=SequentialIds())

    result = service.intake(sample_request(), now=NOW)

    assert result.batch_id
    assert len(result.candidate_ids) == 1
    assert len(result.suggestion_ids) == 2

    with db.connection() as conn:
        batch = SuggestionBatchRepository().get(conn, result.batch_id)
        candidates = CandidateEntityRepository().list_for_batch(
            conn, result.batch_id
        )
        suggestions = SuggestionRepository().list_for_twin(
            conn, "twin-1", batch_id=result.batch_id
        )

    assert batch.source_type == "LEGACY_PROFILE"
    assert batch.lifecycle is BatchLifecycle.OPEN
    assert len(candidates) == 1
    assert len(suggestions) == 2
    for s in suggestions:
        assert s.decision_state is DecisionState.PENDING
        assert s.disposition is Disposition.READY
        assert s.candidate_id == candidates[0].candidate_id


def test_intake_writes_no_canonical_truth(tmp_path):
    db = make_db(tmp_path)
    service = IntakeService(db, id_factory=SequentialIds())

    service.intake(sample_request(), now=NOW)

    with db.connection() as conn:
        claims = CareerClaimRepository().list_active_for_twin(conn, "twin-1")
        entity_count = conn.execute(
            "SELECT COUNT(*) AS n FROM career_entities WHERE twin_id = ?",
            ("twin-1",),
        ).fetchone()["n"]

    # No canonical claims and no canonical entities may be created by intake.
    assert claims == []
    assert entity_count == 0


def test_intake_registers_evidence_and_links_to_suggestions(tmp_path):
    db = make_db(tmp_path)
    service = IntakeService(db, id_factory=SequentialIds())

    result = service.intake(sample_request(), now=NOW)

    with db.connection() as conn:
        repo = SuggestionRepository()
        for suggestion_id in result.suggestion_ids:
            ev = repo.evidence_ids(conn, suggestion_id)
            assert len(ev) == 1

        evidence_rows = conn.execute(
            "SELECT * FROM career_evidence WHERE twin_id = ?",
            ("twin-1",),
        ).fetchall()

    assert len(evidence_rows) == 1
    assert evidence_rows[0]["source_type"] == "LEGACY_PROFILE"


def test_intake_deterministic_fingerprints(tmp_path):
    db = make_db(tmp_path)
    service = IntakeService(db, id_factory=SequentialIds())

    result = service.intake(sample_request(), now=NOW)

    with db.connection() as conn:
        suggestions = SuggestionRepository().list_for_twin(
            conn, "twin-1", batch_id=result.batch_id
        )
        by_predicate = {s.predicate: s for s in suggestions}

    from onejob.career_twin.resolution import normalized_value_fingerprint

    expected = normalized_value_fingerprint(
        Predicate.EXPERIENCE_LOCATION, "Cikarang"
    )
    assert (
        by_predicate[Predicate.EXPERIENCE_LOCATION].normalized_value_fingerprint
        == expected
    )


def test_intake_rejects_unauthorized_twin_mismatch(tmp_path):
    db = make_db(tmp_path)
    service = IntakeService(db, id_factory=SequentialIds())

    req = sample_request()
    # A batch-level evidence family + proposals but request twin does not exist.
    req = req.model_copy(update={"twin_id": "twin-unknown"})

    import pytest

    with pytest.raises(Exception):
        service.intake(req, now=NOW)


def test_intake_does_not_persist_raw_sensitive_payload(tmp_path):
    db = make_db(tmp_path)
    service = IntakeService(db, id_factory=SequentialIds())

    result = service.intake(sample_request(), now=NOW)

    with db.connection() as conn:
        # No suggestion table column should hold a raw payload body; only
        # fingerprints/normalized values are stored.
        cols = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(career_atomic_suggestions)"
            ).fetchall()
        }

    forbidden = {"raw_payload", "payload_json", "raw_evidence", "secret"}
    assert not (cols & forbidden)
