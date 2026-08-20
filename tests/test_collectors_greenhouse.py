import json
from pathlib import Path

from onejob.collectors.base import CollectionTarget
from onejob.collectors.greenhouse import GreenhouseCollector


class FixtureResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class FixtureClient:
    def __init__(self, payload):
        self.payload = payload

    def get(self, *args, **kwargs):
        return FixtureResponse(self.payload)


def test_greenhouse_maps_payload_to_universal_observation():
    payload = json.loads(
        Path("tests/fixtures/greenhouse_jobs.json").read_text()
    )

    batch = GreenhouseCollector(
        FixtureClient(payload)
    ).collect(
        CollectionTarget(tenant="example")
    )

    assert batch.status.value == "SUCCESS"
    assert len(batch.observations) == 1

    job = batch.observations[0]

    assert job.source_type.value == "ats"
    assert job.external_id == "1001"
    assert job.company_name == "Example"
    assert job.title == "Production Operator"
    assert job.location_text == "Bekasi, Indonesia"
    assert job.description == "Operate production machines safely."
    assert job.source_url == (
        "https://boards.greenhouse.io/example/jobs/1001"
    )

    assert len(job.source_payload_hash) == 64
    assert len(job.observation_id) == 64


def test_greenhouse_skips_malformed_entry_and_keeps_valid_jobs():
    payload = {
        "jobs": [
            {
                "id": 1001,
                "title": "Production Operator",
                "absolute_url": "https://boards.greenhouse.io/example/jobs/1001",
                "updated_at": "2026-08-20T08:30:00Z",
                "location": {"name": "Bekasi, Indonesia"},
                "content": "<p>Operate production machines safely.</p>",
            },
            {
                "id": 1002,
                # title intentionally missing
                "absolute_url": "https://boards.greenhouse.io/example/jobs/1002",
                "content": "<script>secret-html</script>",
            },
        ]
    }

    batch = GreenhouseCollector(
        FixtureClient(payload)
    ).collect(
        CollectionTarget(tenant="example")
    )

    assert batch.status.value == "PARTIAL"
    assert len(batch.observations) == 1
    assert batch.observations[0].external_id == "1001"

    assert len(batch.warnings) == 1
    warning = batch.warnings[0].lower()

    assert "1002" in warning
    assert "skipped" in warning
    assert "secret-html" not in warning
    assert "<script>" not in warning
