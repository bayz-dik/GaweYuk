from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from onejob.career_twin.api import create_career_twin_router
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
    CareerEntityRepository,
    CareerTwinRepository,
)
from onejob.persistence.db import Database


NOW = datetime(2026, 8, 21, 3, 0, tzinfo=timezone.utc)


class SequentialIds:
    def __init__(self):
        self.counts = {}

    def __call__(self, kind: str) -> str:
        n = self.counts.get(kind, 0) + 1
        self.counts[kind] = n
        return f"{kind}-{n}"


def build_client(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    ids = SequentialIds()
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

    app = FastAPI()
    # Static owner actor resolver for tests.
    app.include_router(
        create_career_twin_router(
            db,
            id_factory=ids,
            actor_resolver=lambda: {
                "actor_id": "user-1",
                "twin_id": "twin-1",
                "is_owner": True,
            },
            now_factory=lambda: NOW,
        )
    )
    return TestClient(app, raise_server_exceptions=False), db, ids


def seed_suggestion(db, ids):
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
                    display_hint="Operator",
                    facts=[
                        ProposedFact(
                            predicate=Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
                            value="PERMANENT",
                            value_type="TEXT",
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
    return result


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------


def test_list_suggestions_returns_safe_fields(tmp_path):
    client, db, ids = build_client(tmp_path)
    seed_suggestion(db, ids)

    resp = client.get("/api/career-twin/suggestions")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    item = items[0]

    # Safe explainability fields present.
    assert "suggestion_id" in item
    assert item["predicate"] == "EXPERIENCE.EMPLOYMENT_TYPE"
    assert item["decision_state"] == "PENDING"
    assert item["disposition"] == "READY"

    # No raw/private internals.
    for forbidden in (
        "payload_json",
        "raw_payload",
        "raw_evidence",
        "secret",
        "normalized_value_fingerprint",
    ):
        assert forbidden not in item


def test_get_single_suggestion(tmp_path):
    client, db, ids = build_client(tmp_path)
    result = seed_suggestion(db, ids)
    sid = result.suggestion_ids[0]

    resp = client.get(f"/api/career-twin/suggestions/{sid}")
    assert resp.status_code == 200
    assert resp.json()["suggestion_id"] == sid


def test_get_unknown_suggestion_returns_404(tmp_path):
    client, db, ids = build_client(tmp_path)
    resp = client.get("/api/career-twin/suggestions/nope")
    assert resp.status_code == 404


def test_list_suggestions_filter_by_decision_state(tmp_path):
    client, db, ids = build_client(tmp_path)
    seed_suggestion(db, ids)
    resp = client.get(
        "/api/career-twin/suggestions", params={"decision_state": "APPROVED"}
    )
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Write endpoints
# ---------------------------------------------------------------------------


def test_approve_endpoint_creates_claim(tmp_path):
    client, db, ids = build_client(tmp_path)
    result = seed_suggestion(db, ids)
    sid = result.suggestion_ids[0]

    resp = client.post(
        f"/api/career-twin/suggestions/{sid}/approve",
        json={
            "expected_suggestion_version": 1,
            "expected_active_claim_id": None,
            "selected_entity_id": "experience-1",
            "idempotency_key": "idem-a-1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["claim_id"]


def test_approve_stale_version_returns_409(tmp_path):
    client, db, ids = build_client(tmp_path)
    result = seed_suggestion(db, ids)
    sid = result.suggestion_ids[0]

    resp = client.post(
        f"/api/career-twin/suggestions/{sid}/approve",
        json={
            "expected_suggestion_version": 99,
            "expected_active_claim_id": None,
            "selected_entity_id": "experience-1",
            "idempotency_key": "idem-a-1",
        },
    )
    assert resp.status_code == 409


def test_reject_endpoint(tmp_path):
    client, db, ids = build_client(tmp_path)
    result = seed_suggestion(db, ids)
    sid = result.suggestion_ids[0]

    resp = client.post(
        f"/api/career-twin/suggestions/{sid}/reject",
        json={
            "expected_suggestion_version": 1,
            "reason": "nope",
            "suppression_mode": "NONE",
            "idempotency_key": "idem-r-1",
        },
    )
    assert resp.status_code == 200


def test_idempotency_conflict_returns_409(tmp_path):
    client, db, ids = build_client(tmp_path)
    result = seed_suggestion(db, ids)
    sid = result.suggestion_ids[0]

    payload = {
        "expected_suggestion_version": 1,
        "expected_active_claim_id": None,
        "selected_entity_id": "experience-1",
        "idempotency_key": "idem-shared",
    }
    first = client.post(
        f"/api/career-twin/suggestions/{sid}/approve", json=payload
    )
    assert first.status_code == 200

    conflicting = client.post(
        f"/api/career-twin/suggestions/{sid}/approve",
        json={**payload, "edited_value": "CONTRACT", "expected_suggestion_version": 2},
    )
    assert conflicting.status_code == 409


def test_direct_fact_endpoint(tmp_path):
    client, db, ids = build_client(tmp_path)

    resp = client.post(
        "/api/career-twin/facts",
        json={
            "entity_intent": "EDIT_EXISTING",
            "entity_id": "experience-1",
            "predicate": "EXPERIENCE.EMPLOYMENT_TYPE",
            "value": "PERMANENT",
            "value_type": "TEXT",
            "expected_active_claim_id": None,
            "source_type": "USER_INPUT",
            "evidence_family_id": "fam-1",
            "payload_fingerprint": "pfp-1",
            "idempotency_key": "idem-df-1",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["claim_id"]


def test_error_response_has_no_stack_trace_or_internal_paths(tmp_path):
    client, db, ids = build_client(tmp_path)
    resp = client.get("/api/career-twin/suggestions/nope")
    body = resp.json()
    text = str(body)
    assert "Traceback" not in text
    assert ".py" not in text
    assert "sqlite" not in text.lower()
