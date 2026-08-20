from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import sqlite3

from .models import (
    ActionDecision,
    ActionMode,
    TrustClassification,
)
from .repository import TrustRepository


PAYMENT_ACTIONS = frozenset(
    {
        "RECRUITMENT_PAYMENT",
        "TRANSFER_PAYMENT",
        "PAY_DEPOSIT",
        "PAY_RECRUITMENT_FEE",
    }
)

CREDENTIAL_ACTIONS = frozenset(
    {
        "SEND_OTP",
        "SEND_PIN",
        "SEND_PASSWORD",
        "SEND_RECOVERY_CODE",
        "SEND_AUTHENTICATION_SECRET",
    }
)

SENSITIVE_DOCUMENT_ACTIONS = frozenset(
    {
        "UPLOAD_KTP",
        "UPLOAD_KK",
        "UPLOAD_NPWP",
        "UPLOAD_BANK_ACCOUNT",
        "UPLOAD_ID_DOCUMENT",
    }
)


@dataclass(frozen=True)
class SafetySwitches:
    autopilot_enabled: bool = False
    sensitive_document_automation: bool = False

    # Deliberately non-configurable in v1 behavior.
    payment_actions: bool = False
    credential_actions: bool = False


@dataclass(frozen=True)
class AuthorizationRequest:
    request_id: str
    user_id: str
    canonical_job_id: str
    company_id: str
    action_type: str
    requested_mode: ActionMode
    consent_scope: str | None


@dataclass(frozen=True)
class AuthorizationResult:
    decision: ActionDecision
    reason_codes: tuple[str, ...]
    evaluation_id: str | None
    consent_id: str | None = None


def _deny(
    *reasons: str,
    evaluation_id: str | None = None,
) -> AuthorizationResult:
    return AuthorizationResult(
        decision=ActionDecision.DENIED,
        reason_codes=tuple(reasons),
        evaluation_id=evaluation_id,
        consent_id=None,
    )


def _is_sensitive(action_type: str) -> bool:
    return action_type in SENSITIVE_DOCUMENT_ACTIONS


def _mode_action(
    mode: ActionMode,
) -> str:
    if mode is ActionMode.AUTOPILOT:
        return "AUTOPILOT_SUBMIT"

    if mode is ActionMode.ASSISTED:
        return "ASSISTED_SUBMIT"

    return "MANUAL_REVIEW"


def authorize_action(
    conn: sqlite3.Connection,
    repo: TrustRepository,
    request: AuthorizationRequest,
    *,
    now: datetime,
    switches: SafetySwitches = SafetySwitches(),
) -> AuthorizationResult:

    # --------------------------------------------------
    # Non-overridable v1 barriers
    # --------------------------------------------------

    if request.action_type in PAYMENT_ACTIONS:
        return _deny(
            "PAYMENT_ACTION_PERMANENTLY_DISABLED"
        )

    if request.action_type in CREDENTIAL_ACTIONS:
        return _deny(
            "CREDENTIAL_ACTION_PERMANENTLY_DISABLED"
        )

    if (
        request.requested_mode is ActionMode.AUTOPILOT
        and not switches.autopilot_enabled
    ):
        return _deny("AUTOPILOT_KILL_SWITCH")

    if (
        _is_sensitive(request.action_type)
        and not switches.sensitive_document_automation
    ):
        return _deny(
            "SENSITIVE_DOCUMENT_AUTOMATION_DISABLED"
        )

    # --------------------------------------------------
    # Current trust snapshot
    # --------------------------------------------------

    evaluation = repo.latest_evaluation(
        conn,
        request.canonical_job_id,
    )

    if evaluation is None:
        return _deny("NO_TRUST_EVALUATION")

    evaluation_id = evaluation.evaluation_id

    if (
        evaluation.policy_version != "trust-v1"
    ):
        return _deny(
            "TRUST_POLICY_VERSION_MISMATCH",
            evaluation_id=evaluation_id,
        )

    if (
        evaluation.valid_until is None
        or now >= evaluation.valid_until
    ):
        return _deny(
            "TRUST_EVALUATION_STALE",
            evaluation_id=evaluation_id,
        )

    # --------------------------------------------------
    # Classification + allowed action contract
    # --------------------------------------------------

    required_action = _mode_action(
        request.requested_mode
    )

    if (
        request.requested_mode is ActionMode.AUTOPILOT
        and evaluation.classification
        is not TrustClassification.AUTOPILOT_ELIGIBLE
    ):
        return _deny(
            "TRUST_POLICY_DENIED_ACTION",
            evaluation_id=evaluation_id,
        )

    if (
        request.requested_mode is ActionMode.ASSISTED
        and evaluation.classification
        not in {
            TrustClassification.AUTOPILOT_ELIGIBLE,
            TrustClassification.ASSISTED_ALLOWED,
        }
    ):
        return _deny(
            "TRUST_POLICY_DENIED_ACTION",
            evaluation_id=evaluation_id,
        )

    if required_action in evaluation.blocked_actions:
        return _deny(
            "TRUST_POLICY_DENIED_ACTION",
            evaluation_id=evaluation_id,
        )

    # --------------------------------------------------
    # Sensitive data requires exact scoped consent
    # --------------------------------------------------

    consent_id = None

    if _is_sensitive(request.action_type):

        if request.consent_scope is None:
            return _deny(
                "CONSENT_REQUIRED",
                evaluation_id=evaluation_id,
            )

        consent = repo.get_valid_consent(
            conn,
            user_id=request.user_id,
            canonical_job_id=request.canonical_job_id,
            scope=request.consent_scope,
            now=now,
        )

        if consent is None:
            return _deny(
                "CONSENT_REQUIRED",
                evaluation_id=evaluation_id,
            )

        if consent.company_id != request.company_id:
            return _deny(
                "CONSENT_CONTEXT_MISMATCH",
                evaluation_id=evaluation_id,
            )

        if (
            consent.recruitment_stage
            is not evaluation.recruitment_stage
        ):
            return _deny(
                "CONSENT_CONTEXT_MISMATCH",
                evaluation_id=evaluation_id,
            )

        consent_id = consent.consent_id

    # --------------------------------------------------
    # Audit-before-authorization
    # --------------------------------------------------

    try:
        repo.append_action_event(
            conn,
            action_event_id=request.request_id,
            canonical_job_id=request.canonical_job_id,
            evaluation_id=evaluation_id,
            action_type=request.action_type,
            requested_mode=request.requested_mode.value,
            result="ALLOWED",
            reason_codes=("AUTHORIZED",),
            consent_id=consent_id,
            override_id=None,
            occurred_at=now,
        )
    except sqlite3.Error:
        return _deny(
            "AUDIT_PERSISTENCE_FAILED",
            evaluation_id=evaluation_id,
        )

    return AuthorizationResult(
        decision=ActionDecision.ALLOWED,
        reason_codes=("AUTHORIZED",),
        evaluation_id=evaluation_id,
        consent_id=consent_id,
    )
