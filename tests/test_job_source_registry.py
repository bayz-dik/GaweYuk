from datetime import datetime, timezone

import pytest

from onejob.ingestion.models import SourceType
from onejob.job_sources.models import (
    AcquisitionMethod,
    ComplianceStatus,
    JobSource,
    SourceHealthState,
    SourceRolloutState,
    SourceTrustTier,
)


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


def _source(**overrides):
    base = dict(
        source_id="src-greenhouse",
        source_key="greenhouse",
        source_type=SourceType.ATS,
        trust_tier=SourceTrustTier.TIER_1_OFFICIAL,
        acquisition_method=AcquisitionMethod.OFFICIAL_API,
        primary_domain="greenhouse.io",
        country_scope=(),
        compliance_status=ComplianceStatus.ALLOWED,
        rollout_state=SourceRolloutState.SHADOW,
        health_state=SourceHealthState.UNKNOWN,
        verification_policy_version="source-policy-v1",
        created_at=NOW,
        updated_at=NOW,
    )
    base.update(overrides)
    return JobSource(**base)


def test_job_source_has_explicit_policy_and_rollout_state():
    source = _source()
    assert source.rollout_state is SourceRolloutState.SHADOW
    assert source.country_scope == ()


def test_job_source_rejects_active_when_compliance_is_unknown():
    with pytest.raises(ValueError, match="compliance"):
        _source(
            source_id="src-bad",
            source_key="bad",
            source_type=SourceType.OPEN_WEB,
            trust_tier=SourceTrustTier.TIER_3_DISCOVERY,
            acquisition_method=AcquisitionMethod.PERMITTED_HTML,
            primary_domain="example.test",
            country_scope=("ID",),
            compliance_status=ComplianceStatus.UNKNOWN,
            rollout_state=SourceRolloutState.ACTIVE,
            health_state=SourceHealthState.HEALTHY,
        )


def test_country_scope_is_normalized_and_sorted():
    source = _source(country_scope=("sg", "ID", "id"))
    # deduplicated, uppercased, sorted; no Indonesia hard-code in the type
    assert source.country_scope == ("ID", "SG")


def test_source_repository_round_trips(tmp_path):
    from onejob.job_sources.repository import SourceRepository
    from onejob.persistence.db import Database

    db = Database(tmp_path / "sources.db")
    db.initialize()
    repo = SourceRepository()

    source = _source(country_scope=("ID", "SG"))

    with db.transaction() as conn:
        repo.insert(conn, source)

    with db.connection() as conn:
        loaded = repo.get_by_key(conn, "greenhouse")
        by_id = repo.get_by_id(conn, "src-greenhouse")
        listed = repo.list_all(conn)

    assert loaded == source
    assert by_id == source
    assert listed == [source]


def test_source_repository_missing_returns_none(tmp_path):
    from onejob.job_sources.repository import SourceRepository
    from onejob.persistence.db import Database

    db = Database(tmp_path / "sources.db")
    db.initialize()
    repo = SourceRepository()

    with db.connection() as conn:
        assert repo.get_by_key(conn, "nope") is None
        assert repo.get_by_id(conn, "nope") is None


def test_source_repository_update_state_records_event(tmp_path):
    from onejob.job_sources.repository import SourceRepository
    from onejob.persistence.db import Database

    db = Database(tmp_path / "sources.db")
    db.initialize()
    repo = SourceRepository()

    with db.transaction() as conn:
        repo.insert(conn, _source())

    later = datetime(2026, 8, 22, tzinfo=timezone.utc)
    with db.transaction() as conn:
        updated = repo.update_state(
            conn,
            source_id="src-greenhouse",
            rollout_state=SourceRolloutState.OBSERVED,
            updated_at=later,
        )

    assert updated.rollout_state is SourceRolloutState.OBSERVED
    assert updated.updated_at == later

    with db.connection() as conn:
        reloaded = repo.get_by_id(conn, "src-greenhouse")
    assert reloaded.rollout_state is SourceRolloutState.OBSERVED
