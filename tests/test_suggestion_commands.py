from datetime import datetime, timezone

import pytest

from onejob.career_twin.commands import (
    ApproveSuggestionCommand,
    RejectSuggestionCommand,
    SuggestionCommandService,
)
from onejob.career_twin.errors import (
    IdempotencyConflict,
    StaleSuggestionState,
    SuggestionNotFound,
)
from onejob.career_twin.intake import (
    CandidateProposal,
    IntakeRequest,
    IntakeService,
    ProposedEvidence,
    ProposedFact,
)
from onejob.career_twin.models import (
    CareerEntity,
    EntityLifecycle,
)
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
    SuggestionRepository,
)
from onejob.career_twin.suggestions import DecisionState, Disposition
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
        # canonical entity the suggestion resolves to
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


def seed_suggestion(
    db: Database,
    ids: SequentialIds,
    *,
    predicate: Predicate = Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
    value: str = "PERMANENT",
    value_type: str = "TEXT",
) -> str:
    intake = IntakeService(db, id_factory=ids)
    result = intake.intake(
        IntakeRequest(
            twin_id="twin-1",
            source_type="USER_INPUT",
            intake_version="intake-v1",
            evidence_family_id="fam-1",
            proposals=[
                CandidateProposal(
                    proposed_entity_type=EntityType.EXPERIENCE,
                    display_hint="Operator @ PT Example",
                    facts=[
                        ProposedFact(
                            predicate=predicate,
                            value=value,
                            value_type=value_type,
                        )
                    ],
                    evidence=[
                        ProposedEvidence(
                            source_type="USER_INPUT",
                            trust_tier="TIER_SELF",
                            independence_status="INDEPENDENT",
                            privacy_class=PrivacyClass.CAREER_PRIVATE,
                            payload_fingerprint="pfp-1",
                        )
                    ],
                )
            ],
        ),
        now=NOW,
    )
    return result.suggestion_ids[0]


def actor():
    return {"actor_id": "user-1", "twin_id": "twin-1", "is_owner": True}


# ---------------------------------------------------------------------------
# Approve
# ---------------------------------------------------------------------------


def test_approve_creates_canonical_claim_and_marks_suggestion(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    suggestion_id = seed_suggestion(db, ids)

    service = SuggestionCommandService(db, id_factory=ids)
    result = service.approve(
        ApproveSuggestionCommand(
            twin_id="twin-1",
            suggestion_id=suggestion_id,
            expected_suggestion_version=1,
            expected_active_claim_id=None,
            selected_entity_id="experience-1",
            idempotency_key="idem-approve-1",
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
        suggestion = SuggestionRepository().get(conn, suggestion_id)
        events = conn.execute(
            "SELECT event_type FROM career_events WHERE twin_id = ? "
            "ORDER BY event_id",
            ("twin-1",),
        ).fetchall()

    assert claim is not None
    assert claim.value == "PERMANENT"
    assert claim.claim_id == result.claim_id
    assert suggestion.decision_state is DecisionState.APPROVED
    event_types = {e["event_type"] for e in events}
    assert "CLAIM_APPROVED" in event_types
    assert "SUGGESTION_APPROVED" in event_types


def test_approve_is_idempotent_on_retry(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    suggestion_id = seed_suggestion(db, ids)
    service = SuggestionCommandService(db, id_factory=ids)

    cmd = ApproveSuggestionCommand(
        twin_id="twin-1",
        suggestion_id=suggestion_id,
        expected_suggestion_version=1,
        expected_active_claim_id=None,
        selected_entity_id="experience-1",
        idempotency_key="idem-approve-1",
    )

    first = service.approve(cmd, actor=actor(), now=NOW)
    second = service.approve(cmd, actor=actor(), now=NOW)

    assert first.claim_id == second.claim_id

    with db.connection() as conn:
        claims = conn.execute(
            "SELECT COUNT(*) AS n FROM career_claims WHERE twin_id = ?",
            ("twin-1",),
        ).fetchone()["n"]
        approvals = conn.execute(
            "SELECT COUNT(*) AS n FROM career_events "
            "WHERE event_type = 'CLAIM_APPROVED'"
        ).fetchone()["n"]

    # Retry must not duplicate canonical effects.
    assert claims == 1
    assert approvals == 1


def test_approve_with_edited_value_keeps_suggestion_immutable(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    suggestion_id = seed_suggestion(db, ids)
    service = SuggestionCommandService(db, id_factory=ids)

    service.approve(
        ApproveSuggestionCommand(
            twin_id="twin-1",
            suggestion_id=suggestion_id,
            expected_suggestion_version=1,
            expected_active_claim_id=None,
            selected_entity_id="experience-1",
            edited_value="CONTRACT",
            idempotency_key="idem-approve-1",
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
        suggestion = SuggestionRepository().get(conn, suggestion_id)

    # Approved claim carries the edited value.
    assert claim.value == "CONTRACT"
    # Original suggestion proposal remains immutable.
    assert suggestion.proposed_value == "PERMANENT"
    assert suggestion.decision_state is DecisionState.APPROVED


def test_approve_rejects_stale_suggestion_version(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    suggestion_id = seed_suggestion(db, ids)
    service = SuggestionCommandService(db, id_factory=ids)

    with pytest.raises(StaleSuggestionState):
        service.approve(
            ApproveSuggestionCommand(
                twin_id="twin-1",
                suggestion_id=suggestion_id,
                expected_suggestion_version=99,
                expected_active_claim_id=None,
                selected_entity_id="experience-1",
                idempotency_key="idem-approve-1",
            ),
            actor=actor(),
            now=NOW,
        )


def test_approve_unknown_suggestion_raises(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    service = SuggestionCommandService(db, id_factory=ids)

    with pytest.raises(SuggestionNotFound):
        service.approve(
            ApproveSuggestionCommand(
                twin_id="twin-1",
                suggestion_id="nope",
                expected_suggestion_version=1,
                expected_active_claim_id=None,
                selected_entity_id="experience-1",
                idempotency_key="idem-approve-1",
            ),
            actor=actor(),
            now=NOW,
        )


def test_approve_same_key_different_request_conflicts(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    suggestion_id = seed_suggestion(db, ids)
    service = SuggestionCommandService(db, id_factory=ids)

    service.approve(
        ApproveSuggestionCommand(
            twin_id="twin-1",
            suggestion_id=suggestion_id,
            expected_suggestion_version=1,
            expected_active_claim_id=None,
            selected_entity_id="experience-1",
            idempotency_key="idem-shared",
        ),
        actor=actor(),
        now=NOW,
    )

    with pytest.raises(IdempotencyConflict):
        service.approve(
            ApproveSuggestionCommand(
                twin_id="twin-1",
                suggestion_id=suggestion_id,
                expected_suggestion_version=2,
                expected_active_claim_id=None,
                selected_entity_id="experience-1",
                edited_value="CONTRACT",
                idempotency_key="idem-shared",
            ),
            actor=actor(),
            now=NOW,
        )


# ---------------------------------------------------------------------------
# Reject
# ---------------------------------------------------------------------------


def test_reject_records_rejection_without_canonical_claim(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    suggestion_id = seed_suggestion(db, ids)
    service = SuggestionCommandService(db, id_factory=ids)

    service.reject(
        RejectSuggestionCommand(
            twin_id="twin-1",
            suggestion_id=suggestion_id,
            expected_suggestion_version=1,
            reason="not correct",
            suppression_mode="NONE",
            idempotency_key="idem-reject-1",
        ),
        actor=actor(),
        now=NOW,
    )

    with db.connection() as conn:
        suggestion = SuggestionRepository().get(conn, suggestion_id)
        claims = conn.execute(
            "SELECT COUNT(*) AS n FROM career_claims WHERE twin_id = ?",
            ("twin-1",),
        ).fetchone()["n"]

    assert suggestion.decision_state is DecisionState.REJECTED
    # Rejection is never a canonical claim.
    assert claims == 0


def test_reject_with_strong_suppression_creates_suppression_record(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    suggestion_id = seed_suggestion(db, ids)
    service = SuggestionCommandService(db, id_factory=ids)

    service.reject(
        RejectSuggestionCommand(
            twin_id="twin-1",
            suggestion_id=suggestion_id,
            expected_suggestion_version=1,
            reason="stop suggesting",
            suppression_mode="STRONG",
            idempotency_key="idem-reject-1",
        ),
        actor=actor(),
        now=NOW,
    )

    with db.connection() as conn:
        suggestion = SuggestionRepository().get(conn, suggestion_id)
        supp = conn.execute(
            "SELECT COUNT(*) AS n FROM career_suppression_records "
            "WHERE twin_id = ?",
            ("twin-1",),
        ).fetchone()["n"]

    assert suggestion.decision_state is DecisionState.REJECTED
    assert suggestion.disposition is Disposition.SUPPRESSED
    assert supp == 1


# ---------------------------------------------------------------------------
# Atomicity / failure injection
# ---------------------------------------------------------------------------


def test_injected_failure_after_claim_rolls_back_everything(tmp_path):
    ids = SequentialIds()
    db = make_db(tmp_path)
    suggestion_id = seed_suggestion(db, ids)
    service = SuggestionCommandService(db, id_factory=ids)

    def boom(conn, **kwargs):
        raise RuntimeError("injected failure after claim creation")

    # Inject a failure into the post-claim hook.
    service._after_claim_hook = boom

    with pytest.raises(RuntimeError):
        service.approve(
            ApproveSuggestionCommand(
                twin_id="twin-1",
                suggestion_id=suggestion_id,
                expected_suggestion_version=1,
                expected_active_claim_id=None,
                selected_entity_id="experience-1",
                idempotency_key="idem-approve-1",
            ),
            actor=actor(),
            now=NOW,
        )

    with db.connection() as conn:
        claims = conn.execute(
            "SELECT COUNT(*) AS n FROM career_claims WHERE twin_id = ?",
            ("twin-1",),
        ).fetchone()["n"]
        events = conn.execute(
            "SELECT COUNT(*) AS n FROM career_events WHERE twin_id = ?",
            ("twin-1",),
        ).fetchone()["n"]
        idem = conn.execute(
            "SELECT COUNT(*) AS n FROM career_idempotency_keys"
        ).fetchone()["n"]
        suggestion = SuggestionRepository().get(conn, suggestion_id)

    # Full rollback: no partial canonical claim, no event, no idempotency
    # record, and the suggestion is not falsely marked approved.
    assert claims == 0
    assert events == 0
    assert idem == 0
    assert suggestion.decision_state is DecisionState.PENDING
