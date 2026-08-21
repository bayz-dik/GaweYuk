from datetime import datetime, timezone

from onejob.collectors.base import Collector, CollectionTarget
from onejob.ingestion.models import RawJobObservation, SourceType


class FixtureCollector:
    source_key = "fixture"
    source_type = SourceType.ATS
    collector_version = "test-1"

    def collect(self, target: CollectionTarget):
        from onejob.collectors.base import CollectionBatch, CollectionStatus

        return CollectionBatch(
            source_key=self.source_key,
            source_type=self.source_type,
            collector_version=self.collector_version,
            target=target,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            status=CollectionStatus.SUCCESS,
            observations=[
                RawJobObservation(
                    observation_id="obs-1",
                    source_key="fixture",
                    source_type=SourceType.ATS,
                    collector_version="test-1",
                    external_id="job-1",
                    source_url="https://example.test/jobs/1",
                    observed_at=datetime.now(timezone.utc),
                    title="Production Operator",
                    company_name="PT Example",
                    location_text="Bekasi",
                    description="Operate production machinery.",
                    source_payload_hash="abc123",
                )
            ],
        )


def test_collector_contract_returns_immutable_observations():
    collector: Collector = FixtureCollector()

    batch = collector.collect(CollectionTarget(tenant="example"))

    assert batch.source_key == "fixture"
    assert batch.observations[0].external_id == "job-1"
    assert batch.observations[0].model_config["frozen"] is True


def test_collector_health_status_exposes_required_states():
    from onejob.collectors.base import CollectorHealthStatus

    assert {status.value for status in CollectorHealthStatus} == {
        "HEALTHY",
        "DEGRADED",
        "RATE_LIMITED",
        "BROKEN",
        "DISABLED",
        "UNKNOWN",
    }


# ---------------------------------------------------------------------------
# Task 3: shared adapter contract across all real ATS collectors
# ---------------------------------------------------------------------------

import json
from pathlib import Path

import pytest

from onejob.collectors.ashby import AshbyCollector
from onejob.collectors.greenhouse import GreenhouseCollector
from onejob.collectors.lever import LeverCollector
from onejob.job_sources.models import AcquisitionMethod


class _FixtureResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _FixtureClient:
    def __init__(self, payload):
        self.payload = payload

    def get(self, *args, **kwargs):
        return _FixtureResponse(self.payload)


def _load(name):
    return json.loads(Path(f"tests/fixtures/{name}").read_text())


_ADAPTERS = [
    (GreenhouseCollector, "greenhouse_jobs.json"),
    (LeverCollector, "lever_jobs.json"),
    (AshbyCollector, "ashby_jobs.json"),
]


def assert_observation_contract(observation):
    assert observation.observation_id
    assert observation.source_key
    assert observation.external_id
    assert observation.source_url.startswith(("http://", "https://"))
    assert observation.title.strip()
    assert observation.company_name.strip()
    assert observation.source_payload_hash
    assert observation.observed_at.tzinfo is not None


@pytest.mark.parametrize("collector_cls,fixture", _ADAPTERS)
def test_adapter_observation_contract(collector_cls, fixture):
    batch = collector_cls(_FixtureClient(_load(fixture))).collect(
        CollectionTarget(tenant="example")
    )
    assert batch.observations
    for observation in batch.observations:
        assert_observation_contract(observation)
        assert observation.apply_url is None or observation.apply_url.startswith(
            ("http://", "https://")
        )


@pytest.mark.parametrize("collector_cls,fixture", _ADAPTERS)
def test_adapter_declares_official_api_acquisition(collector_cls, fixture):
    collector = collector_cls(_FixtureClient(_load(fixture)))
    assert collector.acquisition_method is AcquisitionMethod.OFFICIAL_API


@pytest.mark.parametrize("collector_cls,fixture", _ADAPTERS)
def test_adapter_does_not_expose_trust_or_publication_fields(collector_cls, fixture):
    batch = collector_cls(_FixtureClient(_load(fixture))).collect(
        CollectionTarget(tenant="example")
    )
    observation = batch.observations[0]
    fields = set(observation.model_dump().keys())
    # Adapters observe only. They must never assert trust or publication.
    assert not (fields & {"verified", "trusted", "publication_state", "trust_score"})


@pytest.mark.parametrize("collector_cls,fixture", _ADAPTERS)
def test_adapter_parsing_is_deterministic(collector_cls, fixture):
    payload = _load(fixture)
    first = collector_cls(_FixtureClient(payload)).collect(
        CollectionTarget(tenant="example")
    )
    second = collector_cls(_FixtureClient(payload)).collect(
        CollectionTarget(tenant="example")
    )
    assert [o.observation_id for o in first.observations] == [
        o.observation_id for o in second.observations
    ]


def test_ashby_captures_apply_url():
    batch = AshbyCollector(_FixtureClient(_load("ashby_jobs.json"))).collect(
        CollectionTarget(tenant="example")
    )
    job = batch.observations[0]
    assert job.apply_url == (
        "https://jobs.ashbyhq.com/example/ashby-1001/application"
    )
