from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel

from onejob.ingestion.models import RawJobObservation
from onejob.provenance.lineage import evidence_family_for


class EvidenceRecord(BaseModel):
    evidence_id: str
    canonical_job_id: str
    observation_id: str
    field_name: str
    value: Any
    value_fingerprint: str
    evidence_family_id: str
    independence_status: str
    observed_at: object
    confidence: float


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha1(encoded.encode()).hexdigest()


def _evidence_id(
    observation_id: str,
    field_name: str,
    value: Any,
) -> str:
    raw = f"{observation_id}|{field_name}|{_fingerprint(value)}"
    return "ev-" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def build_field_evidence(
    canonical_job_id: str,
    observations: list[RawJobObservation],
    upstream_family: dict[str, str] | None = None,
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []

    for observation in observations:
        family = evidence_family_for(
            observation.source_key,
            upstream_family,
        )

        independence_status = (
            "derived"
            if upstream_family and observation.source_key in upstream_family
            else "independent"
        )

        salary = None
        if (
            observation.salary_min is not None
            or observation.salary_max is not None
        ):
            salary = [
                observation.salary_min,
                observation.salary_max,
            ]

        fields = {
            "title": observation.title,
            "company": observation.company_name,
            "location": observation.location_text,
            "description": observation.description,
            "salary": salary,
            "published_at": observation.published_at,
            "active_status": True,
        }

        for field_name, value in fields.items():
            records.append(
                EvidenceRecord(
                    evidence_id=_evidence_id(
                        observation.observation_id,
                        field_name,
                        value,
                    ),
                    canonical_job_id=canonical_job_id,
                    observation_id=observation.observation_id,
                    field_name=field_name,
                    value=value,
                    value_fingerprint=_fingerprint(value),
                    evidence_family_id=family,
                    independence_status=independence_status,
                    observed_at=observation.observed_at,
                    confidence=0.90,
                )
            )

    return records
