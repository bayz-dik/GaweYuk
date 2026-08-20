import json
from pathlib import Path

import pytest

from onejob.collectors.base import CollectionTarget
from onejob.collectors.greenhouse import GreenhouseCollector
from onejob.collectors.lever import LeverCollector
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


@pytest.mark.parametrize(
    ("collector_cls", "fixture_name"),
    [
        (GreenhouseCollector, "greenhouse_jobs.json"),
        (LeverCollector, "lever_jobs.json"),
        (AshbyCollector, "ashby_jobs.json"),
    ],
)
def test_same_payload_produces_stable_hash_and_observation_id(
    collector_cls,
    fixture_name,
):
    payload = json.loads(
        Path("tests/fixtures", fixture_name).read_text()
    )

    target = CollectionTarget(tenant="example")

    first = collector_cls(
        FixtureClient(payload)
    ).collect(target).observations[0]

    second = collector_cls(
        FixtureClient(payload)
    ).collect(target).observations[0]

    assert first.source_payload_hash == second.source_payload_hash
    assert first.observation_id == second.observation_id

    assert len(first.source_payload_hash) == 64
    assert len(first.observation_id) == 64
