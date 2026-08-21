from datetime import datetime, timezone

import pytest

from onejob.company_identity.models import (
    CompanyIdentityResolutionState,
    IdentityRelationship,
    IdentityRelationshipStatus,
    IdentityRelationshipType,
)
from onejob.company_identity.resolver import CompanyIdentityResolver


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


def test_name_match_alone_is_not_verified():
    result = CompanyIdentityResolver().resolve(
        company_id="cmp-1",
        claimed_name="PT Contoh Indonesia",
        source_domain="contoh-careers.example",
        relationships=(),
    )
    assert result.state in {
        CompanyIdentityResolutionState.UNKNOWN,
        CompanyIdentityResolutionState.PROBABLE,
    }
    assert result.state is not CompanyIdentityResolutionState.VERIFIED


def test_verified_career_domain_relationship_can_verify_identity():
    relationship = IdentityRelationship(
        relationship_id="rel-1",
        company_id="cmp-1",
        node_id="node-careers",
        relationship_type=IdentityRelationshipType.CAREER_SITE_FOR,
        status=IdentityRelationshipStatus.VERIFIED,
        confidence=0.99,
        verification_method="MANUAL_EVIDENCE",
        evidence_refs=("evidence-1",),
        first_verified_at=NOW,
        last_verified_at=NOW,
    )
    result = CompanyIdentityResolver().resolve(
        company_id="cmp-1",
        claimed_name="PT Contoh Indonesia",
        source_domain="careers.contoh.co.id",
        relationships=(relationship,),
    )
    assert result.state is CompanyIdentityResolutionState.VERIFIED


def test_conflicting_verified_relationships_are_conflicting():
    rel_a = IdentityRelationship(
        relationship_id="rel-a",
        company_id="cmp-1",
        node_id="node-domain",
        relationship_type=IdentityRelationshipType.OWNED_BY,
        status=IdentityRelationshipStatus.VERIFIED,
        confidence=0.95,
        verification_method="REGISTRY",
        evidence_refs=("e1",),
        first_verified_at=NOW,
        last_verified_at=NOW,
    )
    rel_b = IdentityRelationship(
        relationship_id="rel-b",
        company_id="cmp-2",
        node_id="node-domain",
        relationship_type=IdentityRelationshipType.OWNED_BY,
        status=IdentityRelationshipStatus.VERIFIED,
        confidence=0.95,
        verification_method="REGISTRY",
        evidence_refs=("e2",),
        first_verified_at=NOW,
        last_verified_at=NOW,
    )
    result = CompanyIdentityResolver().resolve(
        company_id="cmp-1",
        claimed_name="PT Contoh",
        source_domain="contoh.co.id",
        relationships=(rel_a, rel_b),
    )
    assert result.state is CompanyIdentityResolutionState.CONFLICTING


def test_unverified_relationship_is_probable_not_verified():
    relationship = IdentityRelationship(
        relationship_id="rel-1",
        company_id="cmp-1",
        node_id="node-careers",
        relationship_type=IdentityRelationshipType.CAREER_SITE_FOR,
        status=IdentityRelationshipStatus.PROBABLE,
        confidence=0.7,
        verification_method="HEURISTIC",
        evidence_refs=(),
        first_verified_at=NOW,
        last_verified_at=NOW,
    )
    result = CompanyIdentityResolver().resolve(
        company_id="cmp-1",
        claimed_name="PT Contoh",
        source_domain="contoh.co.id",
        relationships=(relationship,),
    )
    assert result.state is CompanyIdentityResolutionState.PROBABLE


def test_confidence_out_of_range_is_rejected():
    with pytest.raises(ValueError):
        IdentityRelationship(
            relationship_id="rel-x",
            company_id="cmp-1",
            node_id="node-1",
            relationship_type=IdentityRelationshipType.ATS_FOR,
            status=IdentityRelationshipStatus.VERIFIED,
            confidence=1.5,
            verification_method="X",
            evidence_refs=(),
            first_verified_at=NOW,
            last_verified_at=NOW,
        )


def test_no_relationships_is_unknown():
    result = CompanyIdentityResolver().resolve(
        company_id="cmp-1",
        claimed_name="Totally Unknown Co",
        source_domain="unknown.example",
        relationships=(),
    )
    assert result.state is CompanyIdentityResolutionState.UNKNOWN


def test_identity_graph_persistence_round_trip(tmp_path):
    from onejob.company_identity.models import (
        CompanyIdentitySnapshot,
        IdentityNode,
        IdentityNodeType,
    )
    from onejob.company_identity.repository import CompanyIdentityRepository
    from onejob.persistence.db import Database

    db = Database(tmp_path / "identity.db")
    db.initialize()
    repo = CompanyIdentityRepository()

    node = IdentityNode(
        node_id="node-careers",
        node_type=IdentityNodeType.CAREER_DOMAIN,
        value="careers.contoh.co.id",
        created_at=NOW,
    )
    relationship = IdentityRelationship(
        relationship_id="rel-1",
        company_id="cmp-1",
        node_id="node-careers",
        relationship_type=IdentityRelationshipType.CAREER_SITE_FOR,
        status=IdentityRelationshipStatus.VERIFIED,
        confidence=0.99,
        verification_method="MANUAL_EVIDENCE",
        evidence_refs=("evidence-1",),
        first_verified_at=NOW,
        last_verified_at=NOW,
    )

    with db.transaction() as conn:
        repo.insert_node(conn, node)
        repo.insert_relationship(conn, relationship)

    with db.connection() as conn:
        rels = repo.relationships_for_company(conn, "cmp-1")

    assert len(rels) == 1
    assert rels[0] == relationship


def test_snapshot_is_content_addressed_and_immutable(tmp_path):
    from onejob.company_identity.models import CompanyIdentitySnapshot
    from onejob.company_identity.repository import CompanyIdentityRepository
    from onejob.persistence.db import Database

    db = Database(tmp_path / "identity.db")
    db.initialize()
    repo = CompanyIdentityRepository()

    snapshot = CompanyIdentitySnapshot(
        snapshot_id="snap-1",
        company_id="cmp-1",
        state=CompanyIdentityResolutionState.VERIFIED,
        input_fingerprint="fp-1",
        reason_codes=("VERIFIED_CAREER_DOMAIN",),
        created_at=NOW,
    )

    with db.transaction() as conn:
        first = repo.get_or_create_snapshot(conn, snapshot)
        # same fingerprint returns the same immutable snapshot
        second = repo.get_or_create_snapshot(
            conn, snapshot.model_copy(update={"snapshot_id": "snap-2"})
        )

    assert first.snapshot_id == second.snapshot_id == "snap-1"
