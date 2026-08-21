from __future__ import annotations

from enum import Enum

from onejob.job_sources.models import SourceHealthState


class SourceHealthSignal(str, Enum):
    SUCCESS = "SUCCESS"
    TRANSIENT_FAILURE = "TRANSIENT_FAILURE"
    RATE_LIMIT = "RATE_LIMIT"
    AUTH_FAILURE = "AUTH_FAILURE"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    POLICY_VIOLATION = "POLICY_VIOLATION"


# Number of consecutive transient failures that trips the breaker to DEGRADED.
_DEGRADE_THRESHOLD = 3


class SourceHealthEvaluator:
    """Circuit-breaker health transitions.

    Health never mutates compliance status; it only affects source authority
    and scheduling. A single success clears a transient/rate-limited state so a
    recovered source is not permanently penalized.
    """

    def evaluate(
        self,
        current: SourceHealthState,
        signal: SourceHealthSignal,
        *,
        consecutive_transient_failures: int = 0,
    ) -> SourceHealthState:
        if signal is SourceHealthSignal.POLICY_VIOLATION:
            return SourceHealthState.POLICY_BLOCKED
        if signal is SourceHealthSignal.SCHEMA_MISMATCH:
            return SourceHealthState.SCHEMA_CHANGED
        if signal is SourceHealthSignal.RATE_LIMIT:
            return SourceHealthState.RATE_LIMITED
        if signal is SourceHealthSignal.AUTH_FAILURE:
            return SourceHealthState.AUTH_REQUIRED
        if signal is SourceHealthSignal.TRANSIENT_FAILURE:
            if consecutive_transient_failures + 1 >= _DEGRADE_THRESHOLD:
                return SourceHealthState.DEGRADED
            return current if current is not SourceHealthState.UNKNOWN else SourceHealthState.DEGRADED
        # SUCCESS: recover from transient/rate-limited/unknown to healthy.
        if current in (
            SourceHealthState.RATE_LIMITED,
            SourceHealthState.DEGRADED,
            SourceHealthState.UNKNOWN,
            SourceHealthState.HEALTHY,
        ):
            return SourceHealthState.HEALTHY
        # AUTH_REQUIRED / SCHEMA_CHANGED / POLICY_BLOCKED require explicit
        # operator remediation, not a single successful poll.
        return current
