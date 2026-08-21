from datetime import datetime, timezone

from onejob.career_twin.models import (
    CareerEntity,
    EntityLifecycle,
)
from onejob.career_twin.ontology import (
    EntityType,
    ONTOLOGY_VERSION,
    Predicate,
)
from onejob.career_twin.repositories import (
    CareerEntityRepository,
    CareerTwinRepository,
)
from onejob.career_twin.service import (
    ApproveClaimCommand,
    CareerTwinCommandService,
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


def setup_subject(db: Database) -> None:
    twins = CareerTwinRepository()
    entities = CareerEntityRepository()

    with db.transaction() as conn:
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


def test_approve_claim_commits_claim_event_and_outbox_atomically(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    setup_subject(db)

    service = CareerTwinCommandService(
        db,
        id_factory=SequentialIds(),
    )

    claim = service.approve_claim(
        ApproveClaimCommand(
            twin_id="twin-1",
            entity_id="experience-1",
            predicate=Predicate.EXPERIENCE_ROLE,
            value="role-stamping-operator",
            value_type="ROLE_REF",
            evidence_ids=(),
            expected_active_claim_id=None,
            ontology_version=ONTOLOGY_VERSION,
        ),
        now=NOW,
    )

    with db.connection() as conn:
        stored = conn.execute(
            """
            SELECT *
            FROM career_claims
            WHERE claim_id = ?
            """,
            (claim.claim_id,),
        ).fetchone()

        events = conn.execute(
            """
            SELECT *
            FROM career_events
            WHERE twin_id = ?
            ORDER BY occurred_at, event_id
            """,
            ("twin-1",),
        ).fetchall()

        outbox = conn.execute(
            """
            SELECT *
            FROM career_event_outbox
            ORDER BY event_id
            """
        ).fetchall()

    assert stored is not None
    assert stored["lifecycle_state"] == "ACTIVE"
    assert stored["approval_state"] == "APPROVED"

    assert len(events) == 1
    assert events[0]["event_type"] == "CLAIM_APPROVED"

    assert len(outbox) == 1
    assert outbox[0]["event_id"] == events[0]["event_id"]
    assert outbox[0]["status"] == "PENDING"


def test_approve_claim_rejects_stale_expected_active_claim_id(tmp_path):
    import pytest

    from onejob.career_twin.service import StaleClaimState

    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    setup_subject(db)

    service = CareerTwinCommandService(
        db,
        id_factory=SequentialIds(),
    )

    first = service.approve_claim(
        ApproveClaimCommand(
            twin_id="twin-1",
            entity_id="experience-1",
            predicate=Predicate.EXPERIENCE_ROLE,
            value="role-stamping-operator",
            value_type="ROLE_REF",
            evidence_ids=(),
            expected_active_claim_id=None,
            ontology_version=ONTOLOGY_VERSION,
        ),
        now=NOW,
    )

    with pytest.raises(StaleClaimState):
        service.approve_claim(
            ApproveClaimCommand(
                twin_id="twin-1",
                entity_id="experience-1",
                predicate=Predicate.EXPERIENCE_ROLE,
                value="role-production-operator",
                value_type="ROLE_REF",
                evidence_ids=(),
                expected_active_claim_id="wrong-claim-id",
                ontology_version=ONTOLOGY_VERSION,
            ),
            now=NOW,
        )

    with db.connection() as conn:
        claims = conn.execute(
            """
            SELECT claim_id, lifecycle_state
            FROM career_claims
            ORDER BY claim_id
            """
        ).fetchall()

        events = conn.execute(
            """
            SELECT event_type
            FROM career_events
            ORDER BY event_id
            """
        ).fetchall()

        outbox = conn.execute(
            """
            SELECT event_id
            FROM career_event_outbox
            ORDER BY event_id
            """
        ).fetchall()

    assert first.claim_id == "claim-1"

    assert [
        (row["claim_id"], row["lifecycle_state"])
        for row in claims
    ] == [
        ("claim-1", "ACTIVE"),
    ]

    assert [
        row["event_type"]
        for row in events
    ] == [
        "CLAIM_APPROVED",
    ]

    assert len(outbox) == 1


def test_valid_replacement_supersedes_old_claim_and_emits_events(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    setup_subject(db)

    service = CareerTwinCommandService(
        db,
        id_factory=SequentialIds(),
    )

    first = service.approve_claim(
        ApproveClaimCommand(
            twin_id="twin-1",
            entity_id="experience-1",
            predicate=Predicate.EXPERIENCE_ROLE,
            value="role-production-operator",
            value_type="ROLE_REF",
            evidence_ids=(),
            expected_active_claim_id=None,
            ontology_version=ONTOLOGY_VERSION,
        ),
        now=NOW,
    )

    second = service.approve_claim(
        ApproveClaimCommand(
            twin_id="twin-1",
            entity_id="experience-1",
            predicate=Predicate.EXPERIENCE_ROLE,
            value="role-stamping-operator",
            value_type="ROLE_REF",
            evidence_ids=(),
            expected_active_claim_id=first.claim_id,
            ontology_version=ONTOLOGY_VERSION,
        ),
        now=NOW,
    )

    with db.connection() as conn:
        rows = conn.execute(
            """
            SELECT
                claim_id,
                claim_family_id,
                lifecycle_state,
                supersedes_claim_id,
                value_json
            FROM career_claims
            ORDER BY claim_id
            """
        ).fetchall()

        events = conn.execute(
            """
            SELECT event_id, event_type, subject_id
            FROM career_events
            ORDER BY event_id
            """
        ).fetchall()

        outbox = conn.execute(
            """
            SELECT event_id, status
            FROM career_event_outbox
            ORDER BY event_id
            """
        ).fetchall()

    assert first.claim_id == "claim-1"
    assert second.claim_id == "claim-2"

    assert rows[0]["claim_id"] == "claim-1"
    assert rows[0]["lifecycle_state"] == "SUPERSEDED"

    assert rows[1]["claim_id"] == "claim-2"
    assert rows[1]["lifecycle_state"] == "ACTIVE"
    assert rows[1]["supersedes_claim_id"] == "claim-1"

    # Revisions belong to the same logical fact family.
    assert (
        rows[0]["claim_family_id"]
        == rows[1]["claim_family_id"]
    )

    # Factual payload history remains preserved.
    assert "role-production-operator" in rows[0]["value_json"]
    assert "role-stamping-operator" in rows[1]["value_json"]

    assert [
        event["event_type"]
        for event in events
    ] == [
        "CLAIM_APPROVED",
        "CLAIM_SUPERSEDED",
        "CLAIM_APPROVED",
    ]

    assert len(outbox) == 3
    assert all(
        row["status"] == "PENDING"
        for row in outbox
    )

    assert {
        row["event_id"]
        for row in outbox
    } == {
        row["event_id"]
        for row in events
    }


def test_replacement_rolls_back_if_outbox_persistence_fails(tmp_path):
    import sqlite3
    import pytest

    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    setup_subject(db)

    service = CareerTwinCommandService(
        db,
        id_factory=SequentialIds(),
    )

    first = service.approve_claim(
        ApproveClaimCommand(
            twin_id="twin-1",
            entity_id="experience-1",
            predicate=Predicate.EXPERIENCE_ROLE,
            value="role-production-operator",
            value_type="ROLE_REF",
            evidence_ids=(),
            expected_active_claim_id=None,
            ontology_version=ONTOLOGY_VERSION,
        ),
        now=NOW,
    )

    # Force every subsequent outbox INSERT to fail.
    with db.transaction() as conn:
        conn.execute(
            """
            CREATE TRIGGER fail_career_outbox_insert
            BEFORE INSERT ON career_event_outbox
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'forced outbox failure'
                );
            END
            """
        )

    with pytest.raises(
        sqlite3.IntegrityError,
        match="forced outbox failure",
    ):
        service.approve_claim(
            ApproveClaimCommand(
                twin_id="twin-1",
                entity_id="experience-1",
                predicate=Predicate.EXPERIENCE_ROLE,
                value="role-stamping-operator",
                value_type="ROLE_REF",
                evidence_ids=(),
                expected_active_claim_id=first.claim_id,
                ontology_version=ONTOLOGY_VERSION,
            ),
            now=NOW,
        )

    with db.connection() as conn:
        claims = conn.execute(
            """
            SELECT
                claim_id,
                lifecycle_state,
                supersedes_claim_id
            FROM career_claims
            ORDER BY claim_id
            """
        ).fetchall()

        events = conn.execute(
            """
            SELECT event_type
            FROM career_events
            ORDER BY event_id
            """
        ).fetchall()

        outbox = conn.execute(
            """
            SELECT event_id
            FROM career_event_outbox
            ORDER BY event_id
            """
        ).fetchall()

    # Replacement transaction must have vanished completely.
    assert [
        (
            row["claim_id"],
            row["lifecycle_state"],
            row["supersedes_claim_id"],
        )
        for row in claims
    ] == [
        (
            "claim-1",
            "ACTIVE",
            None,
        ),
    ]

    assert [
        row["event_type"]
        for row in events
    ] == [
        "CLAIM_APPROVED",
    ]

    assert len(outbox) == 1
