from onejob.career_twin.ontology import Predicate
from onejob.career_twin.resolution import (
    ValueRelationship,
    classify_value_relationship,
    is_duplicate,
    normalized_value_fingerprint,
)


# ---------------------------------------------------------------------------
# Relationship classification (spec section 10)
# ---------------------------------------------------------------------------


def test_identical_values():
    rel = classify_value_relationship(
        Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
        current="PERMANENT",
        proposed="PERMANENT",
    )
    assert rel is ValueRelationship.IDENTICAL


def test_equivalent_by_normalization_whitespace_case():
    rel = classify_value_relationship(
        Predicate.EXPERIENCE_LOCATION,
        current="Cikarang",
        proposed="  cikarang ",
    )
    assert rel is ValueRelationship.EQUIVALENT


def test_equivalent_skill_alias():
    rel = classify_value_relationship(
        Predicate.SKILL_NAME,
        current="Microsoft Excel",
        proposed="MS Excel",
    )
    assert rel is ValueRelationship.EQUIVALENT


def test_more_specific_is_advisory_not_identical():
    rel = classify_value_relationship(
        Predicate.EXPERIENCE_ROLE,
        current="Operator",
        proposed="Operator Stamping",
    )
    assert rel is ValueRelationship.MORE_SPECIFIC


def test_less_specific_detected():
    rel = classify_value_relationship(
        Predicate.EXPERIENCE_ROLE,
        current="Operator Stamping",
        proposed="Operator",
    )
    assert rel is ValueRelationship.LESS_SPECIFIC


def test_cardinality_many_different_values_are_compatible_not_conflict():
    # EXPERIENCE_RESPONSIBILITY is cardinality-MANY.
    rel = classify_value_relationship(
        Predicate.EXPERIENCE_RESPONSIBILITY,
        current="Operate stamping machine",
        proposed="Inspect product quality",
    )
    assert rel is ValueRelationship.COMPATIBLE


def test_cardinality_one_incompatible_values_conflict():
    # EXPERIENCE_EMPLOYMENT_TYPE is cardinality-ONE.
    rel = classify_value_relationship(
        Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
        current="PERMANENT",
        proposed="CONTRACT",
    )
    assert rel is ValueRelationship.CONFLICTING


def test_unknown_when_current_missing():
    rel = classify_value_relationship(
        Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
        current=None,
        proposed="PERMANENT",
    )
    assert rel is ValueRelationship.UNKNOWN


# ---------------------------------------------------------------------------
# Normalized fingerprint
# ---------------------------------------------------------------------------


def test_fingerprint_stable_across_formatting():
    a = normalized_value_fingerprint(
        Predicate.EXPERIENCE_LOCATION, "Cikarang"
    )
    b = normalized_value_fingerprint(
        Predicate.EXPERIENCE_LOCATION, "  cikarang  "
    )
    assert a == b


def test_fingerprint_differs_for_different_predicate():
    a = normalized_value_fingerprint(
        Predicate.EXPERIENCE_LOCATION, "cikarang"
    )
    b = normalized_value_fingerprint(
        Predicate.EDUCATION_INSTITUTION, "cikarang"
    )
    assert a != b


def test_fingerprint_uses_skill_alias_canonicalization():
    a = normalized_value_fingerprint(Predicate.SKILL_NAME, "Microsoft Excel")
    b = normalized_value_fingerprint(Predicate.SKILL_NAME, "MS Excel")
    assert a == b


# ---------------------------------------------------------------------------
# Duplicate detection (spec section 11)
# ---------------------------------------------------------------------------


def test_duplicate_requires_same_entity_predicate_and_value():
    assert is_duplicate(
        resolved_entity_id_a="experience-1",
        predicate_a=Predicate.EXPERIENCE_ROLE,
        value_a="Operator Stamping",
        resolved_entity_id_b="experience-1",
        predicate_b=Predicate.EXPERIENCE_ROLE,
        value_b="operator stamping",
    )


def test_not_duplicate_when_entity_differs():
    assert not is_duplicate(
        resolved_entity_id_a="experience-1",
        predicate_a=Predicate.EXPERIENCE_ROLE,
        value_a="Operator Stamping",
        resolved_entity_id_b="experience-2",
        predicate_b=Predicate.EXPERIENCE_ROLE,
        value_b="Operator Stamping",
    )


def test_not_duplicate_when_unresolved_entity():
    # Source duplication alone is not enough: an unresolved entity cannot be
    # asserted a duplicate.
    assert not is_duplicate(
        resolved_entity_id_a=None,
        predicate_a=Predicate.EXPERIENCE_ROLE,
        value_a="Operator Stamping",
        resolved_entity_id_b=None,
        predicate_b=Predicate.EXPERIENCE_ROLE,
        value_b="Operator Stamping",
    )


def test_not_duplicate_when_only_text_similar_but_more_specific():
    assert not is_duplicate(
        resolved_entity_id_a="experience-1",
        predicate_a=Predicate.EXPERIENCE_ROLE,
        value_a="Operator",
        resolved_entity_id_b="experience-1",
        predicate_b=Predicate.EXPERIENCE_ROLE,
        value_b="Operator Stamping",
    )
