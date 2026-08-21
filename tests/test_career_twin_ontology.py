from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from onejob.career_twin.models import (
    ApprovalState,
    CareerClaim,
    ClaimLifecycle,
)
from onejob.career_twin.ontology import (
    Cardinality,
    EntityType,
    Predicate,
    predicate_spec,
)


def make_claim() -> CareerClaim:
    return CareerClaim(
        claim_id="claim-1",
        claim_family_id="family-1",
        twin_id="twin-1",
        subject_entity_id="experience-1",
        predicate=Predicate.EXPERIENCE_ROLE,
        object_kind="ENTITY_REF",
        value="role-stamping-operator",
        value_type="ROLE_REF",
        approval_state=ApprovalState.APPROVED,
        lifecycle_state=ClaimLifecycle.ACTIVE,
        ontology_version="career-v1",
        created_at=datetime.now(timezone.utc),
        approved_at=datetime.now(timezone.utc),
    )


def test_experience_role_is_singular_and_typed():
    spec = predicate_spec(Predicate.EXPERIENCE_ROLE)

    assert spec.subject_type is EntityType.EXPERIENCE
    assert spec.cardinality is Cardinality.ONE
    assert spec.value_type == "ROLE_REF"


def test_unknown_predicate_is_not_accepted():
    with pytest.raises(ValueError):
        Predicate("EXPERIENCE.MADE_UP_FIELD")


def test_canonical_claim_is_immutable():
    claim = make_claim()

    with pytest.raises(ValidationError):
        claim.value = "changed"


def test_claim_confidence_is_not_mutable_claim_truth():
    claim = make_claim()

    assert not hasattr(claim, "claim_confidence")
