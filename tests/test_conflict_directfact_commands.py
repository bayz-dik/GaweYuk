from datetime import datetime, timezone

import pytest

from onejob.career_twin.commands import (
    ApproveSuggestionCommand,
    LiftSuppressionCommand,
    ResolveConflictCommand,
    SubmitDirectFactCommand,
    SuggestionCommandService,
)
from onejob.career_twin.conflicts import ConflictSet, ConflictStatus
from onejob.career_twin.errors import (
    AuthorizationDenied,
    InvalidConflictResolution,
    StaleClaimState,
    StaleConflictState,
)
from onejob.career_twin.intake import (
    CandidateProposal,
    IntakeRequest,
    IntakeService,
    ProposedEvidence,
    ProposedFact,
)
from onejob.career_twin.models import CareerEntity, EntityLifecycle
from onejob.career_twin.ontology import (
    EntityType,
    ONTOLOGY_VERSION,
    Predicate,
    PrivacyClass,
)
from onejob.career_twin.repositories import (
    CareerClaimRepository,
    CareerEntityRepository,
    CareerTwinRepository,
    ConflictSetRepository,
    SuggestionRepository,
    SuppressionRepository,
)
from onejob.career_twin.service import (
    ApproveClaimCommand,
    CareerTwinCommandService,
)
from onejob.career_twin.suggestions import DecisionState, Disposition
from onejob.career_twin.suppression import (
    SuppressionRecord,
    SuppressionStrength,
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
        CareerEntityRepository().insert(
            conn,
            CareerEntity(
                entity_id="experience-1",
                twin_id="twin-1",
                entity_type=EntityType.EXPERIENCE,
                lifecycle_state=EntityLifecycle.ACTIVE,
                created_at=NOW,
            ),
        )
    return db


def actor():
    return {"actor_id": "user-1", "twin_id": "twin-1", "is_owner": True}


def import_actor():
    return {"actor_id": "importer", "twin_id": "twin-1", "is_owner": False}


# ---------------------------------------------------------------------------
# SubmitDirectFact
# ---------------------------------------------------------------------------


def test_direct_fact_create_new_writes_canonical_claim(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    service = SuggestionCommandService(db, id_factory=ids)

    result = service.submit_direct_fact(
        SubmitDirectFactCommand(
            twin_id="twin-1",
            entity_intent="EDIT_EXISTING",
            entity_id="experience-1",
            predicate=Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
            value="PERMANENT",
            value_type="TEXT",
            expected_active_claim_id=None,
            source_type="USER_INPUT",
            evidence_family_id="fam-1",
            payload_fingerprint="pfp-1",
            idempotency_key="idem-df-1",
        ),
        actor=actor(),
        now=NOW,
    )

    with db.connection() as conn:
        claim = CareerClaimRepository().active_for_family(
            conn,
            "twin-1",
            "experience-1",
            Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
        )
    assert claim is not None
    assert claim.value == "PERMANENT"
    assert claim.claim_id == result.claim_id


def test_direct_fact_requires_owner_actor(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    service = SuggestionCommandService(db, id_factory=ids)

    # A non-human import actor may not invoke the direct-fact canonical path
    # merely by labeling its source USER_INPUT.
    with pytest.raises(AuthorizationDenied):
        service.submit_direct_fact(
            SubmitDirectFactCommand(
                twin_id="twin-1",
                entity_intent="EDIT_EXISTING",
                entity_id="experience-1",
                predicate=Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
                value="PERMANENT",
                value_type="TEXT",
                expected_active_claim_id=None,
                source_type="USER_INPUT",
                evidence_family_id="fam-1",
                payload_fingerprint="pfp-1",
                idempotency_key="idem-df-1",
            ),
            actor=import_actor(),
            now=NOW,
        )


def test_direct_fact_edit_existing_requires_entity_id(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    service = SuggestionCommandService(db, id_factory=ids)

    with pytest.raises(ValueError):
        service.submit_direct_fact(
            SubmitDirectFactCommand(
                twin_id="twin-1",
                entity_intent="EDIT_EXISTING",
                entity_id=None,
                predicate=Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
                value="PERMANENT",
                value_type="TEXT",
                expected_active_claim_id=None,
                source_type="USER_INPUT",
                evidence_family_id="fam-1",
                payload_fingerprint="pfp-1",
                idempotency_key="idem-df-1",
            ),
            actor=actor(),
            now=NOW,
        )


def test_direct_fact_is_idempotent(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    service = SuggestionCommandService(db, id_factory=ids)

    cmd = SubmitDirectFactCommand(
        twin_id="twin-1",
        entity_intent="EDIT_EXISTING",
        entity_id="experience-1",
        predicate=Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
        value="PERMANENT",
        value_type="TEXT",
        expected_active_claim_id=None,
        source_type="USER_INPUT",
        evidence_family_id="fam-1",
        payload_fingerprint="pfp-1",
        idempotency_key="idem-df-1",
    )
    first = service.submit_direct_fact(cmd, actor=actor(), now=NOW)
    second = service.submit_direct_fact(cmd, actor=actor(), now=NOW)
    assert first.claim_id == second.claim_id

    with db.connection() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM career_claims WHERE twin_id = ?",
            ("twin-1",),
        ).fetchone()["n"]
    assert n == 1


# ---------------------------------------------------------------------------
# ResolveConflict
# ---------------------------------------------------------------------------


def seed_conflict_with_suggestion(db, ids):
    # Existing canonical claim (PERMANENT), plus a competing CONTRACT
    # suggestion and an OPEN conflict.
    canonical = CareerTwinCommandService(db, id_factory=ids)
    with db.transaction() as conn:
        claim = canonical.approve_claim_in_transaction(
            conn,
            ApproveClaimCommand(
                twin_id="twin-1",
                entity_id="experience-1",
                predicate=Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
                value="PERMANENT",
                value_type="TEXT",
                evidence_ids=(),
                expected_active_claim_id=None,
                ontology_version=ONTOLOGY_VERSION,
            ),
            now=NOW,
        )

    intake = IntakeService(db, id_factory=ids)
    result = intake.intake(
        IntakeRequest(
            twin_id="twin-1",
            source_type="USER_INPUT",
            intake_version="intake-v1",
            evidence_family_id="fam-2",
            proposals=[
                CandidateProposal(
                    proposed_entity_type=EntityType.EXPERIENCE,
                    display_hint="Operator",
                    facts=[
                        ProposedFact(
                            predicate=Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
                            value="CONTRACT",
                            value_type="TEXT",
                            expected_active_claim_id=claim.claim_id,
                        )
                    ],
                    evidence=[
                        ProposedEvidence(
                            source_type="USER_INPUT",
                            trust_tier="TIER_SELF",
                            independence_status="INDEPENDENT",
                            privacy_class=PrivacyClass.CAREER_PRIVATE,
                            payload_fingerprint="pfp-2",
                        )
                    ],
                )
            ],
        ),
        now=NOW,
    )
    suggestion_id = result.suggestion_ids[0]

    conflicts = ConflictSetRepository()
    with db.transaction() as conn:
        # resolve the candidate to the canonical entity and mark the competing
        # proposal as CONFLICT disposition (as the conflict detector would).
        s = SuggestionRepository().get(conn, suggestion_id)
        SuggestionRepository().update_versioned(
            conn,
            s.model_copy(
                update={
                    "resolved_entity_id": "experience-1",
                    "disposition": Disposition.CONFLICT,
                    "version": s.version + 1,
                }
            ),
            expected_version=s.version,
        )
        conflicts.insert(
            conn,
            ConflictSet(
                conflict_id="conflict-1",
                twin_id="twin-1",
                entity_id="experience-1",
                predicate=Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
                active_claim_id=claim.claim_id,
                status=ConflictStatus.OPEN,
                version=1,
                created_at=NOW,
            ),
        )
        conflicts.link_suggestion(conn, "conflict-1", suggestion_id)

    return claim.claim_id, suggestion_id


def test_resolve_conflict_accept_alternative_supersedes_claim(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    active_claim_id, suggestion_id = seed_conflict_with_suggestion(db, ids)
    service = SuggestionCommandService(db, id_factory=ids)

    service.resolve_conflict(
        ResolveConflictCommand(
            twin_id="twin-1",
            conflict_id="conflict-1",
            action="ACCEPT_ALTERNATIVE",
            selected_suggestion_id=suggestion_id,
            expected_active_claim_id=active_claim_id,
            expected_conflict_version=1,
            idempotency_key="idem-rc-1",
        ),
        actor=actor(),
        now=NOW,
    )

    with db.connection() as conn:
        claim = CareerClaimRepository().active_for_family(
            conn,
            "twin-1",
            "experience-1",
            Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
        )
        conflict = ConflictSetRepository().get(conn, "conflict-1")
        suggestion = SuggestionRepository().get(conn, suggestion_id)

    assert claim.value == "CONTRACT"
    assert claim.supersedes_claim_id == active_claim_id
    assert conflict.status is ConflictStatus.RESOLVED
    assert suggestion.decision_state is DecisionState.APPROVED


def test_resolve_conflict_keep_current_preserves_claim(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    active_claim_id, suggestion_id = seed_conflict_with_suggestion(db, ids)
    service = SuggestionCommandService(db, id_factory=ids)

    service.resolve_conflict(
        ResolveConflictCommand(
            twin_id="twin-1",
            conflict_id="conflict-1",
            action="KEEP_CURRENT",
            selected_suggestion_id=suggestion_id,
            expected_active_claim_id=active_claim_id,
            expected_conflict_version=1,
            idempotency_key="idem-rc-1",
        ),
        actor=actor(),
        now=NOW,
    )

    with db.connection() as conn:
        claim = CareerClaimRepository().active_for_family(
            conn,
            "twin-1",
            "experience-1",
            Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
        )
        conflict = ConflictSetRepository().get(conn, "conflict-1")
        suggestion = SuggestionRepository().get(conn, suggestion_id)

    # Current claim preserved; competing suggestion rejected.
    assert claim.claim_id == active_claim_id
    assert claim.value == "PERMANENT"
    assert conflict.status is ConflictStatus.RESOLVED
    assert suggestion.decision_state is DecisionState.REJECTED


def test_resolve_conflict_defer_changes_nothing(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    active_claim_id, suggestion_id = seed_conflict_with_suggestion(db, ids)
    service = SuggestionCommandService(db, id_factory=ids)

    service.resolve_conflict(
        ResolveConflictCommand(
            twin_id="twin-1",
            conflict_id="conflict-1",
            action="DEFER",
            selected_suggestion_id=suggestion_id,
            expected_active_claim_id=active_claim_id,
            expected_conflict_version=1,
            idempotency_key="idem-rc-1",
        ),
        actor=actor(),
        now=NOW,
    )

    with db.connection() as conn:
        conflict = ConflictSetRepository().get(conn, "conflict-1")
        claim = CareerClaimRepository().active_for_family(
            conn,
            "twin-1",
            "experience-1",
            Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
        )

    assert conflict.status is ConflictStatus.OPEN
    assert claim.value == "PERMANENT"


def test_resolve_conflict_rejects_stale_conflict_version(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    active_claim_id, suggestion_id = seed_conflict_with_suggestion(db, ids)
    service = SuggestionCommandService(db, id_factory=ids)

    with pytest.raises(StaleConflictState):
        service.resolve_conflict(
            ResolveConflictCommand(
                twin_id="twin-1",
                conflict_id="conflict-1",
                action="ACCEPT_ALTERNATIVE",
                selected_suggestion_id=suggestion_id,
                expected_active_claim_id=active_claim_id,
                expected_conflict_version=99,
                idempotency_key="idem-rc-1",
            ),
            actor=actor(),
            now=NOW,
        )


def test_resolve_conflict_rejects_stale_active_claim(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    active_claim_id, suggestion_id = seed_conflict_with_suggestion(db, ids)
    service = SuggestionCommandService(db, id_factory=ids)

    with pytest.raises(StaleClaimState):
        service.resolve_conflict(
            ResolveConflictCommand(
                twin_id="twin-1",
                conflict_id="conflict-1",
                action="ACCEPT_ALTERNATIVE",
                selected_suggestion_id=suggestion_id,
                expected_active_claim_id="claim-stale",
                expected_conflict_version=1,
                idempotency_key="idem-rc-1",
            ),
            actor=actor(),
            now=NOW,
        )


def test_resolve_conflict_invalid_action(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    active_claim_id, suggestion_id = seed_conflict_with_suggestion(db, ids)
    service = SuggestionCommandService(db, id_factory=ids)

    with pytest.raises(InvalidConflictResolution):
        service.resolve_conflict(
            ResolveConflictCommand(
                twin_id="twin-1",
                conflict_id="conflict-1",
                action="NONSENSE",
                selected_suggestion_id=suggestion_id,
                expected_active_claim_id=active_claim_id,
                expected_conflict_version=1,
                idempotency_key="idem-rc-1",
            ),
            actor=actor(),
            now=NOW,
        )


# ---------------------------------------------------------------------------
# LiftSuppression
# ---------------------------------------------------------------------------


def test_lift_suppression_marks_record_lifted(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    with db.transaction() as conn:
        SuppressionRepository().insert(
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

    service = SuggestionCommandService(db, id_factory=ids)
    service.lift_suppression(
        LiftSuppressionCommand(
            twin_id="twin-1",
            suppression_id="supp-1",
            idempotency_key="idem-lift-1",
        ),
        actor=actor(),
        now=NOW,
    )

    with db.connection() as conn:
        matches = SuppressionRepository().active_matches(
            conn,
            twin_id="twin-1",
            predicate=Predicate.EXPERIENCE_ROLE,
            normalized_value_fingerprint="nfp-1",
        )
    assert matches == []
