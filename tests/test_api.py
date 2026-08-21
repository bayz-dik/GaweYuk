from fastapi.testclient import TestClient
from onejob.api import app

client = TestClient(app)

def test_health_and_jobs_api():
    assert client.get('/health').json() == {'status':'ok'}
    response = client.get('/api/jobs')
    assert response.status_code == 200
    assert len(response.json()) >= 3


def test_answer_api():
    job_id = client.get('/api/jobs').json()[0]['id']
    response = client.post('/api/answers/suggest', json={'job_id': job_id, 'question':'What is your expected salary?'})
    assert response.status_code == 200
    assert response.json()['confidence'] == 100


def test_career_twin_endpoint_delegates_to_safe_service_view(
    monkeypatch,
):
    from onejob import api as api_module

    class StubService:
        def profile_view(self):
            return {
                "name": "Bayu",
                "skills": ["machine operation"],
            }

        def career_twin_view(self):
            return {
                "twin_id": "twin-1",
                "projection_version": "career-projection-v1",
                "input_fingerprint": "fingerprint-1",
                "entities": {
                    "experience-1": {
                        "EXPERIENCE.ROLE": "role-1",
                    },
                },
                "claims": [
                    {
                        "claim_id": "claim-1",
                        "entity_id": "experience-1",
                        "predicate": "EXPERIENCE.ROLE",
                        "approval_state": "APPROVED",
                        "lifecycle_state": "ACTIVE",
                        "provenance_trust_tier": None,
                        "claim_confidence": None,
                    },
                ],
            }

    monkeypatch.setattr(
        api_module,
        "service",
        StubService(),
    )

    profile = client.get("/api/profile")

    assert profile.status_code == 200
    assert profile.json() == {
        "name": "Bayu",
        "skills": ["machine operation"],
    }

    response = client.get("/api/career-twin")

    assert response.status_code == 200

    body = response.json()

    assert body["twin_id"] == "twin-1"
    assert body["projection_version"] == (
        "career-projection-v1"
    )

    claim = body["claims"][0]

    assert claim["approval_state"] == "APPROVED"
    assert claim["lifecycle_state"] == "ACTIVE"

    # Public endpoint must not leak raw evidence.
    assert "payload_json" not in claim
    assert "raw_evidence" not in claim


def test_real_service_uses_configured_v2_query_and_sanitizes_claims(
    monkeypatch,
):
    from onejob import api as api_module
    from onejob.repository import DemoRepository
    from onejob.service import OneJobService

    class StubV2Query:
        def safe_view(self):
            return {
                "twin_id": "twin-1",
                "projection_version": "career-projection-v1",
                "input_fingerprint": "fingerprint-1",
                "entities": {
                    "experience-1": {
                        "EXPERIENCE.ROLE": "role-1",
                    },
                },
                "claims": [
                    {
                        "claim_id": "claim-1",
                        "entity_id": "experience-1",
                        "predicate": "EXPERIENCE.ROLE",
                        "approval_state": "APPROVED",
                        "lifecycle_state": "ACTIVE",
                        "provenance_trust_tier": "USER_ASSERTED",
                        "claim_confidence": 0.8,

                        # Must never reach public API.
                        "payload_json": '{"secret":"raw"}',
                        "raw_evidence": {
                            "document": "private",
                        },
                    },
                ],
            }

    real_service = OneJobService(
        DemoRepository(),
        career_twin_query=StubV2Query(),
    )

    monkeypatch.setattr(
        api_module,
        "service",
        real_service,
    )

    legacy_profile = client.get("/api/profile")

    assert legacy_profile.status_code == 200
    assert "name" in legacy_profile.json()
    assert "skills" in legacy_profile.json()

    response = client.get("/api/career-twin")

    assert response.status_code == 200

    claim = response.json()["claims"][0]

    assert claim == {
        "claim_id": "claim-1",
        "entity_id": "experience-1",
        "predicate": "EXPERIENCE.ROLE",
        "approval_state": "APPROVED",
        "lifecycle_state": "ACTIVE",
        "provenance_trust_tier": "USER_ASSERTED",
        "claim_confidence": 0.8,
    }

    assert "payload_json" not in claim
    assert "raw_evidence" not in claim


def test_career_twin_endpoint_returns_503_when_v2_is_not_configured(
    monkeypatch,
):
    from fastapi.testclient import TestClient

    from onejob import api as api_module
    from onejob.repository import DemoRepository
    from onejob.service import OneJobService

    monkeypatch.setattr(
        api_module,
        "service",
        OneJobService(DemoRepository()),
    )

    # Disable exception re-raising so we can assert the HTTP contract.
    local_client = TestClient(
        api_module.app,
        raise_server_exceptions=False,
    )

    response = local_client.get("/api/career-twin")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Career Twin v2 is not configured"
    }
