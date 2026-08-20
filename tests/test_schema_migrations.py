from onejob.persistence.db import Database


def test_initialize_applies_migrations_once(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")

    db.initialize()
    db.initialize()

    with db.connection() as conn:
        versions = conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()

        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    assert "003_career_twin_core" in {
        row[0] for row in versions
    }

    assert {
        "career_twins",
        "career_entities",
        "career_claims",
        "career_evidence",
        "career_claim_assessments",
        "career_events",
        "career_event_outbox",
    } <= tables
