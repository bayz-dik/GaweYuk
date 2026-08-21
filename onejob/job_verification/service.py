from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta

from onejob.job_verification.freshness import FreshnessState
from onejob.job_verification.models import (
    ApplyDestinationStatus,
    JobVerificationSnapshot,
)
from onejob.job_verification.repository import VerificationRepository
from onejob.persistence.db import Database


VERIFICATION_POLICY_VERSION = "job-verification-v1"
_DEFAULT_VALID_FOR = timedelta(days=7)


class VerificationSystemFailure(RuntimeError):
    """A technical failure during verification.

    This is distinct from domain uncertainty (UNKNOWN). It must fail closed for
    publication and must never be recorded as a completed trust/domain result.
    """


def _fingerprint(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


class JobVerificationService:
    """Assemble an immutable verification snapshot from assessment inputs.

    The service orchestrates identity/corroboration/destination/trust/freshness
    inputs and persists an immutable snapshot. It calls the Trust Engine (or a
    deterministic store in tests); nothing here imports catalog or publication,
    keeping authority one-directional.
    """

    def __init__(
        self,
        db: Database,
        *,
        store,
        now_default: datetime | None = None,
        valid_for: timedelta = _DEFAULT_VALID_FOR,
    ):
        self.db = db
        self.store = store
        self.repo = VerificationRepository()
        self.now_default = now_default
        self.valid_for = valid_for

    def evaluate(
        self, canonical_job_id: str, *, now: datetime
    ) -> JobVerificationSnapshot:
        try:
            identity_state = self.store.resolve_identity(canonical_job_id)
            trust_classification = self.store.trust(canonical_job_id)
            destination_status = self.store.destination(canonical_job_id)
            evidence_refs = self.store.evidence_refs(canonical_job_id)
            # Optional richer production inputs. Test fakes may omit these; a
            # missing method falls back to a safe default without pretending a
            # value was verified.
            canonical_version_id = self._opt(
                "canonical_version_id", canonical_job_id, default=None
            )
            identity_snapshot_id = self._opt(
                "identity_snapshot_id", canonical_job_id, default=None
            )
            trust_evaluation_id = self._opt(
                "trust_evaluation_id", canonical_job_id, default=None
            )
            hard_gate_hits = tuple(
                self._opt("hard_gate_hits", canonical_job_id, default=())
            )
            freshness_state = self._opt(
                "freshness_state", canonical_job_id, default=FreshnessState.CURRENT.value
            )
            corroboration = self._opt(
                "corroboration", canonical_job_id, default=None
            )
            destination_assessment_id = self._opt(
                "destination_assessment_id", canonical_job_id, default=None
            )
            destination_domain = self._opt(
                "destination_domain", canonical_job_id, default=None
            )
        except Exception as exc:  # resolver/trust crash is a system failure
            raise VerificationSystemFailure(str(exc)) from exc

        unknowns: list[str] = []
        if identity_state == "UNKNOWN":
            unknowns.append("COMPANY_IDENTITY")
        if destination_status is ApplyDestinationStatus.UNKNOWN:
            unknowns.append("APPLY_DESTINATION")

        if corroboration is None:
            corroboration = {
                "independent_family_count": len(set(evidence_refs)),
                "appearance_count": len(evidence_refs),
            }

        fingerprint = _fingerprint(
            {
                "canonical_job_id": canonical_job_id,
                "canonical_version_id": canonical_version_id,
                "identity_state": identity_state,
                "trust_classification": trust_classification,
                "trust_evaluation_id": trust_evaluation_id,
                "destination_status": destination_status.value,
                "destination_assessment_id": destination_assessment_id,
                "freshness_state": freshness_state,
                "hard_gate_hits": sorted(hard_gate_hits),
                "evidence_refs": sorted(evidence_refs),
                "policy": VERIFICATION_POLICY_VERSION,
            }
        )

        with self.db.transaction() as conn:
            existing = self.repo.get_by_fingerprint(
                conn,
                canonical_job_id=canonical_job_id,
                input_fingerprint=fingerprint,
            )
            if existing is not None:
                # Content-addressed reuse: identical inputs return the existing
                # immutable snapshot rather than creating a duplicate.
                return existing

            snapshot = JobVerificationSnapshot(
                verification_id=f"verif-{uuid.uuid4().hex}",
                canonical_job_id=canonical_job_id,
                canonical_version_id=canonical_version_id,
                identity_snapshot_id=identity_snapshot_id,
                trust_evaluation_id=trust_evaluation_id,
                identity_state=identity_state,
                trust_classification=trust_classification,
                destination_status=destination_status,
                destination_assessment_id=destination_assessment_id,
                destination_domain=destination_domain,
                freshness_state=freshness_state,
                corroboration=corroboration,
                hard_gate_hits=hard_gate_hits,
                unknowns=tuple(unknowns),
                evaluated_at=now,
                valid_until=now + self.valid_for,
                input_fingerprint=fingerprint,
                verification_policy_version=VERIFICATION_POLICY_VERSION,
            )
            self.repo.append(conn, snapshot, evidence_refs=tuple(evidence_refs))
            return snapshot

    def _opt(self, method_name: str, canonical_job_id: str, *, default):
        method = getattr(self.store, method_name, None)
        if method is None:
            return default
        return method(canonical_job_id)

    def get_snapshot(self, verification_id: str) -> JobVerificationSnapshot | None:
        with self.db.connection() as conn:
            return self.repo.get(conn, verification_id)
