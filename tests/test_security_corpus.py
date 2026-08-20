from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from onejob.trust_engine.models import (
    DetectionMethod,
    DimensionScore,
    DimensionState,
    RecruitmentStage,
    SignalLevel,
    SignalStatus,
    TrustClassification,
    TrustDimension,
    TrustSignal,
)
from onejob.trust_engine.policy import evaluate_policy
from onejob.trust_engine.signals import (
    extract_deterministic_signals,
    redact_secrets,
)

NOW = datetime.now(timezone.utc)
CASE_DIR = Path(__file__).parent / "security_cases"
CASE_FILES = sorted(CASE_DIR.glob("*.json"))


def _extract(text: str, stage: RecruitmentStage):
    return extract_deterministic_signals(
        canonical_job_id="job-security",
        text=text,
        stage=stage,
        evidence_ref="observation:security-corpus",
        observed_at=NOW,
    )


@pytest.mark.parametrize("case_path", CASE_FILES, ids=lambda path: path.stem)
def test_security_case(case_path: Path):
    case = json.loads(case_path.read_text(encoding="utf-8"))

    signals = _extract(
        case["text"],
        RecruitmentStage(case["stage"]),
    )

    signal_types = {signal.signal_type for signal in signals}

    assert set(case.get("expected_signal_types", [])) <= signal_types
    assert signal_types.isdisjoint(
        set(case.get("forbidden_signal_types", []))
    )

    serialized = repr(signals)

    for secret in case.get("secret_literals", []):
        assert secret not in serialized

    for signal in signals:
        assert signal.evidence_refs == ("observation:security-corpus",)
        assert not hasattr(signal, "raw_text")
        assert not hasattr(signal, "raw_secret")


@pytest.mark.parametrize("stage", list(RecruitmentStage))
def test_identity_document_privacy_stage_matrix(stage):
    signals = _extract("Upload KTP sekarang.", stage)
    detected = {signal.signal_type for signal in signals}

    if stage is RecruitmentStage.ONBOARDING:
        assert "EARLY_IDENTITY_DOCUMENT" not in detected
    else:
        assert "EARLY_IDENTITY_DOCUMENT" in detected


@pytest.mark.parametrize("stage", list(RecruitmentStage))
def test_bank_data_privacy_stage_matrix(stage):
    signals = _extract("Masukkan nomor rekening bank sekarang.", stage)
    detected = {signal.signal_type for signal in signals}

    if stage is RecruitmentStage.ONBOARDING:
        assert "EARLY_BANK_DATA" not in detected
    else:
        assert "EARLY_BANK_DATA" in detected


@pytest.mark.parametrize("stage", list(RecruitmentStage))
def test_credential_request_is_l4_at_every_stage(stage):
    signals = _extract("Kirim OTP 654321 ke recruiter.", stage)

    otp = next(
        signal
        for signal in signals
        if signal.signal_type == "OTP_REQUEST"
    )

    assert otp.level is SignalLevel.L4


@pytest.mark.parametrize(
    ("text", "secret"),
    (
        ("OTP: 123456", "123456"),
        ("PIN: 9876", "9876"),
        ("password: supersecret", "supersecret"),
        ("recovery code: ABCD1234", "ABCD1234"),
    ),
)
def test_redaction_removes_secret_literals(text, secret):
    redacted = redact_secrets(text)
    assert secret not in redacted
    assert "[REDACTED]" in redacted


def _known_dimensions():
    return {
        dimension: DimensionScore(
            dimension=dimension,
            state=DimensionState.KNOWN,
            score=95.0,
            confidence=95.0,
            reason_codes=("SECURITY_CORPUS_BASELINE",),
            evidence_refs=(),
        )
        for dimension in TrustDimension
    }


def _ai_signal(level: SignalLevel):
    return TrustSignal(
        signal_id=f"sig-ai-{level.value.lower()}",
        canonical_job_id="job-security",
        signal_type="AI_SUSPECTED_CRITICAL_RISK",
        level=level,
        status=SignalStatus.ACTIVE,
        confidence=0.99,
        detection_method=DetectionMethod.AI,
        context_stage=RecruitmentStage.APPLICATION,
        evidence_refs=("ai:evidence-1",),
        extractor_version="ai-test-v1",
        fingerprint=f"ai-{level.value}",
        first_seen_at=NOW,
        last_seen_at=NOW,
    )


@pytest.mark.parametrize("level", (SignalLevel.L3, SignalLevel.L4))
def test_model_only_critical_signal_requires_corroboration(level):
    decision = evaluate_policy(
        canonical_job_id="job-security",
        recruitment_stage=RecruitmentStage.APPLICATION,
        overall_score=95.0,
        confidence=95.0,
        dimensions=_known_dimensions(),
        signals=(_ai_signal(level),),
        evaluated_at=NOW,
        input_fingerprint=f"ai-only-{level.value}",
    )

    assert decision.classification is TrustClassification.REVIEW_REQUIRED
    assert decision.hard_gates
    assert (
        decision.hard_gates[0].effect
        is TrustClassification.REVIEW_REQUIRED
    )
    assert (
        decision.hard_gates[0].override_policy
        == "REQUIRES_CORROBORATION"
    )


def test_rule_l4_still_absolute_blocks():
    signal = TrustSignal(
        signal_id="sig-rule-l4",
        canonical_job_id="job-security",
        signal_type="OTP_REQUEST",
        level=SignalLevel.L4,
        status=SignalStatus.ACTIVE,
        confidence=1.0,
        detection_method=DetectionMethod.RULE,
        context_stage=RecruitmentStage.APPLICATION,
        evidence_refs=("observation:1",),
        extractor_version="rules-v1",
        fingerprint="rule-l4",
        first_seen_at=NOW,
        last_seen_at=NOW,
    )

    decision = evaluate_policy(
        canonical_job_id="job-security",
        recruitment_stage=RecruitmentStage.APPLICATION,
        overall_score=100.0,
        confidence=100.0,
        dimensions=_known_dimensions(),
        signals=(signal,),
        evaluated_at=NOW,
        input_fingerprint="rule-l4",
    )

    assert decision.classification is TrustClassification.ABSOLUTE_BLOCK
