import json
from pathlib import Path

from onejob.collectors.base import CollectionTarget
from onejob.collectors.ashby import AshbyCollector


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


def test_ashby_maps_payload_to_universal_observation():
    payload = json.loads(
        Path("tests/fixtures/ashby_jobs.json").read_text()
    )

    batch = AshbyCollector(
        FixtureClient(payload)
    ).collect(
        CollectionTarget(tenant="example")
    )

    assert batch.status.value == "SUCCESS"
    assert len(batch.observations) == 1

    job = batch.observations[0]

    assert job.source_type.value == "ats"
    assert job.external_id == "ashby-1001"
    assert job.company_name == "Example"
    assert job.title == "Production Operator"
    assert job.location_text == "Bekasi, Indonesia"
    assert job.description == "Operate production machines safely."
    assert job.employment_type == "FullTime"
    assert job.source_url == (
        "https://jobs.ashbyhq.com/example/ashby-1001"
    )

    assert len(job.source_payload_hash) == 64
    assert len(job.observation_id) == 64


def test_ashby_skips_malformed_entry_and_keeps_valid_jobs():
    payload = {
        "jobs": [
            {
                "id": "ashby-1001",
                "title": "Production Operator",
                "location": "Bekasi, Indonesia",
                "descriptionPlain": "Operate production machines safely.",
                "publishedAt": "2026-08-20T08:30:00Z",
                "employmentType": "FullTime",
                "jobUrl": "https://jobs.ashbyhq.com/example/ashby-1001",
            },
            {
                "id": "ashby-1002",
                # title intentionally missing
                "jobUrl": "https://jobs.ashbyhq.com/example/ashby-1002",
                "descriptionHtml": "<script>secret-ashby-html</script>",
            },
        ]
    }

    batch = AshbyCollector(
        FixtureClient(payload)
    ).collect(
        CollectionTarget(tenant="example")
    )

    assert batch.status.value == "PARTIAL"
    assert len(batch.observations) == 1
    assert batch.observations[0].external_id == "ashby-1001"

    assert len(batch.warnings) == 1

    warning = batch.warnings[0].lower()

    assert "ashby-1002" in warning
    assert "skipped" in warning
    assert "secret-ashby-html" not in warning
    assert "<script>" not in warning
