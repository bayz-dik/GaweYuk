from datetime import datetime, timezone

import pytest

from onejob.career_twin.candidates import (
    CandidateEntity,
    CandidateLifecycle,
)
from onejob.career_twin.conflicts import (
    ConflictSet,
    ConflictStatus,
)
from onejob.career_twin.ontology import (
    EntityType,
    ONTOLOGY_VERSION,
    Predicate,
    PrivacyClass,
)
from onejob.career_twin.resolution import (
    ConfidenceBand,
    EntityResolution,
)
from onejob.career_twin.suggestions import (
    AtomicSuggestion,
    BatchLifecycle,
    DecisionState,
    Disposition,
    SuggestionBatch,
)
from onejob.career_twin.suppression import (
    SuppressionRecord,
    SuppressionStrength,
)
from onejob.career_twin.models import (
    CareerEntity,
    CareerEvidence,
    EntityLifecycle,
)
from onejob.career_twin.repositories import (
    CandidateEntityRepository,
    CareerEntityRepository,
    CareerEvidenceRepository,
    CareerTwinRepository,
    ConflictSetRepository,
    EntityResolutionRepository,
    IdempotencyRepository,
    SuggestionBatchRepository,
    SuggestionRepository,
    SuppressionRepository,
)
from onejob.persistence.db import Database


NOW = datetime(2026, 8, 21, 3, 0, tzinfo=timezone.utc)


def make_db(tmp_path) -> Database:
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    twins = CareerTwinRepository()
    with db.transaction() as conn:
        twins.ensure_twin(conn, "twin-1", "user-1", ONTOLOGY_VERSION)
    return db


def seed_batch(db: Database) -> None:
    batches = SuggestionBatchRepository()
    with db.transaction() as conn:
        batches.insert(
            conn,
            SuggestionBatch(
                batch_id="batch-1",
                twin_id="twin-1",
                source_type="USER_INPUT",
                intake_version="intake-v1",
                evidence_family_id="fam-1",
                lifecycle=BatchLifecycle.OPEN,
                created_at=NOW,
            ),
        )


# ---------------------------------------------------------------------------
# SuggestionBatch
# ---------------------------------------------------------------------------


def test_batch_roundtrip(tmp_path):
    db = make_db(tmp_path)
    repo = SuggestionBatchRepository()

    with db.transaction() as conn:
        repo.insert(
            conn,
            SuggestionBatch(
                batch_id="batch-1",
                twin_id="twin-1",
                source_type="LEGACY_PROFILE",
                source_reference="ref-1",
                intake_version="intake-v1",
                evidence_family_id="fam-1",
                lifecycle=BatchLifecycle.OPEN,
                created_at=NOW,
            ),
        )

    with db.connection() as conn:
        loaded = repo.get(conn, "batch-1")

    assert loaded is not None
    assert loaded.source_type == "LEGACY_PROFILE"
    assert loaded.lifecycle is BatchLifecycle.OPEN


def test_batch_mark_processed(tmp_path):
    db = make_db(tmp_path)
    repo = SuggestionBatchRepository()
    seed_batch(db)

    with db.transaction() as conn:
        repo.mark_lifecycle(
            conn, "batch-1", BatchLifecycle.PROCESSED, now=NOW
        )

    with db.connection() as conn:
        loaded = repo.get(conn, "batch-1")

    assert loaded.lifecycle is BatchLifecycle.PROCESSED
    assert loaded.completed_at == NOW


# ---------------------------------------------------------------------------
# CandidateEntity
# ---------------------------------------------------------------------------


def test_candidate_roundtrip_and_update(tmp_path):
    db = make_db(tmp_path)
    seed_batch(db)
    repo = CandidateEntityRepository()

    candidate = CandidateEntity(
        candidate_id="candidate-1",
        batch_id="batch-1",
        twin_id="twin-1",
        proposed_entity_type=EntityType.EXPERIENCE,
        fingerprint="fp-1",
        display_hint="Operator @ PT Example",
        lifecycle_state=CandidateLifecycle.STAGED,
        created_at=NOW,
    )

    with db.transaction() as conn:
        repo.insert(conn, candidate)

    with db.connection() as conn:
        loaded = repo.get(conn, "candidate-1")
    assert loaded.lifecycle_state is CandidateLifecycle.STAGED
    assert loaded.promoted_entity_id is None

    with db.transaction() as conn:
        repo.update(conn, candidate.with_state("LINK"))

    with db.connection() as conn:
        loaded = repo.get(conn, "candidate-1")
    assert loaded.lifecycle_state is CandidateLifecycle.LINKED


def test_candidate_list_by_batch(tmp_path):
    db = make_db(tmp_path)
    seed_batch(db)
    repo = CandidateEntityRepository()

    with db.transaction() as conn:
        for i in range(2):
            repo.insert(
                conn,
                CandidateEntity(
                    candidate_id=f"candidate-{i}",
                    batch_id="batch-1",
                    twin_id="twin-1",
                    proposed_entity_type=EntityType.SKILL,
                    fingerprint=f"fp-{i}",
                    display_hint=f"skill-{i}",
                    lifecycle_state=CandidateLifecycle.STAGED,
                    created_at=NOW,
                ),
            )

    with db.connection() as conn:
        items = repo.list_for_batch(conn, "batch-1")
    assert len(items) == 2


# ---------------------------------------------------------------------------
# AtomicSuggestion (optimistic concurrency on version)
# ---------------------------------------------------------------------------


def seed_candidate(db: Database) -> None:
    repo = CandidateEntityRepository()
    with db.transaction() as conn:
        repo.insert(
            conn,
            CandidateEntity(
                candidate_id="candidate-1",
                batch_id="batch-1",
                twin_id="twin-1",
                proposed_entity_type=EntityType.EXPERIENCE,
                fingerprint="fp-1",
                display_hint="Operator",
                lifecycle_state=CandidateLifecycle.STAGED,
                created_at=NOW,
            ),
        )


def make_suggestion(**over) -> AtomicSuggestion:
    base = dict(
        suggestion_id="suggestion-1",
        batch_id="batch-1",
        twin_id="twin-1",
        candidate_id="candidate-1",
        predicate=Predicate.EXPERIENCE_ROLE,
        proposed_value="role-1",
        value_type="ROLE_REF",
        decision_state=DecisionState.PENDING,
        disposition=Disposition.READY,
        normalized_value_fingerprint="nfp-1",
        version=1,
        created_at=NOW,
    )
    base.update(over)
    return AtomicSuggestion(**base)


def test_suggestion_roundtrip(tmp_path):
    db = make_db(tmp_path)
    seed_batch(db)
    seed_candidate(db)
    repo = SuggestionRepository()

    with db.transaction() as conn:
        repo.insert(conn, make_suggestion())

    with db.connection() as conn:
        loaded = repo.get(conn, "suggestion-1")

    assert loaded.decision_state is DecisionState.PENDING
    assert loaded.disposition is Disposition.READY
    assert loaded.proposed_value == "role-1"
    assert loaded.version == 1


def test_suggestion_versioned_update_succeeds_when_version_matches(tmp_path):
    db = make_db(tmp_path)
    seed_batch(db)
    seed_candidate(db)
    repo = SuggestionRepository()

    with db.transaction() as conn:
        repo.insert(conn, make_suggestion())

    updated = make_suggestion(
        decision_state=DecisionState.APPROVED,
        version=2,
        decided_at=NOW,
        decision_actor_id="user-1",
    )

    with db.transaction() as conn:
        repo.update_versioned(conn, updated, expected_version=1)

    with db.connection() as conn:
        loaded = repo.get(conn, "suggestion-1")
    assert loaded.decision_state is DecisionState.APPROVED
    assert loaded.version == 2


def test_suggestion_versioned_update_fails_when_stale(tmp_path):
    db = make_db(tmp_path)
    seed_batch(db)
    seed_candidate(db)
    repo = SuggestionRepository()

    with db.transaction() as conn:
        repo.insert(conn, make_suggestion())

    with pytest.raises(LookupError):
        with db.transaction() as conn:
            repo.update_versioned(
                conn,
                make_suggestion(version=99),
                expected_version=42,
            )


def test_suggestion_link_evidence(tmp_path):
    db = make_db(tmp_path)
    seed_batch(db)
    seed_candidate(db)
    repo = SuggestionRepository()

    evidence = CareerEvidenceRepository()
    with db.transaction() as conn:
        for i in (1, 2):
            evidence.insert(
                conn,
                CareerEvidence(
                    evidence_id=f"evidence-{i}",
                    twin_id="twin-1",
                    source_type="USER_INPUT",
                    evidence_family_id="fam-1",
                    observed_at=NOW,
                    payload_fingerprint=f"pfp-{i}",
                    trust_tier="TIER_SELF",
                    independence_status="INDEPENDENT",
                    privacy_class=PrivacyClass.CAREER_PRIVATE,
                ),
            )

    with db.transaction() as conn:
        repo.insert(conn, make_suggestion())
        repo.link_evidence(conn, "suggestion-1", "evidence-1")
        repo.link_evidence(conn, "suggestion-1", "evidence-2")

    with db.connection() as conn:
        ev = repo.evidence_ids(conn, "suggestion-1")
    assert set(ev) == {"evidence-1", "evidence-2"}


def test_suggestion_find_by_fingerprint(tmp_path):
    db = make_db(tmp_path)
    seed_batch(db)
    seed_candidate(db)
    repo = SuggestionRepository()

    with db.transaction() as conn:
        repo.insert(conn, make_suggestion())

    with db.connection() as conn:
        found = repo.find_by_fingerprint(
            conn,
            twin_id="twin-1",
            predicate=Predicate.EXPERIENCE_ROLE,
            normalized_value_fingerprint="nfp-1",
        )
    assert len(found) == 1
    assert found[0].suggestion_id == "suggestion-1"


# ---------------------------------------------------------------------------
# EntityResolution
# ---------------------------------------------------------------------------


def test_resolution_append_and_latest(tmp_path):
    db = make_db(tmp_path)
    seed_batch(db)
    seed_candidate(db)
    repo = EntityResolutionRepository()

    with db.transaction() as conn:
        repo.append(
            conn,
            EntityResolution(
                resolution_id="res-1",
                candidate_id="candidate-1",
                proposed_entity_id=None,
                confidence=None,
                confidence_band=ConfidenceBand.UNKNOWN,
                method="experience-resolver",
                algorithm_version="career-resolver-v1",
                input_fingerprint="ifp-1",
                signals_json="{}",
                created_at=NOW,
            ),
        )
        repo.append(
            conn,
            EntityResolution(
                resolution_id="res-2",
                candidate_id="candidate-1",
                proposed_entity_id=None,
                confidence=0.8,
                confidence_band=ConfidenceBand.HIGH,
                method="experience-resolver",
                algorithm_version="career-resolver-v1",
                input_fingerprint="ifp-2",
                signals_json="{}",
                created_at=datetime(2026, 8, 21, 4, 0, tzinfo=timezone.utc),
                supersedes_resolution_id="res-1",
            ),
        )

    with db.connection() as conn:
        latest = repo.latest_for_candidate(conn, "candidate-1")
    assert latest.resolution_id == "res-2"
    assert latest.confidence_band is ConfidenceBand.HIGH


# ---------------------------------------------------------------------------
# ConflictSet
# ---------------------------------------------------------------------------


def make_entity(db: Database, entity_id: str) -> None:
    repo = CareerEntityRepository()
    with db.transaction() as conn:
        repo.insert(
            conn,
            CareerEntity(
                entity_id=entity_id,
                twin_id="twin-1",
                entity_type=EntityType.EXPERIENCE,
                lifecycle_state=EntityLifecycle.ACTIVE,
                created_at=NOW,
            ),
        )


def test_conflict_roundtrip_and_versioned_resolve(tmp_path):
    db = make_db(tmp_path)
    make_entity(db, "experience-1")
    repo = ConflictSetRepository()

    with db.transaction() as conn:
        repo.insert(
            conn,
            ConflictSet(
                conflict_id="conflict-1",
                twin_id="twin-1",
                entity_id="experience-1",
                predicate=Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
                active_claim_id=None,
                status=ConflictStatus.OPEN,
                version=1,
                created_at=NOW,
            ),
        )

    with db.connection() as conn:
        loaded = repo.get(conn, "conflict-1")
    assert loaded.status is ConflictStatus.OPEN

    resolved = loaded.model_copy(
        update={
            "status": ConflictStatus.RESOLVED,
            "version": 2,
            "resolved_at": NOW,
            "resolution_type": "ACCEPT_ALTERNATIVE",
        }
    )
    with db.transaction() as conn:
        repo.update_versioned(conn, resolved, expected_version=1)

    with db.connection() as conn:
        loaded = repo.get(conn, "conflict-1")
    assert loaded.status is ConflictStatus.RESOLVED

    with pytest.raises(LookupError):
        with db.transaction() as conn:
            repo.update_versioned(conn, resolved, expected_version=1)


def test_conflict_link_suggestions_with_cluster(tmp_path):
    db = make_db(tmp_path)
    make_entity(db, "experience-1")
    seed_batch(db)
    seed_candidate(db)
    conflicts = ConflictSetRepository()
    suggestions = SuggestionRepository()

    with db.transaction() as conn:
        suggestions.insert(conn, make_suggestion())
        conflicts.insert(
            conn,
            ConflictSet(
                conflict_id="conflict-1",
                twin_id="twin-1",
                entity_id="experience-1",
                predicate=Predicate.EXPERIENCE_ROLE,
                active_claim_id=None,
                status=ConflictStatus.OPEN,
                version=1,
                created_at=NOW,
            ),
        )
        conflicts.link_suggestion(
            conn, "conflict-1", "suggestion-1", cluster_key="cluster-a"
        )

    with db.connection() as conn:
        linked = conflicts.suggestion_ids(conn, "conflict-1")
    assert linked == ["suggestion-1"]


# ---------------------------------------------------------------------------
# SuppressionRecord
# ---------------------------------------------------------------------------


def test_suppression_insert_and_active_match(tmp_path):
    db = make_db(tmp_path)
    repo = SuppressionRepository()

    with db.transaction() as conn:
        repo.insert(
            conn,
            SuppressionRecord(
                suppression_id="supp-1",
                twin_id="twin-1",
                predicate=Predicate.EXPERIENCE_ROLE,
                normalized_value_fingerprint="nfp-1",
                strength=SuppressionStrength.STRONG,
                reason="user requested",
                created_at=NOW,
            ),
        )

    with db.connection() as conn:
        matches = repo.active_matches(
            conn,
            twin_id="twin-1",
            predicate=Predicate.EXPERIENCE_ROLE,
            normalized_value_fingerprint="nfp-1",
        )
    assert len(matches) == 1
    assert matches[0].strength is SuppressionStrength.STRONG


def test_suppression_lift_excludes_from_active(tmp_path):
    db = make_db(tmp_path)
    repo = SuppressionRepository()

    with db.transaction() as conn:
        repo.insert(
            conn,
            SuppressionRecord(
                suppression_id="supp-1",
                twin_id="twin-1",
                predicate=Predicate.EXPERIENCE_ROLE,
                normalized_value_fingerprint="nfp-1",
                strength=SuppressionStrength.SOFT,
                reason=None,
                created_at=NOW,
            ),
        )
        repo.lift(conn, "supp-1", now=NOW)

    with db.connection() as conn:
        matches = repo.active_matches(
            conn,
            twin_id="twin-1",
            predicate=Predicate.EXPERIENCE_ROLE,
            normalized_value_fingerprint="nfp-1",
        )
    assert matches == []


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_idempotency_store_and_lookup(tmp_path):
    db = make_db(tmp_path)
    repo = IdempotencyRepository()

    with db.transaction() as conn:
        repo.store(
            conn,
            idempotency_key="idem-1",
            request_fingerprint="req-1",
            result_reference="suggestion-1",
            now=NOW,
        )

    with db.connection() as conn:
        record = repo.get(conn, "idem-1")
    assert record is not None
    assert record.request_fingerprint == "req-1"
    assert record.result_reference == "suggestion-1"
