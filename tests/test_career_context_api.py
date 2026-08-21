from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from onejob.career_context.api import create_career_context_router
from onejob.career_twin.ontology import ONTOLOGY_VERSION
from onejob.career_twin.repositories import CareerTwinRepository
from onejob.persistence.db import Database


AT = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)


class SequentialIds:
    def __init__(self):
        self.counts = {}

    def __call__(self, kind: str) -> str:
        n = self.counts.get(kind, 0) + 1
        self.counts[kind] = n
        return f"{kind}-{n}"


def build(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    with db.transaction() as conn:
        CareerTwinRepository().ensure_twin(conn, "twin-1", "user-1", ONTOLOGY_VERSION)
    app = FastAPI()
    app.include_router(
        create_career_context_router(
            db,
            id_factory=SequentialIds(),
            actor_resolver=lambda: {
                "actor_id": "user-1", "twin_id": "twin-1",
                "is_owner": True, "actor_type": "USER",
            },
            now_factory=lambda: AT,
        )
    )
    return TestClient(app, raise_server_exceptions=False), db


def test_create_intent_version_and_get_safe_view(tmp_path):
    client, db = build(tmp_path)

    resp = client.post(
        "/api/career-intent/versions",
        json={
            "idempotency_key": "i1",
            "expected_active_version_id": None,
            "statements": [
                {
                    "predicate": "COMPENSATION.MIN_SALARY",
                    "operator": "GTE",
                    "value": 6_000_000,
                    "strength": "HARD_CONSTRAINT",
                    "value_type": "MONEY",
                    "unknown_policy": "REQUIRE_VERIFICATION",
                }
            ],
        },
    )
    assert resp.status_code == 200

    view = client.get("/api/career-intent")
    assert view.status_code == 200
    body = view.json()
    assert "active_version" in body
    assert "statements" in body
    # no raw internals
    text = str(body)
    assert "input_fingerprint" not in body
    assert "outbox" not in text.lower()


def test_stale_version_maps_to_409(tmp_path):
    client, db = build(tmp_path)
    client.post(
        "/api/career-intent/versions",
        json={"idempotency_key": "i1", "expected_active_version_id": None,
              "statements": [{"predicate": "COMPENSATION.MIN_SALARY", "operator": "GTE",
                              "value": 6_000_000, "strength": "HARD_CONSTRAINT",
                              "value_type": "MONEY"}]},
    )
    # expecting None again after v1 exists → stale
    resp = client.post(
        "/api/career-intent/versions",
        json={"idempotency_key": "i2", "expected_active_version_id": None,
              "statements": [{"predicate": "COMPENSATION.MIN_SALARY", "operator": "GTE",
                              "value": 7_000_000, "strength": "HARD_CONSTRAINT",
                              "value_type": "MONEY"}]},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error_code"] == "STALE_VERSION"


def test_unsatisfiable_intent_maps_to_422(tmp_path):
    client, db = build(tmp_path)
    resp = client.post(
        "/api/career-intent/versions",
        json={"idempotency_key": "i1", "expected_active_version_id": None,
              "statements": [
                  {"predicate": "COMPENSATION.MIN_SALARY", "operator": "GTE",
                   "value": 7_000_000, "strength": "HARD_CONSTRAINT", "value_type": "MONEY"},
                  {"predicate": "COMPENSATION.MAX_SALARY", "operator": "LTE",
                   "value": 6_000_000, "strength": "HARD_CONSTRAINT", "value_type": "MONEY"},
              ]},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error_code"] == "UNSATISFIABLE_INTENT"


def test_unknown_predicate_maps_to_domain_error(tmp_path):
    client, db = build(tmp_path)
    resp = client.post(
        "/api/career-intent/versions",
        json={"idempotency_key": "i1", "expected_active_version_id": None,
              "statements": [{"predicate": "ARBITRARY.EXPR", "operator": "GTE",
                              "value": 1, "strength": "HARD_CONSTRAINT", "value_type": "MONEY"}]},
    )
    assert resp.status_code in (400, 422)


def test_create_and_list_targets(tmp_path):
    client, db = build(tmp_path)
    client.post(
        "/api/career-intent/versions",
        json={"idempotency_key": "i1", "expected_active_version_id": None,
              "statements": [{"predicate": "COMPENSATION.MIN_SALARY", "operator": "GTE",
                              "value": 6_000_000, "strength": "HARD_CONSTRAINT", "value_type": "MONEY"}]},
    )
    resp = client.post(
        "/api/career-targets",
        json={
            "idempotency_key": "t1",
            "display_name": "Warehouse",
            "role_focus": ["operator"],
            "domain_focus": ["logistics"],
            "explicit_keywords": ["forklift"],
            "scope_definition": {"location": "bekasi"},
            "overrides": [],
        },
    )
    assert resp.status_code == 200
    target_id = resp.json()["target_id"]

    listing = client.get("/api/career-targets")
    assert listing.status_code == 200
    assert any(t["target_id"] == target_id for t in listing.json())

    detail = client.get(f"/api/career-targets/{target_id}")
    assert detail.status_code == 200
    assert "compatibility_status" in detail.json()


def test_route_and_evaluate_domain_outcomes_are_not_500(tmp_path):
    client, db = build(tmp_path)
    client.post(
        "/api/career-intent/versions",
        json={"idempotency_key": "i1", "expected_active_version_id": None,
              "statements": [{"predicate": "COMPENSATION.MIN_SALARY", "operator": "GTE",
                              "value": 6_000_000, "strength": "HARD_CONSTRAINT", "value_type": "MONEY"}]},
    )
    resp = client.post(
        "/api/career-context/route",
        json={"job_id": "oj-nonexistent"},
    )
    # unknown job → 404, not 500
    assert resp.status_code in (404, 200)


def test_lift_missing_unauthorized_probe_uses_access_safe(tmp_path):
    client, db = build(tmp_path)
    # get a target that does not exist → 404
    resp = client.get("/api/career-targets/does-not-exist")
    assert resp.status_code == 404
