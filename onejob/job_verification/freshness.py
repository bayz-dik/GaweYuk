from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class FreshnessState(str, Enum):
    CURRENT = "CURRENT"
    DUE_SOON = "DUE_SOON"
    EXPIRED = "EXPIRED"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FreshnessAssessment:
    state: FreshnessState
    last_authoritative_seen_at: datetime | None
    evaluated_at: datetime
    valid_until: datetime
    reason_codes: tuple[str, ...] = field(default_factory=tuple)


# Default verification validity window. Tier-aware tuning happens in the
# reverification scheduler; the snapshot itself just carries validity.
_DEFAULT_VALID_FOR = timedelta(days=7)


def assess_freshness(
    *,
    last_authoritative_seen_at: datetime | None,
    evaluated_at: datetime,
    explicit_expires_at: datetime | None = None,
    valid_for: timedelta = _DEFAULT_VALID_FOR,
    closed: bool = False,
) -> FreshnessAssessment:
    if closed:
        return FreshnessAssessment(
            state=FreshnessState.CLOSED,
            last_authoritative_seen_at=last_authoritative_seen_at,
            evaluated_at=evaluated_at,
            valid_until=evaluated_at,
            reason_codes=("AUTHORITATIVE_CLOSURE",),
        )

    if last_authoritative_seen_at is None:
        return FreshnessAssessment(
            state=FreshnessState.UNKNOWN,
            last_authoritative_seen_at=None,
            evaluated_at=evaluated_at,
            valid_until=evaluated_at + valid_for,
            reason_codes=("NO_AUTHORITATIVE_SIGHTING",),
        )

    valid_until = evaluated_at + valid_for
    if explicit_expires_at is not None and explicit_expires_at < valid_until:
        valid_until = explicit_expires_at

    if valid_until <= evaluated_at:
        return FreshnessAssessment(
            state=FreshnessState.EXPIRED,
            last_authoritative_seen_at=last_authoritative_seen_at,
            evaluated_at=evaluated_at,
            valid_until=valid_until,
            reason_codes=("VERIFICATION_EXPIRED",),
        )

    return FreshnessAssessment(
        state=FreshnessState.CURRENT,
        last_authoritative_seen_at=last_authoritative_seen_at,
        evaluated_at=evaluated_at,
        valid_until=valid_until,
        reason_codes=("FRESH",),
    )
