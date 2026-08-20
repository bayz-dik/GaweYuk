from datetime import datetime, timezone

from onejob.ingestion.models import RawJobObservation, SourceType
from onejob.provenance.evidence import build_field_evidence


def test_same_upstream_family_is_not_counted_as_independent():
    now = datetime.now(timezone.utc)

    a = RawJobObservation(
        observation_id="a",
        source_key="company-ats",
        source_type=SourceType.ATS,
        collector_version="1",
        external_id="x",
        source_url="https://ats/x",
        observed_at=now,
        title="Operator",
        company_name="Example",
        location_text="Bekasi",
        description="Operate machines",
        source_payload_hash="1",
    )

    b = a.model_copy(
        update={
            "observation_id": "b",
            "source_key": "linkedin",
            "source_url": "https://linkedin/x",
            "source_payload_hash": "2",
        }
    )

    evidence = build_field_evidence(
        "job-1",
        [a, b],
        upstream_family={"linkedin": "company-ats"},
    )

    title_evidence = [
        e for e in evidence
        if e.field_name == "title"
    ]

    assert len({
        e.evidence_family_id
        for e in title_evidence
    }) == 1
