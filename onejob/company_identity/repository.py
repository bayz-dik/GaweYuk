from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from onejob.company_identity.models import (
    CompanyIdentityResolutionState,
    CompanyIdentitySnapshot,
    IdentityNode,
    IdentityNodeType,
    IdentityRelationship,
    IdentityRelationshipStatus,
    IdentityRelationshipType,
)


def _dt(value: datetime) -> str:
    return value.isoformat()


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


class CompanyIdentityRepository:
    """Persistence for the company identity graph and immutable snapshots."""

    def insert_node(self, conn: sqlite3.Connection, node: IdentityNode) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO company_identity_nodes (
                node_id, node_type, value, created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (node.node_id, node.node_type.value, node.value, _dt(node.created_at)),
        )

    def insert_relationship(
        self, conn: sqlite3.Connection, relationship: IdentityRelationship
    ) -> None:
        conn.execute(
            """
            INSERT INTO company_identity_relationships (
                relationship_id, company_id, node_id, relationship_type,
                status, confidence, verification_method, evidence_refs_json,
                first_verified_at, last_verified_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                relationship.relationship_id,
                relationship.company_id,
                relationship.node_id,
                relationship.relationship_type.value,
                relationship.status.value,
                relationship.confidence,
                relationship.verification_method,
                json.dumps(list(relationship.evidence_refs)),
                _dt(relationship.first_verified_at),
                _dt(relationship.last_verified_at),
            ),
        )

    def relationships_for_company(
        self, conn: sqlite3.Connection, company_id: str
    ) -> list[IdentityRelationship]:
        rows = conn.execute(
            """
            SELECT relationship_id, company_id, node_id, relationship_type,
                   status, confidence, verification_method, evidence_refs_json,
                   first_verified_at, last_verified_at
            FROM company_identity_relationships
            WHERE company_id = ?
            ORDER BY relationship_id
            """,
            (company_id,),
        ).fetchall()
        return [
            IdentityRelationship(
                relationship_id=row[0],
                company_id=row[1],
                node_id=row[2],
                relationship_type=IdentityRelationshipType(row[3]),
                status=IdentityRelationshipStatus(row[4]),
                confidence=row[5],
                verification_method=row[6],
                evidence_refs=tuple(json.loads(row[7])),
                first_verified_at=_parse_dt(row[8]),
                last_verified_at=_parse_dt(row[9]),
            )
            for row in rows
        ]

    def get_or_create_snapshot(
        self, conn: sqlite3.Connection, snapshot: CompanyIdentitySnapshot
    ) -> CompanyIdentitySnapshot:
        existing = conn.execute(
            """
            SELECT snapshot_id, company_id, state, input_fingerprint,
                   reason_codes_json, created_at
            FROM company_identity_snapshots
            WHERE company_id = ? AND input_fingerprint = ?
            """,
            (snapshot.company_id, snapshot.input_fingerprint),
        ).fetchone()
        if existing is not None:
            return CompanyIdentitySnapshot(
                snapshot_id=existing[0],
                company_id=existing[1],
                state=CompanyIdentityResolutionState(existing[2]),
                input_fingerprint=existing[3],
                reason_codes=tuple(json.loads(existing[4])),
                created_at=_parse_dt(existing[5]),
            )
        conn.execute(
            """
            INSERT INTO company_identity_snapshots (
                snapshot_id, company_id, state, input_fingerprint,
                reason_codes_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.snapshot_id,
                snapshot.company_id,
                snapshot.state.value,
                snapshot.input_fingerprint,
                json.dumps(list(snapshot.reason_codes)),
                _dt(snapshot.created_at),
            ),
        )
        return snapshot
