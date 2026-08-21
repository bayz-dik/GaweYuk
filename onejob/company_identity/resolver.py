from __future__ import annotations

from onejob.company_identity.models import (
    CompanyIdentityResolution,
    CompanyIdentityResolutionState,
    IdentityRelationship,
    IdentityRelationshipStatus,
)


# Relationship types that, when verified for the expected company, are strong
# enough to establish a verified organizational identity.
_IDENTITY_BEARING = {
    "CAREER_SITE_FOR",
    "ATS_FOR",
    "OWNED_BY",
}


class CompanyIdentityResolver:
    """Deterministic, evidence-backed company identity resolution.

    Name similarity alone never yields VERIFIED. Identity comes from verified
    evidence relationships among domains, ATS tenants, brands, and entities.
    No LLM is used.
    """

    def resolve(
        self,
        *,
        company_id: str,
        claimed_name: str,
        source_domain: str,
        relationships: tuple[IdentityRelationship, ...],
    ) -> CompanyIdentityResolution:
        verified = [
            r
            for r in relationships
            if r.status is IdentityRelationshipStatus.VERIFIED
        ]

        # Conflicting verified ownership of the same node by different
        # companies means we cannot trust identity.
        if self._has_conflict(verified):
            return CompanyIdentityResolution(
                company_id=company_id,
                state=CompanyIdentityResolutionState.CONFLICTING,
                reason_codes=("CONFLICTING_VERIFIED_RELATIONSHIPS",),
            )

        for relationship in verified:
            if (
                relationship.company_id == company_id
                and relationship.relationship_type.value in _IDENTITY_BEARING
            ):
                return CompanyIdentityResolution(
                    company_id=company_id,
                    state=CompanyIdentityResolutionState.VERIFIED,
                    reason_codes=(
                        f"VERIFIED_{relationship.relationship_type.value}",
                    ),
                )

        probable = [
            r
            for r in relationships
            if r.status is IdentityRelationshipStatus.PROBABLE
            and r.company_id == company_id
        ]
        if probable:
            return CompanyIdentityResolution(
                company_id=company_id,
                state=CompanyIdentityResolutionState.PROBABLE,
                reason_codes=("PROBABLE_RELATIONSHIP_EVIDENCE",),
            )

        return CompanyIdentityResolution(
            company_id=company_id,
            state=CompanyIdentityResolutionState.UNKNOWN,
            reason_codes=("NO_RELATIONSHIP_EVIDENCE",),
        )

    @staticmethod
    def _has_conflict(verified: list[IdentityRelationship]) -> bool:
        # Same node claimed by more than one company via verified relationships.
        node_companies: dict[str, set[str]] = {}
        for relationship in verified:
            node_companies.setdefault(relationship.node_id, set()).add(
                relationship.company_id
            )
        return any(len(companies) > 1 for companies in node_companies.values())
