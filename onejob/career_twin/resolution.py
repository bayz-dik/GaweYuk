from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict

from onejob.career_twin.ontology import Predicate, EntityType


RESOLVER_ALGORITHM_VERSION = "career-resolver-v1"


class ConfidenceBand(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class EntityResolution(BaseModel):
    """Appendable/versioned resolution assessment. Never mutable truth.

    Even a HIGH band only authorizes routing/linking; it never grants
    claim-approval authority.
    """

    model_config = ConfigDict(frozen=True)

    resolution_id: str
    candidate_id: str
    proposed_entity_id: str | None = None
    confidence: float | None = None
    confidence_band: ConfidenceBand
    method: str
    algorithm_version: str
    input_fingerprint: str
    signals_json: str = "{}"
    created_at: datetime
    supersedes_resolution_id: str | None = None


# ---------------------------------------------------------------------------
# Deterministic entity resolution v1
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolutionCandidateInput:
    candidate_id: str
    entity_type: EntityType
    attributes: dict


@dataclass(frozen=True)
class ResolutionEntityInput:
    entity_id: str
    entity_type: EntityType
    attributes: dict


@dataclass(frozen=True)
class EntityResolutionAssessment:
    """Explainable, versioned resolution output.

    Surfaces routing only (``proposed_entity_id``). It carries no field that
    could approve or replace a canonical claim -- even a HIGH band grants
    linking authority only, never claim-approval authority.
    """

    result: ConfidenceBand
    proposed_entity_id: str | None
    confidence: float | None
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    method: str = ""
    algorithm_version: str = RESOLVER_ALGORITHM_VERSION


# Minimal deterministic skill alias table. Extension point for a future
# ontology-backed alias resolver.
_SKILL_ALIASES: dict[str, str] = {
    "ms excel": "microsoft excel",
    "microsoft excel": "microsoft excel",
    "excel": "microsoft excel",
    "js": "javascript",
    "javascript": "javascript",
}


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    return " ".join(str(value).strip().lower().split()) or None


def _canonical_skill(value: str | None) -> str | None:
    if value is None:
        return None
    return _SKILL_ALIASES.get(value, value)


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _dates_overlap(
    a_start: date | None,
    a_end: date | None,
    b_start: date | None,
    b_end: date | None,
) -> bool:
    if None in (a_start, b_start):
        return False
    a_end = a_end or date.max
    b_end = b_end or date.max
    return a_start <= b_end and b_start <= a_end


def _resolve_skill(
    candidate: ResolutionCandidateInput,
    entities: list[ResolutionEntityInput],
) -> EntityResolutionAssessment:
    raw_name = candidate.attributes.get("name")
    name = _normalize_text(raw_name)
    canon = _canonical_skill(name)

    for entity in entities:
        ename = _normalize_text(entity.attributes.get("name"))
        if ename is not None and ename == name:
            return EntityResolutionAssessment(
                result=ConfidenceBand.HIGH,
                proposed_entity_id=entity.entity_id,
                confidence=0.99,
                reasons=["exact normalized skill name match"],
                method="skill-resolver",
            )

    for entity in entities:
        ecanon = _canonical_skill(_normalize_text(entity.attributes.get("name")))
        if canon is not None and ecanon == canon:
            return EntityResolutionAssessment(
                result=ConfidenceBand.HIGH,
                proposed_entity_id=entity.entity_id,
                confidence=0.9,
                reasons=["known skill alias equivalent"],
                method="skill-resolver",
            )

    return EntityResolutionAssessment(
        result=ConfidenceBand.LOW,
        proposed_entity_id=None,
        confidence=None,
        reasons=["no matching skill identity"],
        method="skill-resolver",
    )


def _resolve_experience(
    candidate: ResolutionCandidateInput,
    entities: list[ResolutionEntityInput],
) -> EntityResolutionAssessment:
    c_company = _normalize_text(candidate.attributes.get("company"))
    c_role = _normalize_text(candidate.attributes.get("role"))
    c_start = _parse_date(candidate.attributes.get("start_date"))
    c_end = _parse_date(candidate.attributes.get("end_date"))

    best: EntityResolutionAssessment | None = None

    for entity in entities:
        e_company = _normalize_text(entity.attributes.get("company"))
        e_role = _normalize_text(entity.attributes.get("role"))
        e_start = _parse_date(entity.attributes.get("start_date"))
        e_end = _parse_date(entity.attributes.get("end_date"))

        reasons: list[str] = []
        warnings: list[str] = []

        company_match = c_company is not None and c_company == e_company
        role_match = c_role is not None and c_role == e_role

        if company_match:
            reasons.append("same normalized company")
        if role_match:
            reasons.append("same normalized role")

        if not (company_match or role_match):
            continue

        dates_known = all(
            d is not None for d in (c_start, e_start)
        ) and (c_end is not None or e_end is not None)

        if c_start is None and c_end is None and e_start is None and e_end is None:
            # No date signal at all -> requires review.
            warnings.append("dates unavailable")
            candidate_assessment = EntityResolutionAssessment(
                result=ConfidenceBand.MEDIUM,
                proposed_entity_id=entity.entity_id,
                confidence=0.6,
                reasons=reasons or ["partial identity match"],
                warnings=warnings,
                method="experience-resolver",
            )
        elif _dates_overlap(c_start, c_end, e_start, e_end):
            reasons.append("overlapping employment period")
            if company_match and role_match:
                candidate_assessment = EntityResolutionAssessment(
                    result=ConfidenceBand.HIGH,
                    proposed_entity_id=entity.entity_id,
                    confidence=0.95,
                    reasons=reasons,
                    warnings=warnings,
                    method="experience-resolver",
                )
            else:
                candidate_assessment = EntityResolutionAssessment(
                    result=ConfidenceBand.MEDIUM,
                    proposed_entity_id=entity.entity_id,
                    confidence=0.7,
                    reasons=reasons,
                    warnings=warnings,
                    method="experience-resolver",
                )
        else:
            # Strong contradiction: dates known and clearly non-overlapping.
            # This vetoes any aggregate similarity from company/role.
            warnings.append(
                "contradictory employment dates (non-overlapping)"
            )
            candidate_assessment = EntityResolutionAssessment(
                result=ConfidenceBand.LOW,
                proposed_entity_id=None,
                confidence=None,
                reasons=reasons,
                warnings=warnings,
                method="experience-resolver",
            )

        best = _prefer(best, candidate_assessment)

    if best is None:
        return EntityResolutionAssessment(
            result=ConfidenceBand.LOW,
            proposed_entity_id=None,
            confidence=None,
            reasons=["no matching experience identity"],
            method="experience-resolver",
        )

    return best


_BAND_RANK = {
    ConfidenceBand.HIGH: 3,
    ConfidenceBand.MEDIUM: 2,
    ConfidenceBand.LOW: 1,
    ConfidenceBand.UNKNOWN: 0,
}


def _prefer(
    current: EntityResolutionAssessment | None,
    candidate: EntityResolutionAssessment,
) -> EntityResolutionAssessment:
    if current is None:
        return candidate
    if _BAND_RANK[candidate.result] > _BAND_RANK[current.result]:
        return candidate
    return current


def _resolve_generic(
    candidate: ResolutionCandidateInput,
    entities: list[ResolutionEntityInput],
) -> EntityResolutionAssessment:
    # Default identity resolver: exact normalized "name"/"title" match.
    keys = ("name", "title", "institution", "program")
    c_values = {
        _normalize_text(candidate.attributes.get(k))
        for k in keys
    } - {None}

    for entity in entities:
        e_values = {
            _normalize_text(entity.attributes.get(k))
            for k in keys
        } - {None}
        if c_values & e_values:
            return EntityResolutionAssessment(
                result=ConfidenceBand.HIGH,
                proposed_entity_id=entity.entity_id,
                confidence=0.9,
                reasons=["exact normalized identity match"],
                method="generic-resolver",
            )

    return EntityResolutionAssessment(
        result=ConfidenceBand.LOW,
        proposed_entity_id=None,
        confidence=None,
        reasons=["no matching identity"],
        method="generic-resolver",
    )


# Entity-type-specific resolver strategies. A single universal threshold is
# forbidden (spec 8.3); each entity type routes to its own strategy.
_RESOLVERS = {
    EntityType.SKILL: _resolve_skill,
    EntityType.EXPERIENCE: _resolve_experience,
}


def resolve_entity(
    candidate: ResolutionCandidateInput,
    entities: list[ResolutionEntityInput],
) -> EntityResolutionAssessment:
    """Deterministic, versioned, explainable, entity-type-aware, fail-safe.

    Any internal failure yields UNKNOWN rather than a confident wrong answer.
    A HIGH result proposes routing only and never approves a claim.
    """
    try:
        if not entities:
            return EntityResolutionAssessment(
                result=ConfidenceBand.LOW,
                proposed_entity_id=None,
                confidence=None,
                reasons=["no canonical entities to compare"],
                method="resolver",
            )

        resolver = _RESOLVERS.get(candidate.entity_type, _resolve_generic)
        same_type = [
            e for e in entities if e.entity_type == candidate.entity_type
        ]
        return resolver(candidate, same_type or entities)
    except Exception as exc:  # fail-safe: never fabricate certainty
        return EntityResolutionAssessment(
            result=ConfidenceBand.UNKNOWN,
            proposed_entity_id=None,
            confidence=None,
            reasons=[],
            warnings=[f"resolver error: {type(exc).__name__}"],
            method="resolver",
        )
