from __future__ import annotations

from datetime import datetime
from enum import IntEnum, StrEnum
import hashlib
import json
from typing import Mapping, Sequence

from .models import (
    DimensionState,
    RecruitmentStage,
)
from .scoring import DimensionInput


class TrustEventType(StrEnum):
    L4_SIGNAL_CHANGED = "L4_SIGNAL_CHANGED"
    L3_SIGNAL_CHANGED = "L3_SIGNAL_CHANGED"

    CREDENTIAL_CRITICAL = "CREDENTIAL_CRITICAL"
    PAYMENT_CRITICAL = "PAYMENT_CRITICAL"
    PRIVACY_CRITICAL = "PRIVACY_CRITICAL"

    COMPANY_IDENTITY_CHANGED = "COMPANY_IDENTITY_CHANGED"
    DOMAIN_CHANGED = "DOMAIN_CHANGED"
    CRITICAL_CONFLICT_OPENED = "CRITICAL_CONFLICT_OPENED"

    NEW_OBSERVATION = "NEW_OBSERVATION"
    CONSENSUS_CHANGED = "CONSENSUS_CHANGED"
    SOURCE_HEALTH_CHANGED = "SOURCE_HEALTH_CHANGED"

    FRESHNESS_DECAY = "FRESHNESS_DECAY"
    POLICY_MIGRATION = "POLICY_MIGRATION"
    MAINTENANCE = "MAINTENANCE"


class RecalcPriority(IntEnum):
    P0_IMMEDIATE = 0
    P1_HIGH = 1
    P2_NORMAL = 2
    P3_BACKGROUND = 3


P0_EVENTS = frozenset(
    {
        TrustEventType.L4_SIGNAL_CHANGED,
        TrustEventType.L3_SIGNAL_CHANGED,
        TrustEventType.CREDENTIAL_CRITICAL,
        TrustEventType.PAYMENT_CRITICAL,
        TrustEventType.PRIVACY_CRITICAL,
    }
)

P1_EVENTS = frozenset(
    {
        TrustEventType.COMPANY_IDENTITY_CHANGED,
        TrustEventType.DOMAIN_CHANGED,
        TrustEventType.CRITICAL_CONFLICT_OPENED,
    }
)

P2_EVENTS = frozenset(
    {
        TrustEventType.NEW_OBSERVATION,
        TrustEventType.CONSENSUS_CHANGED,
        TrustEventType.SOURCE_HEALTH_CHANGED,
    }
)


def priority_for_event(
    event_type: TrustEventType,
) -> RecalcPriority:
    if event_type in P0_EVENTS:
        return RecalcPriority.P0_IMMEDIATE

    if event_type in P1_EVENTS:
        return RecalcPriority.P1_HIGH

    if event_type in P2_EVENTS:
        return RecalcPriority.P2_NORMAL

    return RecalcPriority.P3_BACKGROUND


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def input_fingerprint(
    *,
    canonical_job_id: str,
    recruitment_stage: RecruitmentStage,
    policy_version: str,
    evidence_refs: Sequence[str],
    active_signal_ids: Sequence[str],
    source_health: Mapping[str, str],
) -> str:
    payload = {
        "canonical_job_id": canonical_job_id,
        "recruitment_stage": recruitment_stage.value,
        "policy_version": policy_version,
        "evidence_refs": sorted(set(evidence_refs)),
        "active_signal_ids": sorted(
            set(active_signal_ids)
        ),
        "source_health": {
            key: source_health[key]
            for key in sorted(source_health)
        },
    }

    encoded = _canonical_json(payload).encode(
        "utf-8"
    )

    return hashlib.sha256(encoded).hexdigest()


def should_recalculate(
    *,
    previous_input_fingerprint: str | None,
    new_input_fingerprint: str,
) -> bool:
    if previous_input_fingerprint is None:
        return True

    return (
        previous_input_fingerprint
        != new_input_fingerprint
    )


def is_evaluation_fresh(
    *,
    evaluated_at: datetime,
    valid_until: datetime | None,
    now: datetime,
    evaluation_policy_version: str,
    current_policy_version: str,
) -> bool:
    if (
        evaluation_policy_version
        != current_policy_version
    ):
        return False

    if valid_until is None:
        return False

    if now < evaluated_at:
        return False

    return now < valid_until


def failure_dimension_input(
    *,
    reason: str,
) -> DimensionInput:
    return DimensionInput(
        state=DimensionState.UNKNOWN,
        score=None,
        confidence=None,
        reason_codes=(reason,),
        evidence_refs=(),
    )


SOURCE_HEALTH_CONFIDENCE_MULTIPLIERS = {
    "HEALTHY": 1.0,
    "PARTIAL": 0.80,
    "DEGRADED": 0.70,
    "RATE_LIMITED": 0.60,
    "BROKEN": 0.35,
    "UNKNOWN": 0.50,
}


def source_health_confidence_multiplier(
    status: str,
) -> float:
    normalized = status.upper()

    return SOURCE_HEALTH_CONFIDENCE_MULTIPLIERS.get(
        normalized,
        SOURCE_HEALTH_CONFIDENCE_MULTIPLIERS[
            "UNKNOWN"
        ],
    )


def source_health_creates_scam_signal(
    status: str,
) -> bool:
    # Reliability failure is uncertainty,
    # not evidence of maliciousness.
    return False
