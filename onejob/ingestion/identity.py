from __future__ import annotations

import hashlib

from onejob.normalization import _clean, _company


def _digest(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode()).hexdigest()[:16]
    return f"{prefix}-{digest}"


def company_id_for(display_name: str) -> str:
    normalized = _company(display_name)
    return _digest("cmp", normalized)


def job_identity_key(
    company_id: str,
    normalized_title: str,
    normalized_location: str,
) -> str:
    title = _clean(normalized_title)
    location = _clean(normalized_location)
    return _digest("job", f"{company_id}|{title}|{location}")


def _similarity(left: str | None, right: str | None) -> float:
    from difflib import SequenceMatcher

    a = _clean(left or "")
    b = _clean(right or "")

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    return SequenceMatcher(None, a, b).ratio()


def identity_score(left: dict, right: dict) -> float:
    left_source = left.get("source_key")
    right_source = right.get("source_key")
    left_external = left.get("external_id")
    right_external = right.get("external_id")

    if (
        left_source
        and right_source
        and left_source == right_source
        and left_external
        and right_external
        and left_external == right_external
    ):
        return 1.0

    company_score = _similarity(
        _company(left.get("company", "")),
        _company(right.get("company", "")),
    )
    title_score = _similarity(
        left.get("title"),
        right.get("title"),
    )
    location_score = _similarity(
        left.get("location"),
        right.get("location"),
    )
    description_score = _similarity(
        left.get("description"),
        right.get("description"),
    )

    score = (
        company_score * 0.35
        + title_score * 0.30
        + location_score * 0.20
        + description_score * 0.15
    )

    return round(max(0.0, min(1.0, score)), 6)

