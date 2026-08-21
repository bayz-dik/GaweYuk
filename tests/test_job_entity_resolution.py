from datetime import datetime, timezone

import pytest

from onejob.ingestion.entity_resolution import (
    JobEntityResolver,
    JobIdentityCandidate,
    JobIdentityDisposition,
)


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


def _candidate(**overrides):
    base = dict(
        canonical_job_id=None,
        company_id="cmp-1",
        source_id="src-ats",
        external_id="req-1",
        authoritative_external_id=False,
        title="Operator",
        location="Bekasi",
        description="Production line operator",
        employment_type=None,
    )
    base.update(overrides)
    return JobIdentityCandidate(**base)


resolver = JobEntityResolver()


def test_same_authoritative_requisition_is_same():
    decision = resolver.resolve(
        incoming=_candidate(
            company_id="cmp-1",
            source_id="src-ats",
            external_id="req-7",
            authoritative_external_id=True,
        ),
        existing=(
            _candidate(
                canonical_job_id="job-1",
                company_id="cmp-1",
                source_id="src-ats",
                external_id="req-7",
                authoritative_external_id=True,
            ),
        ),
    )
    assert decision.disposition is JobIdentityDisposition.SAME
    assert decision.canonical_job_id == "job-1"
    assert "AUTHORITATIVE_REQUISITION_MATCH" in decision.reason_codes


def test_close_but_uncertain_candidates_are_ambiguous():
    decision = resolver.resolve(
        incoming=_candidate(
            company_id="cmp-1",
            title="Operator Produksi",
            location="Bekasi",
            description="Production line operator",
        ),
        existing=(
            _candidate(
                canonical_job_id="job-a",
                company_id="cmp-1",
                title="Operator Production",
                location="Bekasi",
                description="Production line operator day shift",
            ),
            _candidate(
                canonical_job_id="job-b",
                company_id="cmp-1",
                title="Operator Produksi",
                location="Cikarang",
                description="Production line operator night shift",
            ),
        ),
    )
    assert decision.disposition is JobIdentityDisposition.AMBIGUOUS
    assert decision.canonical_job_id is None


def test_clearly_different_requisition_is_distinct():
    decision = resolver.resolve(
        incoming=_candidate(
            company_id="cmp-1",
            title="Senior Data Scientist",
            location="Jakarta",
            description="Machine learning research role",
        ),
        existing=(
            _candidate(
                canonical_job_id="job-a",
                company_id="cmp-1",
                title="Warehouse Operator",
                location="Bekasi",
                description="Forklift and loading",
            ),
        ),
    )
    assert decision.disposition is JobIdentityDisposition.DISTINCT
    assert decision.canonical_job_id is None


def test_company_mismatch_prevents_same_even_with_similar_title():
    decision = resolver.resolve(
        incoming=_candidate(
            company_id="cmp-1",
            title="Operator Produksi",
            location="Bekasi",
        ),
        existing=(
            _candidate(
                canonical_job_id="job-a",
                company_id="cmp-2",
                title="Operator Produksi",
                location="Bekasi",
            ),
        ),
    )
    assert decision.disposition is not JobIdentityDisposition.SAME


def test_no_existing_is_distinct():
    decision = resolver.resolve(incoming=_candidate(), existing=())
    assert decision.disposition is JobIdentityDisposition.DISTINCT
    assert decision.canonical_job_id is None
