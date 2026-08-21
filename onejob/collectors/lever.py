from __future__ import annotations

from datetime import datetime, timezone

from onejob.collectors.base import (
    CollectionBatch,
    CollectionStatus,
    CollectionTarget,
)
from onejob.collectors.common import (
    canonical_payload_hash,
    stable_observation_id,
)
from onejob.ingestion.models import RawJobObservation, SourceType
from onejob.job_sources.models import AcquisitionMethod


def _from_milliseconds(value):
    if value is None:
        return None

    return datetime.fromtimestamp(
        value / 1000,
        tz=timezone.utc,
    )


class LeverCollector:
    source_key = "lever"
    source_type = SourceType.ATS
    collector_version = "1"
    acquisition_method = AcquisitionMethod.OFFICIAL_API

    def __init__(self, http_client):
        self.http_client = http_client

    def collect(
        self,
        target: CollectionTarget,
    ) -> CollectionBatch:
        started_at = datetime.now(timezone.utc)

        url = (
            "https://api.lever.co/v0/postings/"
            f"{target.tenant}?mode=json"
        )

        response = self.http_client.get(url)
        response.raise_for_status()

        payload = response.json()
        observations: list[RawJobObservation] = []
        warnings: list[str] = []

        for item in payload:
            raw_id = item.get("id")
            title = item.get("text")

            if raw_id is None or not str(title or "").strip():
                identifier = (
                    str(raw_id)
                    if raw_id is not None
                    else "unknown"
                )
                warnings.append(
                    f"skipped lever entry id={identifier}: "
                    "missing required id/title"
                )
                continue

            external_id = str(raw_id)
            source_payload_hash = canonical_payload_hash(item)

            categories = item.get("categories") or {}
            content = item.get("content") or {}

            observations.append(
                RawJobObservation(
                    observation_id=stable_observation_id(
                        self.source_key,
                        external_id,
                        source_payload_hash,
                    ),
                    source_key=self.source_key,
                    source_type=self.source_type,
                    collector_version=self.collector_version,
                    external_id=external_id,
                    source_url=item["hostedUrl"],
                    apply_url=item.get("applyUrl") or item.get("hostedUrl"),
                    observed_at=datetime.now(timezone.utc),
                    updated_at=_from_milliseconds(
                        item.get("updatedAt")
                    ),
                    title=str(title),
                    company_name=target.tenant.replace(
                        "-",
                        " ",
                    ).title(),
                    location_text=categories.get(
                        "location",
                        "",
                    ),
                    description=content.get(
                        "description",
                        "",
                    ),
                    employment_type=categories.get(
                        "commitment"
                    ),
                    source_payload_hash=source_payload_hash,
                )
            )

        finished_at = datetime.now(timezone.utc)

        return CollectionBatch(
            source_key=self.source_key,
            source_type=self.source_type,
            collector_version=self.collector_version,
            target=target,
            started_at=started_at,
            finished_at=finished_at,
            status=(
                CollectionStatus.PARTIAL
                if warnings
                else CollectionStatus.SUCCESS
            ),
            observations=observations,
            warnings=warnings,
        )
