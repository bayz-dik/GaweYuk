from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from onejob.career_twin.models import CareerClaim
from onejob.career_twin.ontology import (
    Cardinality,
    predicate_spec,
)
from onejob.career_twin.repositories import CareerClaimRepository
from onejob.persistence.db import Database


PROJECTION_VERSION = "career-projection-v1"


class CareerTwinProjection(BaseModel):
    model_config = ConfigDict(frozen=True)

    twin_id: str
    active_claim_ids: tuple[str, ...]
    entities: dict[str, dict[str, object]] = Field(
        default_factory=dict
    )
    input_fingerprint: str
    projection_version: str = PROJECTION_VERSION


class ProjectionService:
    def __init__(self, db: Database):
        self.db = db
        self.claims = CareerClaimRepository()

    @staticmethod
    def _canonical_payload(
        claims: tuple[CareerClaim, ...],
    ) -> list[dict[str, object]]:
        return [
            {
                "claim_id": claim.claim_id,
                "claim_family_id": claim.claim_family_id,
                "entity_id": claim.subject_entity_id,
                "predicate": claim.predicate.value,
                "value": claim.value,
                "value_type": claim.value_type,
            }
            for claim in claims
        ]

    @staticmethod
    def _materialize_entities(
        claims: tuple[CareerClaim, ...],
    ) -> dict[str, dict[str, object]]:
        entities: dict[str, dict[str, object]] = {}

        for claim in claims:
            entity = entities.setdefault(
                claim.subject_entity_id,
                {},
            )

            key = claim.predicate.value
            spec = predicate_spec(claim.predicate)

            if spec.cardinality is Cardinality.MANY:
                values = entity.setdefault(key, [])

                if not isinstance(values, list):
                    raise RuntimeError(
                        "projection cardinality collision: "
                        f"{claim.subject_entity_id=} "
                        f"{key=}"
                    )

                values.append(claim.value)
            else:
                entity[key] = claim.value

        return entities

    def _build_from_connection(
        self,
        conn,
        twin_id: str,
    ) -> CareerTwinProjection:
        claims = tuple(
            sorted(
                self.claims.list_active_for_twin(
                    conn,
                    twin_id,
                ),
                key=lambda claim: claim.claim_id,
            )
        )

        payload = self._canonical_payload(claims)

        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

        fingerprint = hashlib.sha256(
            encoded.encode("utf-8")
        ).hexdigest()

        return CareerTwinProjection(
            twin_id=twin_id,
            active_claim_ids=tuple(
                claim.claim_id
                for claim in claims
            ),
            entities=self._materialize_entities(claims),
            input_fingerprint=fingerprint,
        )

    def build(
        self,
        twin_id: str,
    ) -> CareerTwinProjection:
        with self.db.connection() as conn:
            return self._build_from_connection(
                conn,
                twin_id,
            )

    def rebuild_cache(
        self,
        twin_id: str,
    ) -> CareerTwinProjection:
        with self.db.transaction() as conn:
            projection = self._build_from_connection(
                conn,
                twin_id,
            )

            payload_json = projection.model_dump_json()

            conn.execute(
                """
                INSERT INTO career_projection_cache (
                    twin_id,
                    projection_version,
                    input_fingerprint,
                    payload_json,
                    built_at,
                    stale_at
                )
                VALUES (
                    ?,
                    ?,
                    ?,
                    ?,
                    datetime('now'),
                    NULL
                )
                ON CONFLICT(twin_id)
                DO UPDATE SET
                    projection_version = excluded.projection_version,
                    input_fingerprint = excluded.input_fingerprint,
                    payload_json = excluded.payload_json,
                    built_at = excluded.built_at,
                    stale_at = NULL
                """,
                (
                    twin_id,
                    projection.projection_version,
                    projection.input_fingerprint,
                    payload_json,
                ),
            )

            return projection


class LegacyCareerTwinProjection:
    def __init__(self, db: Database):
        self.db = db
        self.projections = ProjectionService(db)

    def build(
        self,
        twin_id: str,
        *,
        legacy_intent_fallback=None,
    ):
        from onejob.profile import (
            CareerTwin,
            WorkExperience,
        )

        projection = self.projections.build(twin_id)

        display_name = ""
        skill_names: dict[str, str] = {}
        role_names: dict[str, str] = {}

        for entity_id, entity in projection.entities.items():
            if "PERSON.DISPLAY_NAME" in entity:
                display_name = str(
                    entity["PERSON.DISPLAY_NAME"]
                )

            if "SKILL.NAME" in entity:
                skill_names[entity_id] = str(
                    entity["SKILL.NAME"]
                )

            if "ROLE.NAME" in entity:
                role_names[entity_id] = str(
                    entity["ROLE.NAME"]
                )

        experiences = []

        for entity in projection.entities.values():
            if "EXPERIENCE.ROLE" not in entity:
                continue

            role_ref = str(entity["EXPERIENCE.ROLE"])

            skill_refs = entity.get(
                "EXPERIENCE.SKILL_USED",
                [],
            )
            if not isinstance(skill_refs, list):
                skill_refs = [skill_refs]

            responsibilities = entity.get(
                "EXPERIENCE.RESPONSIBILITY",
                [],
            )
            if not isinstance(responsibilities, list):
                responsibilities = [responsibilities]

            experiences.append(
                WorkExperience(
                    title=role_names.get(
                        role_ref,
                        role_ref,
                    ),
                    months=int(
                        entity.get(
                            "EXPERIENCE.DURATION_MONTHS",
                            0,
                        )
                    ),
                    skills=[
                        skill_names.get(
                            str(ref),
                            str(ref),
                        )
                        for ref in skill_refs
                    ],
                    responsibilities=[
                        str(value)
                        for value in responsibilities
                    ],
                )
            )

        intent = (
            legacy_intent_fallback
            if legacy_intent_fallback is not None
            else CareerTwin(name=display_name)
        )

        return CareerTwin(
            name=display_name,
            skills=sorted(skill_names.values()),
            experiences=experiences,
            preferred_roles=list(
                intent.preferred_roles
            ),
            preferred_locations=list(
                intent.preferred_locations
            ),
            policy=intent.policy,
            expected_salary=intent.expected_salary,
            available_in_days=intent.available_in_days,
        )
