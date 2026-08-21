"""Pre-PR review fixes for Slice 4A: production-path integration hardening.

These tests exercise the real ingestion orchestration rather than unit stubs:
tri-state entity resolution, real apply-destination verification, snapshot-bound
catalog destinations, and mirror evidence-family lineage.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from onejob.catalog.api import create_catalog_router
from onejob.collectors.base import (
    CollectionBatch,
    CollectionStatus,
    CollectionTarget,
)
from onejob.ingestion.entity_resolution import JobIdentityDisposition
from onejob.ingestion.models import RawJobObservation, SourceType
from onejob.ingestion.pipeline import IngestionPipeline
from onejob.job_sources.models import (
    AcquisitionMethod,
    ComplianceStatus,
    SourceRolloutState,
    SourceTrustTier,
)
from onejob.job_sources.service import JobSourceService
from onejob.job_verification.destination import (
    DestinationVerifier,
    SafeFetchPolicy,
)
from onejob.job_verification.models import ApplyDestinationStatus
from onejob.job_verification.repository import VerificationRepository
from onejob.persistence.db import Database


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


def _resolver(mapping=None):
    mapping = mapping or {}

    def resolve(host: str) -> list[str]:
        return mapping.get(host, ["93.184.216.34"])

    return resolve


def _no_redirect_fetcher():
    def fetcher(url):
        return [url]

    return fetcher


class _Collector:
    source_key = "greenhouse"
    source_type = SourceType.ATS
    collector_version = "1"
    acquisition_method = AcquisitionMethod.OFFICIAL_API
    target = CollectionTarget(tenant="contoh")

    def __init__(self, observations):
        self._observations = observations

    def collect(self, target):
        return CollectionBatch(
            source_key=self.source_key,
            source_type=self.source_type,
            collector_version=self.collector_version,
            target=target,
            started_at=NOW,
            finished_at=NOW,
            status=CollectionStatus.SUCCESS,
            observations=list(self._observations),
        )


def _observation(
    *,
    observation_id,
    external_id,
    title="Production Operator",
    location="Bekasi",
    description="Operate production machines safely.",
    apply_url=None,
    source_key="greenhouse",
    upstream_family_hint=None,
):
    return RawJobObservation(
        observation_id=observation_id,
        source_key=source_key,
        source_type=SourceType.ATS,
        collector_version="1",
        external_id=external_id,
        source_url=f"https://boards.greenhouse.io/contoh/jobs/{external_id}",
        apply_url=apply_url,
        observed_at=NOW,
        title=title,
        company_name="PT Contoh",
        location_text=location,
        description=description,
        source_payload_hash=f"hash-{observation_id}",
        upstream_family_hint=upstream_family_hint,
    )


def _register_source(db, *, source_id, source_key, primary_domain="greenhouse.io"):
    service = JobSourceService(db)
    service.register(
        source_id=source_id,
        source_key=source_key,
        source_type=SourceType.ATS,
        trust_tier=SourceTrustTier.TIER_1_OFFICIAL,
        acquisition_method=AcquisitionMethod.OFFICIAL_API,
        primary_domain=primary_domain,
        country_scope=("ID",),
        compliance_status=ComplianceStatus.ALLOWED,
        verification_policy_version="source-policy-v1",
        now=NOW,
    )
    for target in (
        SourceRolloutState.SHADOW,
        SourceRolloutState.OBSERVED,
        SourceRolloutState.VALIDATED,
        SourceRolloutState.ACTIVE,
    ):
        with db.connection() as conn:
            live = service.repo.get_by_id(conn, source_id)
        service.promote(
            source_id=source_id,
            expected_state=live.rollout_state,
            target_state=target,
            reason_code="test_promote",
            now=NOW,
        )


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "prod.db")
    database.initialize()
    return database


# ---------------------------------------------------------------------------
# Critical 1: tri-state entity resolution in the production ingestion path
# ---------------------------------------------------------------------------


def test_production_path_resolves_same_requisition_to_one_canonical_job(db):
    _register_source(db, source_id="src-greenhouse", source_key="greenhouse")
    pipeline = IngestionPipeline(db)

    first = pipeline.collect_one(
        _Collector([_observation(observation_id="obs-1", external_id="req-1")]),
        CollectionTarget(tenant="contoh"),
    )
    second = pipeline.collect_one(
        _Collector([_observation(observation_id="obs-2", external_id="req-1")]),
        CollectionTarget(tenant="contoh"),
    )

    assert first.canonical_job_ids == second.canonical_job_ids
    with db.connection() as conn:
        jobs = conn.execute("SELECT COUNT(*) FROM canonical_jobs").fetchone()[0]
    assert jobs == 1


def test_production_path_creates_distinct_jobs_for_different_requisitions(db):
    _register_source(db, source_id="src-greenhouse", source_key="greenhouse")
    pipeline = IngestionPipeline(db)

    pipeline.collect_one(
        _Collector(
            [
                _observation(
                    observation_id="obs-1",
                    external_id="req-1",
                    title="Production Operator",
                    location="Bekasi",
                )
            ]
        ),
        CollectionTarget(tenant="contoh"),
    )
    pipeline.collect_one(
        _Collector(
            [
                _observation(
                    observation_id="obs-2",
                    external_id="req-2",
                    title="Senior Data Scientist",
                    location="Jakarta",
                    description="Machine learning research role",
                )
            ]
        ),
        CollectionTarget(tenant="contoh"),
    )

    with db.connection() as conn:
        jobs = conn.execute("SELECT COUNT(*) FROM canonical_jobs").fetchone()[0]
    assert jobs == 2


def _seed_canonical_job(db, *, job_id, title, location, description):
    """Insert prior canonical state directly.

    Two real requisitions already exist in the catalog. Seeding them directly
    keeps the assertion focused on how the production path handles the later
    AMBIGUOUS observation.
    """
    from onejob.ingestion.identity import company_id_for

    company_id = company_id_for("PT Contoh")
    with db.transaction() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO companies (company_id, normalized_name, "
            "display_name) VALUES (?, 'pt contoh', 'PT Contoh')",
            (company_id,),
        )
        conn.execute(
            """
            INSERT INTO canonical_jobs (
                canonical_job_id, company_id, title, normalized_title, location,
                normalized_location, description, lifecycle_state,
                first_seen_at, last_seen_at, active_status_confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, 1.0)
            """,
            (
                job_id,
                company_id,
                title,
                title.lower(),
                location,
                location.lower(),
                description,
                NOW.isoformat(),
                NOW.isoformat(),
            ),
        )


def test_production_path_does_not_silently_merge_ambiguous_observation(db):
    _register_source(db, source_id="src-greenhouse", source_key="greenhouse")

    # Two plausible existing requisitions from the same company.
    _seed_canonical_job(
        db,
        job_id="job-a",
        title="Operator Production",
        location="Bekasi",
        description="Production line operator day shift",
    )
    _seed_canonical_job(
        db,
        job_id="job-b",
        title="Operator Produksi",
        location="Cikarang",
        description="Production line operator night shift",
    )

    pipeline = IngestionPipeline(db)

    # An incoming observation that is close to both must not silently merge.
    ambiguous = pipeline.collect_one(
        _Collector(
            [
                _observation(
                    observation_id="obs-ambiguous",
                    external_id="req-ambiguous",
                    title="Operator Produksi",
                    location="Bekasi",
                    description="Production line operator",
                )
            ]
        ),
        CollectionTarget(tenant="contoh"),
    )

    with db.connection() as conn:
        # Raw observation and provenance are preserved.
        raw = conn.execute(
            "SELECT COUNT(*) FROM raw_job_observations "
            "WHERE observation_id = 'obs-ambiguous'"
        ).fetchone()[0]
        provenance = conn.execute(
            "SELECT COUNT(*) FROM observation_provenance "
            "WHERE observation_id = 'obs-ambiguous'"
        ).fetchone()[0]
        # The ambiguous observation is not attached to either existing job.
        merged = conn.execute(
            "SELECT COUNT(*) FROM canonical_job_sources "
            "WHERE observation_id = 'obs-ambiguous'"
        ).fetchone()[0]
        review_cases = conn.execute(
            "SELECT COUNT(*) FROM verification_cases "
            "WHERE reason_codes_json LIKE '%AMBIGUOUS%'"
        ).fetchone()[0]
        jobs_after = conn.execute(
            "SELECT COUNT(*) FROM canonical_jobs"
        ).fetchone()[0]

    assert raw == 1
    assert provenance == 1
    assert merged == 0
    assert jobs_after == 2  # no silent absorption, no new merge target
    assert ambiguous.canonical_job_ids == []
    assert "obs-ambiguous" in ambiguous.ambiguous_observation_ids
    assert review_cases >= 1


# ---------------------------------------------------------------------------
# Critical 2: real apply-destination verification, never auto-VERIFIED
# ---------------------------------------------------------------------------


def _pipeline_with_verifier(db, *, dns=None, fetcher=None):
    verifier = DestinationVerifier(
        fetch_policy=SafeFetchPolicy(resolver=_resolver(dns))
    )
    return IngestionPipeline(
        db,
        destination_verifier=verifier,
        destination_fetcher=fetcher or _no_redirect_fetcher(),
    )


def _destination_status(db, canonical_job_id):
    with db.connection() as conn:
        row = conn.execute(
            "SELECT destination_status FROM job_verification_snapshots "
            "WHERE canonical_job_id = ? ORDER BY evaluated_at DESC LIMIT 1",
            (canonical_job_id,),
        ).fetchone()
    return row[0] if row is not None else None


@pytest.mark.parametrize(
    "apply_url",
    [
        "http://127.0.0.1/apply",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/apply",
    ],
)
def test_unsafe_apply_url_never_becomes_verified(db, apply_url):
    _register_source(db, source_id="src-greenhouse", source_key="greenhouse")
    pipeline = _pipeline_with_verifier(db)

    result = pipeline.collect_one(
        _Collector(
            [
                _observation(
                    observation_id="obs-unsafe",
                    external_id="req-unsafe",
                    apply_url=apply_url,
                )
            ]
        ),
        CollectionTarget(tenant="contoh"),
    )
    job_id = result.canonical_job_ids[0]

    assert _destination_status(db, job_id) == ApplyDestinationStatus.BLOCKED.value


def test_public_unverified_external_url_is_not_verified(db):
    _register_source(db, source_id="src-greenhouse", source_key="greenhouse")
    pipeline = _pipeline_with_verifier(db)

    result = pipeline.collect_one(
        _Collector(
            [
                _observation(
                    observation_id="obs-external",
                    external_id="req-external",
                    apply_url="https://random-third-party.example/apply",
                )
            ]
        ),
        CollectionTarget(tenant="contoh"),
    )
    job_id = result.canonical_job_ids[0]

    # A non-empty public URL is not verification.
    assert _destination_status(db, job_id) != ApplyDestinationStatus.VERIFIED.value


def test_safe_ats_destination_can_become_verified_through_verifier(db):
    _register_source(db, source_id="src-greenhouse", source_key="greenhouse")
    pipeline = _pipeline_with_verifier(db)

    result = pipeline.collect_one(
        _Collector(
            [
                _observation(
                    observation_id="obs-ats",
                    external_id="req-ats",
                    apply_url="https://boards.greenhouse.io/contoh/jobs/req-ats",
                )
            ]
        ),
        CollectionTarget(tenant="contoh"),
    )
    job_id = result.canonical_job_ids[0]

    assert _destination_status(db, job_id) == ApplyDestinationStatus.VERIFIED.value


def test_missing_verifier_fails_closed_to_unknown(db):
    _register_source(db, source_id="src-greenhouse", source_key="greenhouse")
    # No verifier injected: the boundary must not auto-verify.
    pipeline = IngestionPipeline(db)

    result = pipeline.collect_one(
        _Collector(
            [
                _observation(
                    observation_id="obs-noverifier",
                    external_id="req-noverifier",
                    apply_url="https://boards.greenhouse.io/contoh/jobs/x",
                )
            ]
        ),
        CollectionTarget(tenant="contoh"),
    )
    job_id = result.canonical_job_ids[0]

    assert _destination_status(db, job_id) == ApplyDestinationStatus.UNKNOWN.value


def test_redirect_to_private_target_is_blocked_in_pipeline(db):
    _register_source(db, source_id="src-greenhouse", source_key="greenhouse")

    def redirecting(url):
        return [url, "http://169.254.169.254/meta"]

    pipeline = _pipeline_with_verifier(db, fetcher=redirecting)

    result = pipeline.collect_one(
        _Collector(
            [
                _observation(
                    observation_id="obs-redirect",
                    external_id="req-redirect",
                    apply_url="https://boards.greenhouse.io/contoh/jobs/req-redirect",
                )
            ]
        ),
        CollectionTarget(tenant="contoh"),
    )
    job_id = result.canonical_job_ids[0]

    assert _destination_status(db, job_id) == ApplyDestinationStatus.BLOCKED.value


# ---------------------------------------------------------------------------
# Critical 3: catalog destination bound to the authorizing verification snapshot
# ---------------------------------------------------------------------------


def _persist_eligible_trust(db, canonical_job_id, *, evaluated_at):
    from onejob.trust_engine.models import (
        DimensionScore,
        DimensionState,
        RecruitmentStage,
        TrustClassification,
        TrustDecision,
        TrustDimension,
    )
    from onejob.trust_engine.repository import TrustRepository

    dimensions = {
        dim: DimensionScore(
            dimension=dim,
            state=DimensionState.KNOWN,
            score=95.0,
            confidence=95.0,
            reason_codes=("VERIFIED_AUTHORITATIVE",),
            evidence_refs=(),
        )
        for dim in TrustDimension
    }
    decision = TrustDecision(
        evaluation_id=f"eval-eligible-{canonical_job_id}",
        canonical_job_id=canonical_job_id,
        recruitment_stage=RecruitmentStage.APPLICATION,
        overall_score=95.0,
        confidence=95.0,
        dimensions=dimensions,
        classification=TrustClassification.AUTOPILOT_ELIGIBLE,
        hard_gates=(),
        risk_signal_ids=(),
        unknown_dimensions=(),
        not_applicable_dimensions=(),
        allowed_actions=("APPLY",),
        blocked_actions=(),
        override_policy="NONE",
        primary_reasons=("AUTOPILOT_THRESHOLDS_MET",),
        evidence_refs=(),
        evaluated_at=evaluated_at,
        valid_until=None,
        input_fingerprint=f"eligible-{canonical_job_id}",
        policy_version="trust-v1",
    )
    repo = TrustRepository()
    with db.transaction() as conn:
        repo.ensure_schema(conn)
        repo.append_evaluation(conn, decision)


def _seed_verified_identity(db):
    """Seed a verified ATS-to-company relationship for PT Contoh."""
    from onejob.company_identity.models import (
        IdentityNode,
        IdentityNodeType,
        IdentityRelationship,
        IdentityRelationshipStatus,
        IdentityRelationshipType,
    )
    from onejob.company_identity.repository import CompanyIdentityRepository
    from onejob.ingestion.identity import company_id_for

    repo = CompanyIdentityRepository()
    company_id = company_id_for("PT Contoh")
    with db.transaction() as conn:
        repo.insert_node(
            conn,
            IdentityNode(
                node_id="node-ats-contoh",
                node_type=IdentityNodeType.ATS_TENANT,
                value="contoh",
                created_at=NOW,
            ),
        )
        repo.insert_relationship(
            conn,
            IdentityRelationship(
                relationship_id="rel-contoh",
                company_id=company_id,
                node_id="node-ats-contoh",
                relationship_type=IdentityRelationshipType.ATS_FOR,
                status=IdentityRelationshipStatus.VERIFIED,
                confidence=0.99,
                verification_method="MANUAL_EVIDENCE",
                evidence_refs=("evidence-contoh-1",),
                first_verified_at=NOW,
                last_verified_at=NOW,
            ),
        )
    return company_id


def test_catalog_does_not_expose_changed_unverified_domain(db):
    _register_source(db, source_id="src-greenhouse", source_key="greenhouse")
    _seed_verified_identity(db)
    app = FastAPI()
    app.include_router(create_catalog_router(db))
    client = TestClient(app, raise_server_exceptions=False)

    pipeline = _pipeline_with_verifier(db)
    safe_url = "https://boards.greenhouse.io/contoh/jobs/req-bound"
    result = pipeline.collect_one(
        _Collector(
            [
                _observation(
                    observation_id="obs-bound",
                    external_id="req-bound",
                    apply_url=safe_url,
                )
            ]
        ),
        CollectionTarget(tenant="contoh"),
    )
    job_id = result.canonical_job_ids[0]

    _persist_eligible_trust(
        db, job_id, evaluated_at=datetime.now(timezone.utc) + timedelta(days=1)
    )
    pipeline.reverify_and_publish(job_id, now=NOW)

    published = client.get(f"/api/catalog/jobs/{job_id}").json()
    assert published["apply_destination"]["status"] == "VERIFIED"
    assert published["apply_destination"]["domain"] == "boards.greenhouse.io"

    # The latest appearance changes to a malicious domain with no successful
    # reverification. The catalog must keep exposing only the domain that was
    # actually verified for the current publication head.
    with db.transaction() as conn:
        conn.execute(
            "UPDATE job_source_appearances SET apply_url = ? "
            "WHERE canonical_job_id = ?",
            ("https://evil-lookalike.example/apply", job_id),
        )

    after = client.get(f"/api/catalog/jobs/{job_id}").json()
    assert after["apply_destination"]["domain"] != "evil-lookalike.example"
    assert after["apply_destination"]["domain"] == "boards.greenhouse.io"


# ---------------------------------------------------------------------------
# Important 4: mirror lineage through the real ingestion path
# ---------------------------------------------------------------------------


def test_mirrors_share_one_independent_family_through_real_pipeline(db):
    _register_source(db, source_id="src-greenhouse", source_key="greenhouse")
    _register_source(
        db,
        source_id="src-board-a",
        source_key="board-a",
        primary_domain="board-a.example",
    )
    _register_source(
        db,
        source_id="src-board-b",
        source_key="board-b",
        primary_domain="board-b.example",
    )

    pipeline = _pipeline_with_verifier(db)

    origin = pipeline.collect_one(
        _Collector(
            [_observation(observation_id="obs-origin", external_id="req-mirror")]
        ),
        CollectionTarget(tenant="contoh"),
    )
    job_id = origin.canonical_job_ids[0]

    with db.connection() as conn:
        upstream_family = conn.execute(
            "SELECT evidence_family_id FROM job_source_appearances "
            "WHERE canonical_job_id = ?",
            (job_id,),
        ).fetchone()[0]

    # Two mirrors declare the shared upstream origin family.
    for mirror_id, source_key in (
        ("obs-mirror-a", "board-a"),
        ("obs-mirror-b", "board-b"),
    ):
        pipeline.collect_one(
            _Collector(
                [
                    _observation(
                        observation_id=mirror_id,
                        external_id=f"{mirror_id}-ext",
                        source_key=source_key,
                        upstream_family_hint=upstream_family,
                    )
                ]
            ),
            CollectionTarget(tenant="contoh"),
        )

    with db.connection() as conn:
        rows = conn.execute(
            "SELECT evidence_family_id FROM job_source_appearances "
            "WHERE canonical_job_id = ?",
            (job_id,),
        ).fetchall()
        snapshot = conn.execute(
            "SELECT corroboration_json FROM job_verification_snapshots "
            "WHERE canonical_job_id = ? ORDER BY evaluated_at DESC LIMIT 1",
            (job_id,),
        ).fetchone()

    assert len(rows) == 3
    assert len({row[0] for row in rows}) == 1

    import json

    corroboration = json.loads(snapshot[0])
    assert corroboration["appearance_count"] == 3
    assert corroboration["independent_family_count"] == 1
