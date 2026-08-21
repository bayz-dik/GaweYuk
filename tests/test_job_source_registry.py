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


# ---------------------------------------------------------------------------
# Task 2: policy, rollout state machine, health circuit breaker
# ---------------------------------------------------------------------------

from onejob.persistence.db import Database


def _registered_source_service(tmp_path):
    from onejob.job_sources.service import JobSourceService

    db = Database(tmp_path / "svc.db")
    db.initialize()
    service = JobSourceService(db)
    source = service.register(
        source_id="src-x",
        source_key="x",
        source_type=SourceType.ATS,
        trust_tier=SourceTrustTier.TIER_1_OFFICIAL,
        acquisition_method=AcquisitionMethod.OFFICIAL_API,
        primary_domain="x.example",
        country_scope=("ID",),
        compliance_status=ComplianceStatus.ALLOWED,
        verification_policy_version="source-policy-v1",
        now=NOW,
    )
    return service, source


def test_register_starts_in_registered_state(tmp_path):
    service, source = _registered_source_service(tmp_path)
    assert source.rollout_state is SourceRolloutState.REGISTERED


def test_new_source_cannot_skip_shadow(tmp_path):
    from onejob.job_sources.service import InvalidSourceTransition

    service, source = _registered_source_service(tmp_path)

    with pytest.raises(InvalidSourceTransition):
        service.promote(
            source_id=source.source_id,
            expected_state=SourceRolloutState.REGISTERED,
            target_state=SourceRolloutState.ACTIVE,
            reason_code="manual_skip",
            now=NOW,
        )


def test_promote_registered_to_shadow(tmp_path):
    service, source = _registered_source_service(tmp_path)
    updated = service.promote(
        source_id=source.source_id,
        expected_state=SourceRolloutState.REGISTERED,
        target_state=SourceRolloutState.SHADOW,
        reason_code="begin_shadow",
        now=NOW,
    )
    assert updated.rollout_state is SourceRolloutState.SHADOW


def test_promote_with_stale_expected_state_raises(tmp_path):
    from onejob.job_sources.service import StaleSourceState

    service, source = _registered_source_service(tmp_path)
    service.promote(
        source_id=source.source_id,
        expected_state=SourceRolloutState.REGISTERED,
        target_state=SourceRolloutState.SHADOW,
        reason_code="begin_shadow",
        now=NOW,
    )
    with pytest.raises(StaleSourceState):
        service.promote(
            source_id=source.source_id,
            expected_state=SourceRolloutState.REGISTERED,
            target_state=SourceRolloutState.OBSERVED,
            reason_code="stale",
            now=NOW,
        )


def test_policy_blocked_source_is_never_collection_eligible():
    from onejob.job_sources.policy import SourcePolicy

    blocked = _source(
        compliance_status=ComplianceStatus.POLICY_BLOCKED,
        rollout_state=SourceRolloutState.POLICY_BLOCKED,
    )
    decision = SourcePolicy().evaluate(blocked)
    assert decision.collection_allowed is False
    assert decision.publication_evidence_allowed is False


def test_active_tier1_allows_publication_evidence():
    from onejob.job_sources.policy import SourcePolicy

    active = _source(rollout_state=SourceRolloutState.ACTIVE)
    decision = SourcePolicy().evaluate(active)
    assert decision.collection_allowed is True
    assert decision.publication_evidence_allowed is True


def test_tier3_shadow_may_collect_but_not_authorize_publication():
    from onejob.job_sources.policy import SourcePolicy

    tier3 = _source(
        trust_tier=SourceTrustTier.TIER_3_DISCOVERY,
        rollout_state=SourceRolloutState.SHADOW,
        acquisition_method=AcquisitionMethod.PERMITTED_HTML,
    )
    decision = SourcePolicy().evaluate(tier3)
    assert decision.collection_allowed is True
    assert decision.publication_evidence_allowed is False


def test_health_policy_violation_blocks_source():
    from onejob.job_sources.health import (
        SourceHealthEvaluator,
        SourceHealthSignal,
    )

    result = SourceHealthEvaluator().evaluate(
        SourceHealthState.HEALTHY, SourceHealthSignal.POLICY_VIOLATION
    )
    assert result is SourceHealthState.POLICY_BLOCKED


def test_health_schema_mismatch_marks_schema_changed():
    from onejob.job_sources.health import (
        SourceHealthEvaluator,
        SourceHealthSignal,
    )

    result = SourceHealthEvaluator().evaluate(
        SourceHealthState.HEALTHY, SourceHealthSignal.SCHEMA_MISMATCH
    )
    assert result is SourceHealthState.SCHEMA_CHANGED


def test_health_rate_limit_then_success_recovers():
    from onejob.job_sources.health import (
        SourceHealthEvaluator,
        SourceHealthSignal,
    )

    evaluator = SourceHealthEvaluator()
    limited = evaluator.evaluate(
        SourceHealthState.HEALTHY, SourceHealthSignal.RATE_LIMIT
    )
    assert limited is SourceHealthState.RATE_LIMITED
    recovered = evaluator.evaluate(limited, SourceHealthSignal.SUCCESS)
    assert recovered is SourceHealthState.HEALTHY
