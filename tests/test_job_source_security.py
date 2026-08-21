import pytest

from onejob.job_verification.destination import (
    SafeFetchPolicy,
    UnsafeFetchTarget,
)


def _resolver(mapping=None):
    mapping = mapping or {}

    def resolve(host: str) -> list[str]:
        return mapping.get(host, ["93.184.216.34"])

    return resolve


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.1.2.3/x",
        "http://172.16.0.1/x",
        "http://192.168.0.1/x",
        "http://0.0.0.0/x",
        "http://[fe80::1]/x",
        "file:///etc/passwd",
        "gopher://example.com/",
        "https://admin:secret@example.com/",
    ],
)
def test_ssrf_targets_rejected(url):
    with pytest.raises(UnsafeFetchTarget):
        SafeFetchPolicy(resolver=_resolver()).validate_url(url)


def test_credentials_never_appear_in_assessment():
    from onejob.job_verification.destination import DestinationVerifier

    verifier = DestinationVerifier(
        fetch_policy=SafeFetchPolicy(resolver=_resolver())
    )
    # A URL without userinfo (userinfo already rejected by policy); ensure the
    # serialized assessment carries no Authorization/cookie/token fields.
    assessment = verifier.verify(
        "https://jobs.example.com/apply",
        allowed_domains=("jobs.example.com",),
        fetcher=lambda url: [url],
    )
    payload = assessment.model_dump()
    serialized = str(payload).lower()
    for secret_marker in ("authorization", "cookie", "api_key", "secret", "token"):
        assert secret_marker not in serialized


# ---------------------------------------------------------------------------
# Task 16: adversarial corpus + hard-risk publication invariants
# ---------------------------------------------------------------------------

import json
from pathlib import Path

from onejob.job_verification.models import ApplyDestinationStatus
from onejob.job_verification.policy import PublicationPolicy, PublicationState


def load_security_cases():
    path = Path("tests/security_cases/job_source_verification_cases.json")
    return json.loads(path.read_text())


class _CorpusSnapshot:
    def __init__(self, case):
        self.trust_classification = case["trust_classification"]
        self.identity_state = case["identity_state"]
        self.destination_status = ApplyDestinationStatus(case["destination_status"])
        self.freshness_state = case["freshness_state"]
        self.hard_gate_hits = tuple(case["hard_gates"])
        self.unknowns = tuple(case["unknowns"])


class _CorpusSourcePolicy:
    def __init__(self, case):
        self.publication_evidence_allowed = case["publication_evidence_allowed"]


@pytest.mark.parametrize("case", load_security_cases(), ids=lambda c: c["id"])
def test_job_source_security_case(case):
    draft = PublicationPolicy().evaluate(
        _CorpusSnapshot(case), source_policy=_CorpusSourcePolicy(case)
    )
    assert draft.state.value == case["expected"]


def test_hard_gate_can_never_become_publishable():
    # No trust classification, identity, or freshness combination can publish a
    # confirmed hard-gate job.
    for trust in ("AUTOPILOT_ELIGIBLE", "ASSISTED_ALLOWED"):
        draft = PublicationPolicy().evaluate(
            _CorpusSnapshot(
                {
                    "trust_classification": trust,
                    "identity_state": "VERIFIED",
                    "destination_status": "VERIFIED",
                    "freshness_state": "CURRENT",
                    "hard_gates": ["PAYMENT_REQUIRED"],
                    "unknowns": [],
                }
            ),
            source_policy=_CorpusSourcePolicy({"publication_evidence_allowed": True}),
        )
        assert draft.state is PublicationState.REJECTED


def test_payment_negation_does_not_trigger_payment_hard_gate():
    # Reuse the existing Trust Engine signal extractor rather than a second
    # payment detector. A negated statement must not create a payment signal,
    # while an explicit payment demand must.
    from datetime import datetime, timezone

    from onejob.trust_engine.models import RecruitmentStage
    from onejob.trust_engine.signals import extract_deterministic_signals

    now = datetime(2026, 8, 21, tzinfo=timezone.utc)

    negated = extract_deterministic_signals(
        canonical_job_id="job-neg",
        text="Tidak ada biaya rekrutmen apa pun dalam proses ini.",
        stage=RecruitmentStage.APPLICATION,
        evidence_ref="evidence-neg",
        observed_at=now,
    )
    positive = extract_deterministic_signals(
        canonical_job_id="job-pos",
        text="Transfer biaya administrasi Rp150.000 untuk memproses lamaran.",
        stage=RecruitmentStage.APPLICATION,
        evidence_ref="evidence-pos",
        observed_at=now,
    )

    negated_types = {s.signal_type for s in negated}
    positive_types = {s.signal_type for s in positive}

    assert "RECRUITMENT_PAYMENT" not in negated_types
    assert "RECRUITMENT_PAYMENT" in positive_types
