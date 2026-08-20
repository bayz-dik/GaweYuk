from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser

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


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str):
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts)


def _strip_html(value: str | None) -> str:
    if not value:
        return ""

    parser = _TextExtractor()
    parser.feed(value)
    return parser.text()


def _parse_datetime(value: str | None):
    if not value:
        return None

    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


class GreenhouseCollector:
    source_key = "greenhouse"
    source_type = SourceType.ATS
    collector_version = "1"

    def __init__(self, http_client):
        self.http_client = http_client

    def collect(
        self,
        target: CollectionTarget,
    ) -> CollectionBatch:
        started_at = datetime.now(timezone.utc)

        url = (
            "https://boards-api.greenhouse.io/v1/boards/"
            f"{target.tenant}/jobs?content=true"
        )

        response = self.http_client.get(url)
        response.raise_for_status()

        payload = response.json()
        observations: list[RawJobObservation] = []
        warnings: list[str] = []

        for item in payload.get("jobs", []):
            raw_id = item.get("id")
            title = item.get("title")

            if raw_id is None or not str(title or "").strip():
                identifier = (
                    str(raw_id)
                    if raw_id is not None
                    else "unknown"
                )
                warnings.append(
                    f"skipped greenhouse entry id={identifier}: "
                    "missing required id/title"
                )
                continue

            external_id = str(raw_id)
            source_payload_hash = canonical_payload_hash(item)

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
                    source_url=item["absolute_url"],
                    observed_at=datetime.now(timezone.utc),
                    updated_at=_parse_datetime(
                        item.get("updated_at")
                    ),
                    title=str(title),
                    company_name=target.tenant.replace(
                        "-",
                        " ",
                    ).title(),
                    location_text=(
                        item.get("location", {}).get(
                            "name",
                            "",
                        )
                    ),
                    description=_strip_html(
                        item.get("content")
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
