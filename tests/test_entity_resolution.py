from onejob.career_twin.ontology import EntityType
from onejob.career_twin.resolution import (
    ConfidenceBand,
    EntityResolutionAssessment,
    ResolutionEntityInput,
    ResolutionCandidateInput,
    RESOLVER_ALGORITHM_VERSION,
    resolve_entity,
)


def experience_candidate(**attrs) -> ResolutionCandidateInput:
    base = {
        "company": "PT Astra Honda Motor",
        "role": "Operator Stamping",
        "start_date": "2020-01-01",
        "end_date": "2021-08-01",
    }
    base.update(attrs)
    return ResolutionCandidateInput(
        candidate_id="candidate-1",
        entity_type=EntityType.EXPERIENCE,
        attributes=base,
    )


def experience_entity(entity_id="experience-1", **attrs) -> ResolutionEntityInput:
    base = {
        "company": "PT Astra Honda Motor",
        "role": "Operator Stamping",
        "start_date": "2020-01-01",
        "end_date": "2021-08-01",
    }
    base.update(attrs)
    return ResolutionEntityInput(
        entity_id=entity_id,
        entity_type=EntityType.EXPERIENCE,
        attributes=base,
    )


# ---------------------------------------------------------------------------
# Common contract
# ---------------------------------------------------------------------------


def test_assessment_carries_algorithm_version_and_reasons():
    assessment = resolve_entity(
        experience_candidate(),
        [experience_entity()],
    )
    assert isinstance(assessment, EntityResolutionAssessment)
    assert assessment.algorithm_version == RESOLVER_ALGORITHM_VERSION
    # No opaque percentage alone: reasons must be present for a determination.
    assert assessment.reasons


def test_empty_canonical_set_is_low_not_false_certainty():
    assessment = resolve_entity(experience_candidate(), [])
    assert assessment.result is ConfidenceBand.LOW
    assert assessment.proposed_entity_id is None


# ---------------------------------------------------------------------------
# Hard contradiction outranks aggregate similarity (spec 8.2 / 24.2)
# ---------------------------------------------------------------------------


def test_same_company_role_but_contradictory_dates_does_not_auto_link():
    candidate = experience_candidate(
        start_date="2010-01-01",
        end_date="2011-01-01",
    )
    entity = experience_entity(
        start_date="2020-01-01",
        end_date="2021-08-01",
    )
    assessment = resolve_entity(candidate, [entity])

    # Strong date contradiction must veto the otherwise-high similarity.
    assert assessment.result is not ConfidenceBand.HIGH
    assert any("date" in r.lower() for r in assessment.reasons + assessment.warnings)


def test_overlapping_dates_with_same_company_and_role_auto_links():
    candidate = experience_candidate(
        start_date="2020-03-01",
        end_date="2021-06-01",
    )
    entity = experience_entity(
        start_date="2020-01-01",
        end_date="2021-08-01",
    )
    assessment = resolve_entity(candidate, [entity])
    assert assessment.result is ConfidenceBand.HIGH
    assert assessment.proposed_entity_id == "experience-1"


def test_missing_dates_require_review_medium():
    candidate = experience_candidate(start_date=None, end_date=None)
    entity = experience_entity(start_date=None, end_date=None)
    assessment = resolve_entity(candidate, [entity])
    assert assessment.result is ConfidenceBand.MEDIUM
    assert any("date" in w.lower() for w in assessment.warnings)


# ---------------------------------------------------------------------------
# Skill resolver: aliases classify as equivalent (spec 24.2)
# ---------------------------------------------------------------------------


def skill_candidate(name: str) -> ResolutionCandidateInput:
    return ResolutionCandidateInput(
        candidate_id="candidate-skill",
        entity_type=EntityType.SKILL,
        attributes={"name": name},
    )


def skill_entity(name: str, entity_id="skill-1") -> ResolutionEntityInput:
    return ResolutionEntityInput(
        entity_id=entity_id,
        entity_type=EntityType.SKILL,
        attributes={"name": name},
    )


def test_skill_exact_name_match_is_high():
    assessment = resolve_entity(
        skill_candidate("Machine Operation"),
        [skill_entity("machine operation")],
    )
    assert assessment.result is ConfidenceBand.HIGH
    assert assessment.proposed_entity_id == "skill-1"


def test_skill_known_alias_is_equivalent_high():
    assessment = resolve_entity(
        skill_candidate("MS Excel"),
        [skill_entity("Microsoft Excel")],
    )
    assert assessment.result is ConfidenceBand.HIGH
    assert any("alias" in r.lower() for r in assessment.reasons)


def test_skill_unrelated_name_is_low():
    assessment = resolve_entity(
        skill_candidate("Welding"),
        [skill_entity("Accounting")],
    )
    assert assessment.result is ConfidenceBand.LOW


# ---------------------------------------------------------------------------
# Entity-type resolver policies differ (spec 8.3 / 24.2)
# ---------------------------------------------------------------------------


def test_entity_type_policies_differ_between_skill_and_experience():
    # Same identical name -> HIGH for skill.
    skill = resolve_entity(
        skill_candidate("Operator Stamping"),
        [skill_entity("Operator Stamping")],
    )
    # But an experience with same role text and contradictory dates
    # must NOT be HIGH -- experience resolution requires date compatibility.
    experience = resolve_entity(
        experience_candidate(start_date="2005-01-01", end_date="2006-01-01"),
        [experience_entity(start_date="2020-01-01", end_date="2021-01-01")],
    )
    assert skill.result is ConfidenceBand.HIGH
    assert experience.result is not ConfidenceBand.HIGH


# ---------------------------------------------------------------------------
# Fail-safe: resolver failure returns UNKNOWN, not false certainty
# ---------------------------------------------------------------------------


def test_resolver_failure_returns_unknown():
    # A candidate with a broken attributes payload (raises on access) must
    # produce UNKNOWN rather than a confident wrong answer.
    class Exploding(dict):
        def get(self, *a, **k):
            raise RuntimeError("boom")

    candidate = ResolutionCandidateInput(
        candidate_id="candidate-x",
        entity_type=EntityType.EXPERIENCE,
        attributes=Exploding(),
    )
    assessment = resolve_entity(candidate, [experience_entity()])
    assert assessment.result is ConfidenceBand.UNKNOWN
    assert assessment.proposed_entity_id is None


# ---------------------------------------------------------------------------
# HIGH links routing only; it does not approve a claim (spec 24.2)
# ---------------------------------------------------------------------------


def test_high_result_only_proposes_routing_and_has_no_approval_authority():
    assessment = resolve_entity(experience_candidate(), [experience_entity()])
    assert assessment.result is ConfidenceBand.HIGH
    # The assessment surface exposes routing only: a proposed entity id.
    # There is no field that could approve/replace a claim.
    fields = set(assessment.__dataclass_fields__)
    assert "proposed_entity_id" in fields
    assert not (fields & {"approved", "claim_id", "canonical_claim", "approve"})
