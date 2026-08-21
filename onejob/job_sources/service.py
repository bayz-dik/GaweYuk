from __future__ import annotations

from datetime import datetime

from onejob.ingestion.models import SourceType
from onejob.job_sources.models import (
    AcquisitionMethod,
    ComplianceStatus,
    JobSource,
    SourceHealthState,
    SourceRolloutState,
    SourceTrustTier,
)
from onejob.job_sources.repository import SourceRepository
from onejob.persistence.db import Database


class InvalidSourceTransition(RuntimeError):
    pass


class StaleSourceState(RuntimeError):
    pass


# Allowed rollout edges. No REGISTERED -> ACTIVE shortcut; a source must earn
# authority through SHADOW/OBSERVED/VALIDATED first (spec 4.8).
ALLOWED_ROLLOUT_TRANSITIONS: dict[SourceRolloutState, set[SourceRolloutState]] = {
    SourceRolloutState.REGISTERED: {SourceRolloutState.SHADOW},
    SourceRolloutState.SHADOW: {
        SourceRolloutState.OBSERVED,
        SourceRolloutState.DISABLED,
        SourceRolloutState.POLICY_BLOCKED,
    },
    SourceRolloutState.OBSERVED: {
        SourceRolloutState.VALIDATED,
        SourceRolloutState.SHADOW,
        SourceRolloutState.DISABLED,
    },
    SourceRolloutState.VALIDATED: {
        SourceRolloutState.ACTIVE,
        SourceRolloutState.SHADOW,
        SourceRolloutState.DISABLED,
    },
    SourceRolloutState.ACTIVE: {
        SourceRolloutState.DEGRADED,
        SourceRolloutState.SHADOW,
        SourceRolloutState.DISABLED,
        SourceRolloutState.POLICY_BLOCKED,
    },
    SourceRolloutState.DEGRADED: {
        SourceRolloutState.SHADOW,
        SourceRolloutState.ACTIVE,
        SourceRolloutState.DISABLED,
    },
    SourceRolloutState.DISABLED: {SourceRolloutState.SHADOW},
    SourceRolloutState.POLICY_BLOCKED: set(),
}


class JobSourceService:
    def __init__(self, db: Database, *, repository: SourceRepository | None = None):
        self.db = db
        self.repo = repository or SourceRepository()

    def register(
        self,
        *,
        source_id: str,
        source_key: str,
        source_type: SourceType,
        trust_tier: SourceTrustTier,
        acquisition_method: AcquisitionMethod,
        primary_domain: str | None,
        country_scope: tuple[str, ...],
        compliance_status: ComplianceStatus,
        verification_policy_version: str,
        now: datetime,
    ) -> JobSource:
        source = JobSource(
            source_id=source_id,
            source_key=source_key,
            source_type=source_type,
            trust_tier=trust_tier,
            acquisition_method=acquisition_method,
            primary_domain=primary_domain,
            country_scope=country_scope,
            compliance_status=compliance_status,
            rollout_state=SourceRolloutState.REGISTERED,
            health_state=SourceHealthState.UNKNOWN,
            verification_policy_version=verification_policy_version,
            created_at=now,
            updated_at=now,
        )
        with self.db.transaction() as conn:
            self.repo.insert(conn, source)
        return source

    def promote(
        self,
        *,
        source_id: str,
        expected_state: SourceRolloutState,
        target_state: SourceRolloutState,
        reason_code: str,
        now: datetime,
    ) -> JobSource:
        with self.db.transaction() as conn:
            current = self.repo.get_by_id(conn, source_id)
            if current is None:
                raise LookupError(f"job source not found: {source_id}")
            if current.rollout_state is not expected_state:
                raise StaleSourceState(
                    "stale source rollout state: "
                    f"expected={expected_state.value} "
                    f"actual={current.rollout_state.value}"
                )
            allowed = ALLOWED_ROLLOUT_TRANSITIONS.get(current.rollout_state, set())
            if target_state not in allowed:
                raise InvalidSourceTransition(
                    f"{current.rollout_state.value} -> {target_state.value} "
                    "is not an allowed rollout transition"
                )
            return self.repo.update_state(
                conn,
                source_id=source_id,
                rollout_state=target_state,
                updated_at=now,
                reason_code=reason_code,
            )

    def record_health(
        self,
        *,
        source_id: str,
        health_state: SourceHealthState,
        reason_code: str,
        now: datetime,
    ) -> JobSource:
        with self.db.transaction() as conn:
            current = self.repo.get_by_id(conn, source_id)
            if current is None:
                raise LookupError(f"job source not found: {source_id}")
            return self.repo.update_state(
                conn,
                source_id=source_id,
                health_state=health_state,
                updated_at=now,
                reason_code=reason_code,
            )
