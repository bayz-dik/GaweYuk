from datetime import datetime, timezone

from onejob.career_twin.events import CareerEvent
from onejob.career_twin.repositories import CareerEventRepository
from onejob.persistence.db import Database


NOW = datetime(2026, 8, 21, 4, 0, tzinfo=timezone.utc)


def test_event_repository_persists_event_and_outbox_together(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()

    repo = CareerEventRepository()

    event = CareerEvent(
        event_id="event-1",
        twin_id="twin-1",
        event_type="CLAIM_APPROVED",
        subject_id="claim-1",
        occurred_at=NOW,
        payload={
            "claim_id": "claim-1",
        },
    )

    with db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO career_twins (
                twin_id,
                user_id,
                ontology_version,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "twin-1",
                "user-1",
                "career-v1",
                "ACTIVE",
                NOW.isoformat(),
            ),
        )

        repo.append_with_outbox(
            conn,
            event,
        )

    with db.connection() as conn:
        stored_event = conn.execute(
            """
            SELECT *
            FROM career_events
            WHERE event_id = ?
            """,
            ("event-1",),
        ).fetchone()

        stored_outbox = conn.execute(
            """
            SELECT *
            FROM career_event_outbox
            WHERE event_id = ?
            """,
            ("event-1",),
        ).fetchone()

    assert stored_event is not None
    assert stored_event["event_type"] == "CLAIM_APPROVED"
    assert stored_event["subject_id"] == "claim-1"

    assert stored_outbox is not None
    assert stored_outbox["status"] == "PENDING"
    assert stored_outbox["attempt_count"] == 0
