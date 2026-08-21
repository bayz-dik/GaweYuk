from onejob.career_twin.conflicts import (
    ConflictAlternative,
    build_conflict_clusters,
    should_open_conflict,
)
from onejob.career_twin.ontology import Predicate


# ---------------------------------------------------------------------------
# Conflict creation decision (spec 12.1)
# ---------------------------------------------------------------------------


def test_cardinality_one_incompatible_opens_conflict():
    assert should_open_conflict(
        Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
        current="PERMANENT",
        proposed="CONTRACT",
    )


def test_cardinality_many_compatible_does_not_open_conflict():
    assert not should_open_conflict(
        Predicate.EXPERIENCE_RESPONSIBILITY,
        current="Operate stamping machine",
        proposed="Inspect product quality",
    )


def test_equivalent_values_do_not_open_conflict():
    assert not should_open_conflict(
        Predicate.SKILL_NAME,
        current="Microsoft Excel",
        proposed="MS Excel",
    )


def test_more_specific_does_not_open_conflict():
    # MORE_SPECIFIC is advisory, not a conflict.
    assert not should_open_conflict(
        Predicate.EXPERIENCE_ROLE,
        current="Operator",
        proposed="Operator Stamping",
    )


def test_no_current_value_does_not_open_conflict():
    assert not should_open_conflict(
        Predicate.EXPERIENCE_EMPLOYMENT_TYPE,
        current=None,
        proposed="PERMANENT",
    )


# ---------------------------------------------------------------------------
# Candidate-value clustering (spec 12.2)
# ---------------------------------------------------------------------------


class FakeSuggestion:
    def __init__(self, suggestion_id, value, fingerprint, family):
        self.suggestion_id = suggestion_id
        self.proposed_value = value
        self.normalized_value_fingerprint = fingerprint
        self.evidence_family_id = family


def test_equivalent_suggestions_cluster_into_one_alternative():
    suggestions = [
        FakeSuggestion("s1", "Operator Stamping", "fp-a", "fam-1"),
        FakeSuggestion("s2", "operator stamping", "fp-a", "fam-2"),
        FakeSuggestion("s3", "Operator Stamping ", "fp-a", "fam-2"),
    ]

    clusters = build_conflict_clusters(
        Predicate.EXPERIENCE_ROLE, suggestions
    )

    assert len(clusters) == 1
    cluster = clusters[0]
    assert isinstance(cluster, ConflictAlternative)
    assert set(cluster.suggestion_ids) == {"s1", "s2", "s3"}


def test_distinct_values_form_distinct_clusters():
    suggestions = [
        FakeSuggestion("s1", "Operator Stamping", "fp-a", "fam-1"),
        FakeSuggestion("s2", "Operator Welding", "fp-b", "fam-2"),
    ]
    clusters = build_conflict_clusters(
        Predicate.EXPERIENCE_ROLE, suggestions
    )
    assert len(clusters) == 2


def test_cluster_counts_evidence_families_not_raw_source_count():
    # Three suggestions but only two distinct evidence families -> support of 2.
    suggestions = [
        FakeSuggestion("s1", "Operator Stamping", "fp-a", "fam-1"),
        FakeSuggestion("s2", "Operator Stamping", "fp-a", "fam-1"),
        FakeSuggestion("s3", "Operator Stamping", "fp-a", "fam-2"),
    ]
    clusters = build_conflict_clusters(
        Predicate.EXPERIENCE_ROLE, suggestions
    )
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.evidence_family_count == 2
    assert cluster.suggestion_count == 3


def test_cluster_preserves_provenance_of_each_suggestion():
    suggestions = [
        FakeSuggestion("s1", "Operator Stamping", "fp-a", "fam-1"),
        FakeSuggestion("s2", "Operator Stamping", "fp-a", "fam-2"),
    ]
    clusters = build_conflict_clusters(
        Predicate.EXPERIENCE_ROLE, suggestions
    )
    # Individual suggestion lineage is preserved inside the cluster.
    assert sorted(clusters[0].suggestion_ids) == ["s1", "s2"]
