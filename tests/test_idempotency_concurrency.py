from datetime import datetime, timezone

import pytest

from onejob.career_twin.errors import (
    IdempotencyConflict,
    StaleConflictState,
    StaleSuggestionState,
)
from onejob.career_twin.idempotency import (
    IdempotencyOutcome,
    request_fingerprint,
    reserve_idempotency,
)
from onejob.career_twin.repositories import (
    CareerTwinRepository,
    IdempotencyRepository,
)
from onejob.career_twin.ontology import ONTOLOGY_VERSION
from onejob.persistence.db import Database


NOW = datetime(2026, 8, 21, 3, 0, tzinfo=timezone.utc)


def make_db(tmp_path) -> Database:
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    with db.transaction() as conn:
        CareerTwinRepository().ensure_twin(
            conn, "twin-1", "user-1", ONTOLOGY_VERSION
        )
    return db


# ---------------------------------------------------------------------------
# request fingerprint
# ---------------------------------------------------------------------------


def test_request_fingerprint_is_order_independent_for_mappings():
    a = request_fingerprint({"a": 1, "b": 2})
    b = request_fingerprint({"b": 2, "a": 1})
    assert a == b


def test_request_fingerprint_differs_for_different_payload():
    a = request_fingerprint({"a": 1})
    b = request_fingerprint({"a": 2})
    assert a != b


# ---------------------------------------------------------------------------
# reserve_idempotency
# ---------------------------------------------------------------------------


def test_first_use_reserves_and_reports_new(tmp_path):
    db = make_db(tmp_path)
    repo = IdempotencyRepository()

    with db.transaction() as conn:
        outcome = reserve_idempotency(
            conn,
            repo,
            idempotency_key="idem-1",
            fingerprint="fp-1",
            now=NOW,
        )

    assert isinstance(outcome, IdempotencyOutcome)
    assert outcome.replay is False
    assert outcome.result_reference is None


def test_same_key_same_request_replays_original_result(tmp_path):
    db = make_db(tmp_path)
    repo = IdempotencyRepository()

    with db.transaction() as conn:
        reserve_idempotency(
            conn, repo, idempotency_key="idem-1", fingerprint="fp-1", now=NOW
        )
        repo.store  # ensure attribute exists
    # simulate command completion recording the result
    with db.transaction() as conn:
        conn.execute(
            "UPDATE career_idempotency_keys SET result_reference = ? "
            "WHERE idempotency_key = ?",
            ("suggestion-1", "idem-1"),
        )

    with db.transaction() as conn:
        outcome = reserve_idempotency(
            conn, repo, idempotency_key="idem-1", fingerprint="fp-1", now=NOW
        )

    assert outcome.replay is True
    assert outcome.result_reference == "suggestion-1"


def test_same_key_different_request_raises_conflict(tmp_path):
    db = make_db(tmp_path)
    repo = IdempotencyRepository()

    with db.transaction() as conn:
        reserve_idempotency(
            conn, repo, idempotency_key="idem-1", fingerprint="fp-1", now=NOW
        )

    with pytest.raises(IdempotencyConflict):
        with db.transaction() as conn:
            reserve_idempotency(
                conn,
                repo,
                idempotency_key="idem-1",
                fingerprint="fp-DIFFERENT",
                now=NOW,
            )


# ---------------------------------------------------------------------------
# error taxonomy shape
# ---------------------------------------------------------------------------


def test_stale_errors_are_distinct_types():
    assert issubclass(StaleSuggestionState, RuntimeError)
    assert issubclass(StaleConflictState, RuntimeError)
    assert not issubclass(StaleSuggestionState, StaleConflictState)
