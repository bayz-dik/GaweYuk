from datetime import datetime, timezone

from onejob.trust_engine.models import (
    RecruitmentStage,
    SignalLevel,
)
from onejob.trust_engine.signals import (
    extract_deterministic_signals,
    redact_secrets,
)


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def extract(text, stage=RecruitmentStage.APPLICATION):
    return extract_deterministic_signals(
        canonical_job_id="job-1",
        text=text,
        stage=stage,
        evidence_ref="observation:1",
        observed_at=NOW,
    )


def signal_by_type(signals, signal_type):
    return next(
        signal
        for signal in signals
        if signal.signal_type == signal_type
    )


def test_payment_instruction_is_l3():
    signals = extract(
        "Silakan transfer biaya administrasi "
        "Rp150.000 ke rekening berikut."
    )

    signal = signal_by_type(
        signals,
        "RECRUITMENT_PAYMENT",
    )

    assert signal.level is SignalLevel.L3
    assert signal.confidence == 1.0


def test_negated_payment_warning_does_not_trigger():
    signals = extract(
        "Kami tidak pernah meminta biaya, "
        "deposit, atau transfer apa pun."
    )

    assert not any(
        signal.signal_type == "RECRUITMENT_PAYMENT"
        for signal in signals
    )


def test_otp_request_is_l4():
    signals = extract(
        "Kirim OTP 123456 ke recruiter.",
        RecruitmentStage.SCREENING,
    )

    signal = signal_by_type(
        signals,
        "OTP_REQUEST",
    )

    assert signal.level is SignalLevel.L4


def test_otp_warning_does_not_trigger():
    signals = extract(
        "Jangan pernah kirim OTP kepada siapa pun.",
        RecruitmentStage.SCREENING,
    )

    assert not any(
        signal.signal_type == "OTP_REQUEST"
        for signal in signals
    )


def test_password_request_is_l4():
    signals = extract(
        "Berikan password akun kamu kepada recruiter.",
        RecruitmentStage.SCREENING,
    )

    assert (
        signal_by_type(
            signals,
            "PASSWORD_REQUEST",
        ).level
        is SignalLevel.L4
    )


def test_early_ktp_request_is_l3():
    signals = extract(
        "Upload KTP sebelum mengirim lamaran.",
        RecruitmentStage.APPLICATION,
    )

    assert (
        signal_by_type(
            signals,
            "EARLY_IDENTITY_DOCUMENT",
        ).level
        is SignalLevel.L3
    )


def test_onboarding_ktp_is_not_early_identity_signal():
    signals = extract(
        "Silakan upload KTP untuk proses onboarding.",
        RecruitmentStage.ONBOARDING,
    )

    assert not any(
        signal.signal_type == "EARLY_IDENTITY_DOCUMENT"
        for signal in signals
    )


def test_early_bank_account_request_is_l3():
    signals = extract(
        "Masukkan nomor rekening bank saat screening.",
        RecruitmentStage.SCREENING,
    )

    assert (
        signal_by_type(
            signals,
            "EARLY_BANK_DATA",
        ).level
        is SignalLevel.L3
    )


def test_card_image_request_is_l3_even_during_onboarding():
    signals = extract(
        "Kirim foto kartu ATM bagian depan.",
        RecruitmentStage.ONBOARDING,
    )

    assert (
        signal_by_type(
            signals,
            "CARD_IMAGE_REQUEST",
        ).level
        is SignalLevel.L3
    )


def test_secret_redaction_removes_otp_value():
    redacted = redact_secrets(
        "OTP: 123456"
    )

    assert "123456" not in redacted
    assert "[REDACTED]" in redacted


def test_signal_never_persists_raw_secret_text():
    signals = extract(
        "OTP: 123456 harus dikirim ke recruiter.",
        RecruitmentStage.SCREENING,
    )

    signal = signal_by_type(
        signals,
        "OTP_REQUEST",
    )

    serialized_refs = " ".join(signal.evidence_refs)

    assert "123456" not in serialized_refs
    assert signal.evidence_refs == (
        "observation:1",
    )


def test_same_input_produces_same_signal_identity():
    first = extract(
        "Bayar biaya administrasi Rp100.000."
    )
    second = extract(
        "Bayar biaya administrasi Rp100.000."
    )

    a = signal_by_type(
        first,
        "RECRUITMENT_PAYMENT",
    )
    b = signal_by_type(
        second,
        "RECRUITMENT_PAYMENT",
    )

    assert a.signal_id == b.signal_id
    assert a.fingerprint == b.fingerprint


def test_unknown_stage_is_conservative_for_identity_docs():
    signals = extract(
        "Upload NPWP sekarang.",
        RecruitmentStage.UNKNOWN,
    )

    assert any(
        signal.signal_type == "EARLY_IDENTITY_DOCUMENT"
        for signal in signals
    )
