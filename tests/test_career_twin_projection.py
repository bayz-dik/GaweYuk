from datetime import datetime, timezone

from onejob.career_twin.models import (
    ApprovalState,
    CareerClaim,
    CareerEntity,
    ClaimLifecycle,
    EntityLifecycle,
)
from onejob.career_twin.ontology import (
    EntityType,
    ONTOLOGY_VERSION,
    Predicate,
)
from onejob.career_twin.projection import ProjectionService
from onejob.career_twin.repositories import (
    CareerClaimRepository,
    CareerEntityRepository,
    CareerTwinRepository,
)
from onejob.persistence.db import Database


NOW = datetime(2026, 8, 21, 5, 0, tzinfo=timezone.utc)


def make_claim(
    *,
    claim_id: str,
    family_id: str,
    value: str,
    lifecycle: ClaimLifecycle = ClaimLifecycle.ACTIVE,
) -> CareerClaim:
    return CareerClaim(
        claim_id=claim_id,
        claim_family_id=family_id,
        twin_id="twin-1",
        subject_entity_id="experience-1",
        predicate=Predicate.EXPERIENCE_ROLE,
        object_kind="ENTITY_REF",
        value=value,
        value_type="ROLE_REF",
        approval_state=ApprovalState.APPROVED,
        lifecycle_state=lifecycle,
        ontology_version=ONTOLOGY_VERSION,
        created_at=NOW,
        approved_at=NOW,
        retired_at=(
            NOW
            if lifecycle is ClaimLifecycle.SUPERSEDED
            else None
        ),
    )


def seed_ledger(db: Database) -> None:
    twins = CareerTwinRepository()
    entities = CareerEntityRepository()
    claims = CareerClaimRepository()

    with db.transaction() as conn:
        twins.ensure_twin(
            conn,
            "twin-1",
            "user-1",
            ONTOLOGY_VERSION,
        )

        entities.insert(
            conn,
            CareerEntity(
                entity_id="experience-1",
                twin_id="twin-1",
                entity_type=EntityType.EXPERIENCE,
                lifecycle_state=EntityLifecycle.ACTIVE,
                created_at=NOW,
            ),
        )

        claims.append(
            conn,
            make_claim(
                claim_id="claim-old",
                family_id="family-role",
                value="role-production-operator",
                lifecycle=ClaimLifecycle.SUPERSEDED,
            ),
        )

        claims.append(
            conn,
            make_claim(
                claim_id="claim-current",
                family_id="family-role",
                value="role-stamping-operator",
            ),
        )


def test_projection_is_rebuildable_from_authoritative_ledger(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    seed_ledger(db)

    service = ProjectionService(db)

    first = service.rebuild_cache("twin-1")

    with db.connection() as conn:
        cached = conn.execute(
            """
            SELECT *
            FROM career_projection_cache
            WHERE twin_id = ?
            """,
            ("twin-1",),
        ).fetchone()

    assert cached is not None

    # Only approved + active + non-erased truth survives.
    assert first.active_claim_ids == (
        "claim-current",
    )

    assert first.entities["experience-1"]["EXPERIENCE.ROLE"] == (
        "role-stamping-operator"
    )

    first_fingerprint = first.input_fingerprint

    # Destroy the disposable read model.
    with db.transaction() as conn:
        conn.execute(
            """
            DELETE FROM career_projection_cache
            WHERE twin_id = ?
            """,
            ("twin-1",),
        )

    second = service.rebuild_cache("twin-1")

    # Ledger alone must reproduce the exact same projection.
    assert second == first
    assert second.input_fingerprint == first_fingerprint


def test_projection_ignores_corrupted_cache_and_rebuild_repairs_it(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    seed_ledger(db)

    service = ProjectionService(db)

    expected = service.rebuild_cache("twin-1")

    # Deliberately corrupt the disposable cache.
    with db.transaction() as conn:
        conn.execute(
            """
            UPDATE career_projection_cache
            SET input_fingerprint = 'CORRUPTED',
                payload_json = '{"fake":"truth"}'
            WHERE twin_id = ?
            """,
            ("twin-1",),
        )

    # build() must read authoritative ledger, never cache.
    from_ledger = service.build("twin-1")

    assert from_ledger == expected
    assert from_ledger.input_fingerprint != "CORRUPTED"

    # Rebuild must repair the disposable cache.
    repaired = service.rebuild_cache("twin-1")

    with db.connection() as conn:
        cached = conn.execute(
            """
            SELECT input_fingerprint, payload_json
            FROM career_projection_cache
            WHERE twin_id = ?
            """,
            ("twin-1",),
        ).fetchone()

    assert repaired == expected
    assert cached["input_fingerprint"] == expected.input_fingerprint
    assert "fake" not in cached["payload_json"]
