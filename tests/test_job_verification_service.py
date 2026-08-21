from datetime import datetime, timedelta, timezone

import pytest

from onejob.job_verification.freshness import FreshnessState
from onejob.job_verification.models import ApplyDestinationStatus
from onejob.job_verification.service import (
    JobVerificationService,
    VerificationSystemFailure,
)
from onejob.persistence.db import Database


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


class FakeStore:
    """Deterministic in-memory inputs for the verification service.

    The verification service consumes assessments (identity/corroboration/
    destination/trust/freshness) rather than owning them; the store lets a test
    mutate one input and prove snapshot reuse vs new-snapshot behavior.
    """

    def __init__(self):
        self._evidence = {"job-1": ["evidence-1"]}
        self.identity_state = {"job-1": "VERIFIED"}
        self.trust_classification = {"job-1": "AUTOPILOT_ELIGIBLE"}
        self.destination_status = {"job-1": ApplyDestinationStatus.VERIFIED}
        self.crash_identity = False

    def add_independent_evidence(self, job_id, evidence_id):
        self._evidence.setdefault(job_id, []).append(evidence_id)

    def evidence_refs(self, job_id):
        return tuple(self._evidence.get(job_id, ()))

    def resolve_identity(self, job_id):
        if self.crash_identity:
            raise RuntimeError("identity resolver down")
        return self.identity_state.get(job_id, "UNKNOWN")

    def trust(self, job_id):
        return self.trust_classification.get(job_id, "REVIEW_REQUIRED")

    def destination(self, job_id):
        return self.destination_status.get(job_id, ApplyDestinationStatus.UNKNOWN)


@pytest.fixture
def service(tmp_path):
    db = Database(tmp_path / "verif.db")
    db.initialize()
    store = FakeStore()
    svc = JobVerificationService(db, store=store, now_default=NOW)
    svc.fixture_store = store
    return svc


def test_identical_verification_inputs_reuse_snapshot_id(service):
    first = service.evaluate("job-1", now=NOW)
    second = service.evaluate("job-1", now=NOW)
    assert first.input_fingerprint == second.input_fingerprint
    assert first.verification_id == second.verification_id


def test_changed_evidence_creates_new_verification_snapshot(service):
    first = service.evaluate("job-1", now=NOW)
    service.fixture_store.add_independent_evidence("job-1", "evidence-2")
    second = service.evaluate("job-1", now=NOW)
    assert first.verification_id != second.verification_id
    assert first.input_fingerprint != second.input_fingerprint


def test_snapshot_has_validity_window(service):
    snapshot = service.evaluate("job-1", now=NOW)
    assert snapshot.evaluated_at == NOW
    assert snapshot.valid_until > NOW


def test_unknown_identity_is_domain_result_not_system_failure(service):
    service.fixture_store.identity_state["job-1"] = "UNKNOWN"
    snapshot = service.evaluate("job-1", now=NOW)
    assert "COMPANY_IDENTITY" in snapshot.unknowns


def test_identity_resolver_exception_is_system_failure(service):
    service.fixture_store.crash_identity = True
    with pytest.raises(VerificationSystemFailure):
        service.evaluate("job-1", now=NOW)


def test_snapshot_persisted_and_reloadable(service):
    snapshot = service.evaluate("job-1", now=NOW)
    reloaded = service.get_snapshot(snapshot.verification_id)
    assert reloaded is not None
    assert reloaded.verification_id == snapshot.verification_id


def test_freshness_state_enum_values():
    assert {s.value for s in FreshnessState} == {
        "CURRENT",
        "DUE_SOON",
        "EXPIRED",
        "CLOSED",
        "UNKNOWN",
    }
