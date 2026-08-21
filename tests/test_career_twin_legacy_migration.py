from onejob.career_twin.migration import LegacyProfileImporter
from onejob.career_twin.ontology import Predicate
from onejob.persistence.db import Database
from onejob.profile import CareerTwin, WorkExperience


class SequentialIds:
    def __init__(self):
        self.counts = {}

    def __call__(self, kind: str) -> str:
        number = self.counts.get(kind, 0) + 1
        self.counts[kind] = number
        return f"{kind}-{number}"


def legacy_profile() -> CareerTwin:
    return CareerTwin(
        name="Bayu",
        skills=[
            "machine operation",
            "quality inspection",
        ],
        preferred_roles=[
            "production operator",
        ],
        preferred_locations=[
            "cikarang",
        ],
        experiences=[
            WorkExperience(
                title="Operator Stamping",
                months=20,
                skills=[
                    "machine operation",
                    "quality inspection",
                ],
                responsibilities=[
                    "Operate stamping machine",
                    "Inspect product quality",
                ],
            ),
        ],
        expected_salary=6200000,
        available_in_days=0,
    )


def test_legacy_import_is_idempotent_and_preserves_duration_without_dates(
    tmp_path,
):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()

    importer = LegacyProfileImporter(
        id_factory=SequentialIds(),
    )

    legacy = legacy_profile()

    with db.transaction() as conn:
        first_twin_id = importer.import_profile(
            conn,
            user_id="user-1",
            legacy=legacy,
        )

    with db.transaction() as conn:
        second_twin_id = importer.import_profile(
            conn,
            user_id="user-1",
            legacy=legacy,
        )

    assert second_twin_id == first_twin_id

    with db.connection() as conn:
        twins = conn.execute(
            """
            SELECT COUNT(*)
            FROM career_twins
            WHERE user_id = ?
            """,
            ("user-1",),
        ).fetchone()[0]

        duration_claims = conn.execute(
            """
            SELECT value_json
            FROM career_claims
            WHERE twin_id = ?
              AND predicate = ?
              AND lifecycle_state = 'ACTIVE'
            """,
            (
                first_twin_id,
                Predicate.EXPERIENCE_DURATION_MONTHS.value,
            ),
        ).fetchall()

        invented_dates = conn.execute(
            """
            SELECT COUNT(*)
            FROM career_claims
            WHERE twin_id = ?
              AND predicate IN (?, ?)
            """,
            (
                first_twin_id,
                Predicate.EXPERIENCE_START_DATE.value,
                Predicate.EXPERIENCE_END_DATE.value,
            ),
        ).fetchone()[0]

        imports = conn.execute(
            """
            SELECT COUNT(*)
            FROM career_legacy_imports
            WHERE user_id = ?
            """,
            ("user-1",),
        ).fetchone()[0]

    assert twins == 1
    assert len(duration_claims) == 1
    assert duration_claims[0]["value_json"] == "20"
    assert invented_dates == 0
    assert imports == 1


def test_projection_preserves_all_many_cardinality_claims(tmp_path):
    from onejob.career_twin.projection import ProjectionService

    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()

    importer = LegacyProfileImporter(
        id_factory=SequentialIds(),
    )

    with db.transaction() as conn:
        twin_id = importer.import_profile(
            conn,
            user_id="user-1",
            legacy=legacy_profile(),
        )

    projection = ProjectionService(db).build(twin_id)

    experience_entities = [
        entity
        for entity in projection.entities.values()
        if "EXPERIENCE.DURATION_MONTHS" in entity
    ]

    assert len(experience_entities) == 1

    experience = experience_entities[0]

    assert experience["EXPERIENCE.RESPONSIBILITY"] == [
        "Operate stamping machine",
        "Inspect product quality",
    ]

    assert len(
        experience["EXPERIENCE.SKILL_USED"]
    ) == 2


def test_legacy_adapter_round_trips_facts_and_uses_explicit_intent_fallback(
    tmp_path,
):
    from onejob.career_twin.projection import (
        LegacyCareerTwinProjection,
    )

    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()

    ids = SequentialIds()
    importer = LegacyProfileImporter(
        id_factory=ids,
    )

    original = legacy_profile()

    with db.transaction() as conn:
        twin_id = importer.import_profile(
            conn,
            user_id="user-1",
            legacy=original,
        )

    adapter = LegacyCareerTwinProjection(db)

    rebuilt = adapter.build(
        twin_id,
        legacy_intent_fallback=original,
    )

    assert rebuilt.name == original.name

    assert sorted(rebuilt.skills) == sorted(
        original.skills
    )

    assert len(rebuilt.experiences) == 1

    experience = rebuilt.experiences[0]

    assert experience.title == "Operator Stamping"
    assert experience.months == 20

    assert sorted(experience.skills) == sorted(
        [
            "machine operation",
            "quality inspection",
        ]
    )

    assert experience.responsibilities == [
        "Operate stamping machine",
        "Inspect product quality",
    ]

    # Temporary intent fallback remains explicit.
    assert rebuilt.preferred_roles == (
        original.preferred_roles
    )
    assert rebuilt.preferred_locations == (
        original.preferred_locations
    )
    assert rebuilt.expected_salary == (
        original.expected_salary
    )
    assert rebuilt.available_in_days == (
        original.available_in_days
    )


def test_legacy_import_rejects_changed_factual_payload(tmp_path):
    import pytest

    from onejob.career_twin.migration import (
        LegacyMigrationConflict,
    )

    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()

    importer = LegacyProfileImporter(
        id_factory=SequentialIds(),
    )

    original = legacy_profile()

    with db.transaction() as conn:
        twin_id = importer.import_profile(
            conn,
            user_id="user-1",
            legacy=original,
        )

    changed = original.model_copy(
        update={
            "skills": [
                *original.skills,
                "new-unapproved-skill",
            ],
        }
    )

    with pytest.raises(LegacyMigrationConflict):
        with db.transaction() as conn:
            importer.import_profile(
                conn,
                user_id="user-1",
                legacy=changed,
            )

    with db.connection() as conn:
        twin_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM career_twins
            WHERE user_id = ?
            """,
            ("user-1",),
        ).fetchone()[0]

        import_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM career_legacy_imports
            WHERE user_id = ?
            """,
            ("user-1",),
        ).fetchone()[0]

        stored_twin = conn.execute(
            """
            SELECT twin_id
            FROM career_legacy_imports
            WHERE user_id = ?
            """,
            ("user-1",),
        ).fetchone()

    assert twin_count == 1
    assert import_count == 1
    assert stored_twin["twin_id"] == twin_id
