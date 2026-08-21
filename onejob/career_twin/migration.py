from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Protocol

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
    predicate_spec,
)
from onejob.career_twin.repositories import (
    CareerClaimRepository,
    CareerEntityRepository,
    CareerTwinRepository,
)
from onejob.profile import CareerTwin


class IdFactory(Protocol):
    def __call__(self, kind: str) -> str:
        ...


class LegacyMigrationConflict(RuntimeError):
    def __init__(self, user_id: str):
        self.user_id = user_id
        super().__init__(
            f"legacy profile changed after migration: {user_id}"
        )


def fingerprint_json(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


class LegacyProfileImporter:
    def __init__(
        self,
        *,
        id_factory: IdFactory,
    ):
        self.id_factory = id_factory
        self.twins = CareerTwinRepository()
        self.entities = CareerEntityRepository()
        self.claims = CareerClaimRepository()

    def _entity(
        self,
        conn: sqlite3.Connection,
        *,
        twin_id: str,
        entity_type: EntityType,
        now: datetime,
    ) -> CareerEntity:
        entity = CareerEntity(
            entity_id=self.id_factory("entity"),
            twin_id=twin_id,
            entity_type=entity_type,
            lifecycle_state=EntityLifecycle.ACTIVE,
            created_at=now,
        )

        self.entities.insert(conn, entity)
        return entity

    def _claim(
        self,
        conn: sqlite3.Connection,
        *,
        twin_id: str,
        entity_id: str,
        predicate: Predicate,
        value: object,
        family_suffix: str = "",
        now: datetime,
    ) -> CareerClaim:
        spec = predicate_spec(predicate)
        claim_id = self.id_factory("claim")

        claim = CareerClaim(
            claim_id=claim_id,
            claim_family_id=(
                f"{entity_id}:{predicate.value}"
                f"{family_suffix}"
            ),
            twin_id=twin_id,
            subject_entity_id=entity_id,
            predicate=predicate,
            object_kind=(
                "ENTITY_REF"
                if spec.value_type.endswith("_REF")
                else "VALUE"
            ),
            value=value,
            value_type=spec.value_type,
            approval_state=ApprovalState.APPROVED,
            lifecycle_state=ClaimLifecycle.ACTIVE,
            ontology_version=ONTOLOGY_VERSION,
            created_at=now,
            approved_at=now,
        )

        self.claims.append(conn, claim)
        return claim

    def _previous(
        self,
        conn: sqlite3.Connection,
        user_id: str,
    ):
        return conn.execute(
            """
            SELECT twin_id, input_fingerprint
            FROM career_legacy_imports
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

    def import_profile(
        self,
        conn: sqlite3.Connection,
        *,
        user_id: str,
        legacy: CareerTwin,
    ) -> str:
        factual = {
            "name": legacy.name,
            "skills": sorted(legacy.skills),
            "experiences": [
                exp.model_dump(mode="json")
                for exp in legacy.experiences
            ],
        }

        fingerprint = fingerprint_json(factual)
        previous = self._previous(conn, user_id)

        if previous is not None:
            if previous["input_fingerprint"] == fingerprint:
                return previous["twin_id"]

            raise LegacyMigrationConflict(user_id)

        now = datetime.now(timezone.utc)
        twin_id = self.id_factory("twin")

        self.twins.ensure_twin(
            conn,
            twin_id,
            user_id,
            ONTOLOGY_VERSION,
        )

        person = self._entity(
            conn,
            twin_id=twin_id,
            entity_type=EntityType.PERSON,
            now=now,
        )

        self._claim(
            conn,
            twin_id=twin_id,
            entity_id=person.entity_id,
            predicate=Predicate.PERSON_DISPLAY_NAME,
            value=legacy.name,
            now=now,
        )

        all_skills = set(legacy.skills)

        for experience in legacy.experiences:
            all_skills.update(experience.skills)

        skill_entities = {}

        for skill_name in sorted(all_skills):
            skill = self._entity(
                conn,
                twin_id=twin_id,
                entity_type=EntityType.SKILL,
                now=now,
            )

            skill_entities[skill_name] = skill.entity_id

            self._claim(
                conn,
                twin_id=twin_id,
                entity_id=skill.entity_id,
                predicate=Predicate.SKILL_NAME,
                value=skill_name,
                now=now,
            )

        for experience in legacy.experiences:
            experience_entity = self._entity(
                conn,
                twin_id=twin_id,
                entity_type=EntityType.EXPERIENCE,
                now=now,
            )

            role = self._entity(
                conn,
                twin_id=twin_id,
                entity_type=EntityType.ROLE,
                now=now,
            )

            self._claim(
                conn,
                twin_id=twin_id,
                entity_id=role.entity_id,
                predicate=Predicate.ROLE_NAME,
                value=experience.title,
                now=now,
            )

            self._claim(
                conn,
                twin_id=twin_id,
                entity_id=experience_entity.entity_id,
                predicate=Predicate.EXPERIENCE_ROLE,
                value=role.entity_id,
                now=now,
            )

            self._claim(
                conn,
                twin_id=twin_id,
                entity_id=experience_entity.entity_id,
                predicate=Predicate.EXPERIENCE_DURATION_MONTHS,
                value=experience.months,
                now=now,
            )

            for index, responsibility in enumerate(
                experience.responsibilities
            ):
                self._claim(
                    conn,
                    twin_id=twin_id,
                    entity_id=experience_entity.entity_id,
                    predicate=Predicate.EXPERIENCE_RESPONSIBILITY,
                    value=responsibility,
                    family_suffix=f":{index}",
                    now=now,
                )

            for index, skill_name in enumerate(
                experience.skills
            ):
                self._claim(
                    conn,
                    twin_id=twin_id,
                    entity_id=experience_entity.entity_id,
                    predicate=Predicate.EXPERIENCE_SKILL_USED,
                    value=skill_entities[skill_name],
                    family_suffix=f":{index}",
                    now=now,
                )

        conn.execute(
            """
            INSERT INTO career_legacy_imports (
                user_id,
                twin_id,
                input_fingerprint,
                imported_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                twin_id,
                fingerprint,
                now.isoformat(),
            ),
        )

        return twin_id
