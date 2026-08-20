from __future__ import annotations

from typing import Any

from onejob.ingestion.models import JobLifecycleState


def diff_material_fields(
    old: dict[str, Any],
    new: dict[str, Any],
) -> list[str]:
    keys = set(old) | set(new)

    return sorted(
        key
        for key in keys
        if old.get(key) != new.get(key)
    )


def next_lifecycle_state(
    current: JobLifecycleState,
    *,
    observed_now: bool,
    materially_changed: bool,
) -> JobLifecycleState:
    if (
        current == JobLifecycleState.CLOSED
        and observed_now
    ):
        return JobLifecycleState.REOPENED

    if (
        current == JobLifecycleState.ACTIVE
        and not observed_now
    ):
        return JobLifecycleState.STALE

    if (
        current == JobLifecycleState.ACTIVE
        and materially_changed
    ):
        return JobLifecycleState.UPDATED

    if (
        current == JobLifecycleState.ACTIVE
        and observed_now
    ):
        return JobLifecycleState.ACTIVE

    return current


MATERIAL_JOB_FIELDS = (
    "title",
    "company_name",
    "location_text",
    "description",
    "salary_min",
    "salary_max",
    "currency",
    "employment_type",
    "contact_email",
)


def material_snapshot(job: dict[str, Any]) -> dict[str, Any]:
    return {
        field: job.get(field)
        for field in MATERIAL_JOB_FIELDS
    }
