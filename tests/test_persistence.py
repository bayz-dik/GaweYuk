from datetime import datetime, timezone

from onejob.ingestion.models import RawJobObservation, SourceType
from onejob.persistence.db import Database
from onejob.persistence.repositories import ObservationRepository


def observation():
    return RawJobObservation(
        observation_id="obs-1",
        source_key="fixture",
        source_type=SourceType.ATS,
        collector_version="v1",
        external_id="job-1",
        source_url="https://example.test/1",
        observed_at=datetime.now(timezone.utc),
        title="Operator",
        company_name="PT Example",
        location_text="Bekasi",
        description="Operate machines",
        source_payload_hash="hash-1",
    )


def test_observation_repository_is_idempotent_by_observation_id(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    repo = ObservationRepository()

    with db.transaction() as conn:
        assert repo.insert(conn, observation()) is True
        assert repo.insert(conn, observation()) is False

    with db.connection() as conn:
        rows = repo.list_by_source(conn, "fixture")

    assert [row.observation_id for row in rows] == ["obs-1"]
