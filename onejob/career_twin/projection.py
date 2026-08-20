from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from onejob.career_twin.models import CareerClaim
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

            entity[claim.predicate.value] = claim.value

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
