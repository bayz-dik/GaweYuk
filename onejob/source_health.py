from __future__ import annotations

from onejob.collectors.base import (
    CollectionStatus,
    CollectorHealthStatus,
)

SourceHealthStatus = CollectorHealthStatus


def transition_source_health(
    current: SourceHealthStatus,
    collection_status: CollectionStatus,
    consecutive_failures: int,
) -> tuple[SourceHealthStatus, int]:
    if collection_status == CollectionStatus.SUCCESS:
        return SourceHealthStatus.HEALTHY, 0

    if collection_status == CollectionStatus.PARTIAL:
        return SourceHealthStatus.DEGRADED, consecutive_failures

    if collection_status == CollectionStatus.RATE_LIMITED:
        return SourceHealthStatus.RATE_LIMITED, consecutive_failures

    if collection_status == CollectionStatus.FAILED:
        failures = consecutive_failures + 1

        if failures >= 3:
            return SourceHealthStatus.BROKEN, failures

        return SourceHealthStatus.DEGRADED, failures

    return current, consecutive_failures
