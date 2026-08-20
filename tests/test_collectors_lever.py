import json
from pathlib import Path

from onejob.collectors.base import CollectionTarget
from onejob.collectors.lever import LeverCollector


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


def test_lever_maps_payload_to_universal_observation():
    payload = json.loads(
        Path("tests/fixtures/lever_jobs.json").read_text()
    )

    batch = LeverCollector(
        FixtureClient(payload)
    ).collect(
        CollectionTarget(tenant="example")
    )

    assert batch.status.value == "SUCCESS"
    assert len(batch.observations) == 1

    job = batch.observations[0]

    assert job.source_type.value == "ats"
    assert job.external_id == "lever-1001"
    assert job.company_name == "Example"
    assert job.title == "Production Operator"
    assert job.location_text == "Bekasi, Indonesia"
    assert job.description == "Operate production machines safely."
    assert job.employment_type == "Full-time"
    assert job.source_url == (
        "https://jobs.lever.co/example/lever-1001"
    )

    assert len(job.source_payload_hash) == 64
    assert len(job.observation_id) == 64


def test_lever_skips_malformed_entry_and_keeps_valid_jobs():
    payload = [
        {
            "id": "lever-1001",
            "text": "Production Operator",
            "hostedUrl": "https://jobs.lever.co/example/lever-1001",
            "categories": {
                "location": "Bekasi, Indonesia",
                "commitment": "Full-time",
            },
            "content": {
                "description": "Operate production machines safely.",
            },
        },
        {
            "id": "lever-1002",
            # text/title intentionally missing
            "hostedUrl": "https://jobs.lever.co/example/lever-1002",
            "content": {
                "descriptionHtml": "<script>secret-lever-html</script>",
            },
        },
    ]

    batch = LeverCollector(
        FixtureClient(payload)
    ).collect(
        CollectionTarget(tenant="example")
    )

    assert batch.status.value == "PARTIAL"
    assert len(batch.observations) == 1
    assert batch.observations[0].external_id == "lever-1001"

    assert len(batch.warnings) == 1

    warning = batch.warnings[0].lower()

    assert "lever-1002" in warning
    assert "skipped" in warning
    assert "secret-lever-html" not in warning
    assert "<script>" not in warning
