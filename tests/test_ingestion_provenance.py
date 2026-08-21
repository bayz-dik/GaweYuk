from datetime import datetime, timezone

import pytest

from onejob.ingestion.provenance import (
    EvidenceFamily,
    JobSourceAppearance,
    derive_evidence_family_id,
)


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


def test_same_upstream_listing_reuses_evidence_family():
    first = derive_evidence_family_id(
        source_id="src-greenhouse",
        external_id="req-123",
        upstream_family_hint=None,
    )
    second = derive_evidence_family_id(
        source_id="src-greenhouse",
        external_id="req-123",
        upstream_family_hint=None,
    )
    assert first == second


def test_distinct_listings_get_distinct_families():
    a = derive_evidence_family_id(
        source_id="src-greenhouse", external_id="req-1", upstream_family_hint=None
    )
    b = derive_evidence_family_id(
        source_id="src-greenhouse", external_id="req-2", upstream_family_hint=None
    )
    assert a != b


def test_mirror_can_share_upstream_family():
    origin = derive_evidence_family_id(
        source_id="src-ats", external_id="123", upstream_family_hint=None
    )
    mirror = derive_evidence_family_id(
        source_id="src-board", external_id="mirror-9", upstream_family_hint=origin
    )
    assert mirror == origin


def _prepare_db(tmp_path):
    from onejob.persistence.db import Database
    from onejob.job_sources.models import (
        AcquisitionMethod,
        ComplianceStatus,
        JobSource,
        SourceHealthState,
        SourceRolloutState,
        SourceTrustTier,
    )
    from onejob.job_sources.repository import SourceRepository
    from onejob.ingestion.models import SourceType

    db = Database(tmp_path / "prov.db")
    db.initialize()
    repo = SourceRepository()
    source = JobSource(
        source_id="src-greenhouse",
        source_key="greenhouse",
        source_type=SourceType.ATS,
        trust_tier=SourceTrustTier.TIER_1_OFFICIAL,
        acquisition_method=AcquisitionMethod.OFFICIAL_API,
        primary_domain="greenhouse.io",
        country_scope=(),
        compliance_status=ComplianceStatus.ALLOWED,
        rollout_state=SourceRolloutState.SHADOW,
        health_state=SourceHealthState.UNKNOWN,
        verification_policy_version="source-policy-v1",
        created_at=NOW,
        updated_at=NOW,
    )
    with db.transaction() as conn:
        repo.insert(conn, source)
        # canonical job the appearance links to
        conn.execute(
            "INSERT INTO companies (company_id, normalized_name, display_name) "
            "VALUES ('cmp-1', 'pt example', 'PT Example')"
        )
        conn.execute(
            """
            INSERT INTO canonical_jobs (
                canonical_job_id, company_id, title, normalized_title,
                location, normalized_location, description, lifecycle_state,
                first_seen_at, last_seen_at, active_status_confidence
            )
            VALUES ('job-1', 'cmp-1', 'Operator', 'operator', 'Bekasi',
                    'bekasi', 'desc', 'ACTIVE', ?, ?, 1.0)
            """,
            (NOW.isoformat(), NOW.isoformat()),
        )
    return db


def _observation(observation_id, external_id="req-1"):
    from onejob.ingestion.models import RawJobObservation, SourceType

    return RawJobObservation(
        observation_id=observation_id,
        source_key="greenhouse",
        source_type=SourceType.ATS,
        collector_version="1",
        external_id=external_id,
        source_url="https://boards.greenhouse.io/example/jobs/1",
        observed_at=NOW,
        title="Operator",
        company_name="PT Example",
        location_text="Bekasi",
        description="desc",
        source_payload_hash="hash-1",
    )


def test_two_observations_one_appearance_advances_last_seen(tmp_path):
    from onejob.ingestion.provenance import AppearanceRepository
    from onejob.persistence.repositories import ObservationRepository

    db = _prepare_db(tmp_path)
    obs_repo = ObservationRepository()
    appearances = AppearanceRepository()

    family_id = derive_evidence_family_id(
        source_id="src-greenhouse", external_id="req-1", upstream_family_hint=None
    )

    first_seen = NOW
    later = datetime(2026, 8, 22, tzinfo=timezone.utc)

    with db.transaction() as conn:
        obs_repo.insert(conn, _observation("obs-1"))
        appearances.upsert_seen(
            conn,
            canonical_job_id="job-1",
            source_id="src-greenhouse",
            external_id="req-1",
            source_url="https://boards.greenhouse.io/example/jobs/1",
            apply_url=None,
            evidence_family_id=family_id,
            observation_id="obs-1",
            seen_at=first_seen,
        )

    with db.transaction() as conn:
        obs_repo.insert(conn, _observation("obs-2"))
        appearances.upsert_seen(
            conn,
            canonical_job_id="job-1",
            source_id="src-greenhouse",
            external_id="req-1",
            source_url="https://boards.greenhouse.io/example/jobs/1",
            apply_url=None,
            evidence_family_id=family_id,
            observation_id="obs-2",
            seen_at=later,
        )

    with db.connection() as conn:
        raw_count = conn.execute(
            "SELECT COUNT(*) FROM raw_job_observations"
        ).fetchone()[0]
        appearance_rows = conn.execute(
            "SELECT first_seen_at, last_seen_at, latest_observation_id "
            "FROM job_source_appearances WHERE source_id='src-greenhouse' "
            "AND external_id='req-1'"
        ).fetchall()

    # Two immutable raw observations, but a single appearance whose last_seen
    # advanced and latest observation pointer moved.
    assert raw_count == 2
    assert len(appearance_rows) == 1
    assert appearance_rows[0][0] == first_seen.isoformat()
    assert appearance_rows[0][1] == later.isoformat()
    assert appearance_rows[0][2] == "obs-2"
