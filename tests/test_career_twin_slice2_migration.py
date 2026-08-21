from onejob.persistence.db import Database


# Tables introduced by the Slice 2 forward-only migration.
SLICE2_TABLES = [
    "career_suggestion_batches",
    "career_candidate_entities",
    "career_atomic_suggestions",
    "career_suggestion_evidence",
    "career_entity_resolutions",
    "career_conflict_sets",
    "career_conflict_suggestions",
    "career_suppression_records",
    "career_idempotency_keys",
]


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _table_names(conn) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {row["name"] for row in rows}


def test_fresh_database_creates_all_slice2_tables(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()

    with db.connection() as conn:
        tables = _table_names(conn)

    for table in SLICE2_TABLES:
        assert table in tables, f"missing table: {table}"


def test_slice2_migration_is_recorded(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()

    with db.connection() as conn:
        versions = {
            row["version"]
            for row in conn.execute(
                "SELECT version FROM schema_migrations"
            ).fetchall()
        }

    assert "005_career_twin_suggestions" in versions


def test_migration_is_idempotent_when_run_twice(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    # Running initialize again must not fail or duplicate anything.
    db.initialize()

    with db.connection() as conn:
        count = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM schema_migrations
            WHERE version = '005_career_twin_suggestions'
            """
        ).fetchone()["n"]

    assert count == 1


def test_old_database_migrates_forward(tmp_path):
    # Simulate a database created before Slice 2 by applying only the
    # migrations up to 004 and marking 005 as absent, then re-initialize.
    db_path = tmp_path / "gaweyuk.db"

    # First initialization installs everything; to simulate an "old" DB we
    # delete the Slice 2 tables and its migration marker, then re-run.
    db = Database(db_path)
    db.initialize()

    with db._connect() as conn:
        for table in SLICE2_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute(
            """
            DELETE FROM schema_migrations
            WHERE version = '005_career_twin_suggestions'
            """
        )
        conn.commit()

    # Forward migration should recreate all Slice 2 tables.
    db.initialize()

    with db.connection() as conn:
        tables = _table_names(conn)

    for table in SLICE2_TABLES:
        assert table in tables


def test_atomic_suggestion_table_has_two_axis_and_version_columns(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()

    with db.connection() as conn:
        cols = _table_columns(conn, "career_atomic_suggestions")

    required = {
        "suggestion_id",
        "batch_id",
        "twin_id",
        "candidate_id",
        "resolved_entity_id",
        "predicate",
        "proposed_value_json",
        "value_type",
        "decision_state",
        "disposition",
        "normalized_value_fingerprint",
        "expected_active_claim_id",
        "version",
        "created_at",
        "decided_at",
        "decision_actor_id",
    }
    assert required.issubset(cols), required - cols


def test_candidate_table_tracks_lifecycle_and_promotion(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()

    with db.connection() as conn:
        cols = _table_columns(conn, "career_candidate_entities")

    required = {
        "candidate_id",
        "batch_id",
        "twin_id",
        "proposed_entity_type",
        "fingerprint",
        "display_hint",
        "lifecycle_state",
        "created_at",
        "promoted_entity_id",
    }
    assert required.issubset(cols), required - cols


def test_idempotency_table_supports_key_reuse_detection(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()

    with db.connection() as conn:
        cols = _table_columns(conn, "career_idempotency_keys")

    required = {
        "idempotency_key",
        "request_fingerprint",
        "result_reference",
        "created_at",
    }
    assert required.issubset(cols), required - cols


def test_conflict_set_and_link_tables_present(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()

    with db.connection() as conn:
        conflict_cols = _table_columns(conn, "career_conflict_sets")
        link_cols = _table_columns(conn, "career_conflict_suggestions")

    assert {
        "conflict_id",
        "twin_id",
        "entity_id",
        "predicate",
        "active_claim_id",
        "status",
        "version",
        "created_at",
    }.issubset(conflict_cols)

    assert {"conflict_id", "suggestion_id"}.issubset(link_cols)


def test_suppression_table_present_with_strength(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()

    with db.connection() as conn:
        cols = _table_columns(conn, "career_suppression_records")

    required = {
        "suppression_id",
        "twin_id",
        "predicate",
        "normalized_value_fingerprint",
        "strength",
        "reason",
        "created_at",
    }
    assert required.issubset(cols), required - cols


def test_existing_slice1_claims_are_untouched_by_slice2_migration(tmp_path):
    # The Slice 2 migration must not drop or rewrite Slice 1 tables.
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()

    with db.connection() as conn:
        tables = _table_names(conn)

    for table in [
        "career_claims",
        "career_entities",
        "career_evidence",
        "career_events",
        "career_event_outbox",
        "career_legacy_imports",
    ]:
        assert table in tables
