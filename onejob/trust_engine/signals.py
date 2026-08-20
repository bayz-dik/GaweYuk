from __future__ import annotations

from datetime import datetime
import hashlib
import re

from .models import (
    DetectionMethod,
    RecruitmentStage,
    SignalLevel,
    SignalStatus,
    TrustSignal,
)


EXTRACTOR_VERSION = "rules-v1"

EARLY_SENSITIVE_STAGES = frozenset(
    {
        RecruitmentStage.DISCOVERY,
        RecruitmentStage.APPLICATION,
        RecruitmentStage.SCREENING,
        RecruitmentStage.INTERVIEW,
        RecruitmentStage.OFFER,
        RecruitmentStage.UNKNOWN,
    }
)


NEGATION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:tidak|tak)\s+(?:pernah\s+)?"
        r"(?:meminta|memerlukan|membutuhkan)\b",
        r"\bjangan\s+(?:pernah\s+)?"
        r"(?:kirim|berikan|bagikan|share)\b",
        r"\bnever\s+"
        r"(?:send|share|give|provide|pay|ask)\b",
        r"\bdo\s+not\s+"
        r"(?:send|share|give|provide|pay|ask)\b",
        r"\bdon't\s+"
        r"(?:send|share|give|provide|pay|ask)\b",
        r"\bno\s+(?:payment|fee|deposit)\s+"
        r"(?:is\s+)?required\b",
        r"\btidak\s+ada\s+biaya\b",
        r"\btanpa\s+biaya\b",
    )
)


PAYMENT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bbiaya\s+"
        r"(?:administrasi|admin|rekrutmen|training)\b",
        r"\b(?:application|recruitment|training)\s+fee\b",
        r"\bdeposit\b",
        r"\buang\s+komitmen\b",
        r"\bjaminan\s+training\b",
        r"\btransfer\b.{0,80}\b"
        r"(?:rp|idr|rekening|account)\b",
        r"\b(?:rp|idr)\s*[\d.,]+.{0,80}\btransfer\b",
    )
)


OTP_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\botp\b",
        r"\bkode\s+verifikasi\b",
        r"\bverification\s+code\b",
    )
)


PIN_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bpin\b",
        r"\bpersonal\s+identification\s+number\b",
    )
)


PASSWORD_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bpassword\b",
        r"\bkata\s+sandi\b",
    )
)


RECOVERY_CODE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\brecovery\s+code\b",
        r"\bkode\s+pemulihan\b",
    )
)


AUTH_SECRET_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bauthentication\s+token\b",
        r"\bauth\s+token\b",
        r"\btoken\s+autentikasi\b",
        r"\b2fa\s+code\b",
        r"\bkode\s+2fa\b",
    )
)


IDENTITY_DOCUMENT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bktp\b",
        r"\bnpwp\b",
        r"\bkk\b",
        r"\bkartu\s+keluarga\b",
    )
)


BANK_DATA_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bnomor\s+rekening\b",
        r"\brekening\s+bank\b",
        r"\bbank\s+account\b",
        r"\baccount\s+number\b",
    )
)


CARD_IMAGE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bfoto\s+kartu\s+atm\b",
        r"\bfoto\s+kartu\s+debit\b",
        r"\bfoto\s+kartu\s+kredit\b",
        r"\b(?:debit|credit|atm)\s+card\s+image\b",
    )
)


SECRET_VALUE_PATTERN = re.compile(
    r"(?P<label>"
    r"otp|pin|password|kata\s+sandi|"
    r"recovery\s+code|kode\s+pemulihan|"
    r"verification\s+code|kode\s+verifikasi|"
    r"2fa\s+code|kode\s+2fa"
    r")"
    r"(?P<separator>\s*[:=]?\s*)"
    r"(?P<secret>[A-Za-z0-9._-]{4,})",
    re.IGNORECASE,
)


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def redact_secrets(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return (
            f"{match.group('label')}"
            f"{match.group('separator')}"
            "[REDACTED]"
        )

    return SECRET_VALUE_PATTERN.sub(
        replace,
        text,
    )


def signal_fingerprint(
    *,
    canonical_job_id: str,
    signal_type: str,
    evidence_ref: str,
) -> str:
    material = "|".join(
        (
            _normalize(canonical_job_id),
            _normalize(signal_type),
            _normalize(evidence_ref),
        )
    )

    return hashlib.sha256(
        material.encode("utf-8")
    ).hexdigest()


def _signal_id(fingerprint: str) -> str:
    return f"sig-{fingerprint[:24]}"


def _sentences(text: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(
            r"(?<=[.!?])\s+|\n+",
            text,
        )
        if part.strip()
    ]


def _is_technical_context(sentence: str) -> bool:
    directive = re.search(
        r"\b(?:please|silakan|harap|mohon|kirim|kirimkan|dikirim|berikan|bagikan|send|share|provide|upload|unggah|masukkan|submit|bayar|setor|wajib|harus|must|required)\b",
        sentence,
        re.IGNORECASE,
    )
    if directive:
        return False

    patterns = (
        r"\bexperience\b.{0,80}\b(?:building|developing|implementing)\b",
        r"\bknowledge\s+of\b",
        r"\b(?:validation|verification|reset)\s+(?:algorithms?|systems?)\b",
        r"\breconciliation\b",
        r"\b(?:reports?|reporting)\b.{0,50}\b(?:finance|operations?)\b",
    )
    return any(
        re.search(pattern, sentence, re.IGNORECASE)
        for pattern in patterns
    )


def _is_negated(sentence: str) -> bool:
    return any(
        pattern.search(sentence)
        for pattern in NEGATION_PATTERNS
    )


def _matches(
    sentence: str,
    patterns: tuple[re.Pattern[str], ...],
) -> bool:
    return any(
        pattern.search(sentence)
        for pattern in patterns
    )


def _make_signal(
    *,
    canonical_job_id: str,
    signal_type: str,
    level: SignalLevel,
    stage: RecruitmentStage,
    evidence_ref: str,
    observed_at: datetime,
) -> TrustSignal:
    fingerprint = signal_fingerprint(
        canonical_job_id=canonical_job_id,
        signal_type=signal_type,
        evidence_ref=evidence_ref,
    )

    return TrustSignal(
        signal_id=_signal_id(fingerprint),
        canonical_job_id=canonical_job_id,
        signal_type=signal_type,
        level=level,
        status=SignalStatus.ACTIVE,
        confidence=1.0,
        detection_method=DetectionMethod.RULE,
        context_stage=stage,
        evidence_refs=(evidence_ref,),
        extractor_version=EXTRACTOR_VERSION,
        fingerprint=fingerprint,
        first_seen_at=observed_at,
        last_seen_at=observed_at,
    )



CONTRAST_SPLIT_RE = re.compile(
    r"\s*(?:;|\b(?:tetapi|namun|akan\s+tetapi|but|however)\b)\s*",
    re.IGNORECASE,
)

REQUEST_ACTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:kirim(?:kan)?|dikirim|berikan|diberikan|beri|bagikan)\b",
        r"\b(?:share|send|give|provide|forward|tell)\b",
        r"\b(?:masukkan|input|enter|upload|unggah|submit|sampaikan)\b",
        r"\b(?:bayar|transfer)\b",
    )
)

PAYMENT_RECRUITMENT_CONTEXT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:interview|screening|seleksi|rekrutmen|recruitment)\b",
        r"\b(?:lamaran|application|kandidat|candidate|recruiter)\b",
        r"\b(?:training|onboarding|administrasi|admin)\b",
    )
)

EXPLICIT_RECRUITMENT_FEE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bbiaya\s+(?:administrasi|admin|rekrutmen|training)\b",
        r"\b(?:application|recruitment|training)\s+fee\b",
        r"\bdeposit\s+training\b",
        r"\buang\s+komitmen\b",
        r"\bjaminan\s+training\b",
    )
)


def _clauses(sentence: str) -> list[str]:
    return [
        part.strip(" ,")
        for part in CONTRAST_SPLIT_RE.split(sentence)
        if part.strip(" ,")
    ]


def _has_request_action(text: str) -> bool:
    return any(
        pattern.search(text)
        for pattern in REQUEST_ACTION_PATTERNS
    )


def _is_recruitment_payment_request(text: str) -> bool:
    if not _matches(text, PAYMENT_PATTERNS):
        return False

    if _has_request_action(text):
        return True

    if _matches(text, EXPLICIT_RECRUITMENT_FEE_PATTERNS):
        return True

    has_amount = re.search(
        r"\b(?:rp|idr)\s*[\d.,]+",
        text,
        re.IGNORECASE,
    )

    has_recruitment_context = _matches(
        text,
        PAYMENT_RECRUITMENT_CONTEXT_PATTERNS,
    )

    return bool(has_amount and has_recruitment_context)


def _is_sensitive_request(
    text: str,
    patterns: tuple[re.Pattern[str], ...],
) -> bool:
    if not _matches(text, patterns):
        return False

    if _has_request_action(text):
        return True

    return SECRET_VALUE_PATTERN.search(text) is not None



def extract_deterministic_signals(
    *,
    canonical_job_id: str,
    text: str,
    stage: RecruitmentStage,
    evidence_ref: str,
    observed_at: datetime,
) -> list[TrustSignal]:
    detected: dict[str, SignalLevel] = {}

    for sentence in _sentences(text):
        if _is_technical_context(sentence):
            continue
        for clause in _clauses(sentence):
            if _is_negated(clause):
                continue

            if _is_recruitment_payment_request(clause):
                detected["RECRUITMENT_PAYMENT"] = SignalLevel.L3

            if _is_sensitive_request(clause, OTP_PATTERNS):
                detected["OTP_REQUEST"] = SignalLevel.L4

            if _is_sensitive_request(clause, PIN_PATTERNS):
                detected["PIN_REQUEST"] = SignalLevel.L4

            if _is_sensitive_request(clause, PASSWORD_PATTERNS):
                detected["PASSWORD_REQUEST"] = SignalLevel.L4

            if _is_sensitive_request(clause, RECOVERY_CODE_PATTERNS):
                detected["RECOVERY_CODE_REQUEST"] = SignalLevel.L4

            if _is_sensitive_request(clause, AUTH_SECRET_PATTERNS):
                detected[
                    "AUTHENTICATION_SECRET_REQUEST"
                ] = SignalLevel.L4

            if (
                stage in EARLY_SENSITIVE_STAGES
                and _matches(clause, IDENTITY_DOCUMENT_PATTERNS)
            ):
                detected[
                    "EARLY_IDENTITY_DOCUMENT"
                ] = SignalLevel.L3

            if (
                stage in EARLY_SENSITIVE_STAGES
                and _matches(clause, BANK_DATA_PATTERNS)
            ):
                detected["EARLY_BANK_DATA"] = SignalLevel.L3

            if _matches(clause, CARD_IMAGE_PATTERNS):
                detected["CARD_IMAGE_REQUEST"] = SignalLevel.L3

    return [
        _make_signal(
            canonical_job_id=canonical_job_id,
            signal_type=signal_type,
            level=level,
            stage=stage,
            evidence_ref=evidence_ref,
            observed_at=observed_at,
        )
        for signal_type, level in sorted(detected.items())
    ]
