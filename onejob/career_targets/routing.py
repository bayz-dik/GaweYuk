from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from onejob.career_targets.models import (
    AlternativeTargetAssessment,
    ConfidenceBand,
    RoutingEligibility,
    RoutingMethod,
    RoutingSignal,
    TargetApplicabilityAssessment,
    TargetCompatibilityStatus,
    TargetLifecycle,
    TargetRoutingDecision,
)
from onejob.career_targets.repositories import SavedCareerTargetRepository
from onejob.career_twin.errors import CareerTwinError
from onejob.persistence.db import Database


ROUTER_VERSION = "target-router-v1"

ROUTER_V1_WEIGHTS: dict[str, float] = {
    "ROLE_FAMILY_COMPATIBILITY": 0.35,
    "DOMAIN_COMPATIBILITY": 0.25,
    "LOCATION_RELEVANCE": 0.20,
    "EMPLOYMENT_TYPE_RELEVANCE": 0.05,
    "EXPLICIT_KEYWORD_MATCH": 0.10,
    "TARGET_SCOPE_MATCH": 0.05,
}


class TargetNotRoutable(CareerTwinError):
    pass


class AmbiguousTargetRouting(CareerTwinError):
    pass


class IdFactory(Protocol):
    def __call__(self, kind: str) -> str:
        ...


@dataclass(frozen=True)
class RoutingConfig:
    router_version: str = ROUTER_VERSION
    minimum_threshold: float = 0.60
    ambiguity_margin: float = 0.10
    weights: dict[str, float] = field(default_factory=lambda: dict(ROUTER_V1_WEIGHTS))


def _tokens(text: str) -> set[str]:
    return {t for t in text.lower().replace(",", " ").split() if t}


def job_context_fingerprint(job) -> str:
    payload = json.dumps(
        {
            "normalized_title": job.normalized_title,
            "normalized_company": job.normalized_company,
            "normalized_location": job.normalized_location,
            "skills": sorted(job.skills),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class TargetRoutingService:
    """Deterministic, versioned target routing v1.

    Hard eligibility first (lifecycle ACTIVE + current VALID compatibility),
    then deterministic applicability signals, then threshold + ambiguity gate.
    The router never mutates targets or intent.
    """

    def __init__(
        self,
        db: Database,
        *,
        id_factory: IdFactory,
        config: RoutingConfig | None = None,
    ):
        self.db = db
        self.id_factory = id_factory
        self.config = config or RoutingConfig()
        self.targets = SavedCareerTargetRepository()

    def route(
        self,
        *,
        twin_id: str,
        intent_version_id: str,
        job,
        selected_target_id: str | None = None,
    ) -> TargetRoutingDecision:
        job_fp = job_context_fingerprint(job)
        now = datetime.now()

        with self.db.connection() as conn:
            targets = self.targets.list_for_twin(conn, twin_id)
            eligible: list[tuple] = []  # (target, version, compat)
            for target in targets:
                if target.lifecycle is not TargetLifecycle.ACTIVE:
                    continue
                if target.active_version_id is None:
                    continue
                compat = self.targets.latest_compatibility(
                    conn,
                    target_version_id=target.active_version_id,
                    against_intent_version_id=intent_version_id,
                )
                if compat is None or compat.status is not TargetCompatibilityStatus.VALID:
                    continue
                version = self.targets.get_version(conn, target.active_version_id)
                eligible.append((target, version, compat))

        # Score each eligible target deterministically.
        scored: list[tuple[float, object, object, list[RoutingSignal]]] = []
        for target, version, _ in eligible:
            score, signals = self._score(job, version)
            scored.append((score, target, version, signals))

        scored.sort(key=lambda item: (-item[0], item[2].target_version_id))

        # Explicit user selection wins over auto-routing.
        if selected_target_id is not None:
            return self._user_selected(
                twin_id, intent_version_id, job, job_fp, selected_target_id, scored, now
            )

        if not scored:
            return self._decision(
                twin_id, intent_version_id, job_fp, RoutingMethod.UNSCOPED,
                None, None, None, ["no eligible targets"], [], now,
            )

        top_score, top_target, top_version, _ = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        margin = top_score - second_score

        if top_score < self.config.minimum_threshold:
            return self._decision(
                twin_id, intent_version_id, job_fp, RoutingMethod.UNSCOPED,
                None, top_score, margin,
                ["no target reached minimum threshold"],
                self._alternatives(scored, exclude=None), now,
            )

        if len(scored) > 1 and margin < self.config.ambiguity_margin:
            return self._decision(
                twin_id, intent_version_id, job_fp, RoutingMethod.AMBIGUOUS,
                None, top_score, margin,
                ["top target scores within ambiguity margin"],
                self._alternatives(scored, exclude=None), now,
            )

        return self._decision(
            twin_id, intent_version_id, job_fp, RoutingMethod.AUTO_ROUTED,
            top_version.target_version_id, top_score, margin,
            ["clear winner above threshold and margin"],
            self._alternatives(scored, exclude=top_version.target_version_id), now,
        )

    def _user_selected(
        self, twin_id, intent_version_id, job, job_fp, selected_target_id, scored, now
    ) -> TargetRoutingDecision:
        with self.db.connection() as conn:
            target = self.targets.get_owned(
                conn, target_id=selected_target_id, twin_id=twin_id
            )
            if target is None or target.active_version_id is None:
                raise TargetNotRoutable(f"target not selectable: {selected_target_id}")
            compat = self.targets.latest_compatibility(
                conn,
                target_version_id=target.active_version_id,
                against_intent_version_id=intent_version_id,
            )
        if compat is None or compat.status is not TargetCompatibilityStatus.VALID:
            # User selection may not make an invalid/unsatisfiable target valid.
            raise TargetNotRoutable(
                f"selected target is not valid for the active intent: "
                f"{selected_target_id}"
            )

        alternatives = self._alternatives(
            scored, exclude=target.active_version_id
        )
        return self._decision(
            twin_id, intent_version_id, job_fp, RoutingMethod.USER_SELECTED,
            target.active_version_id, None, None,
            ["explicit user selection"], alternatives, now,
        )

    def _score(self, job, version) -> tuple[float, list[RoutingSignal]]:
        title_tokens = _tokens(job.normalized_title)
        desc_tokens = _tokens(job.description)
        job_all = title_tokens | desc_tokens
        signals: list[RoutingSignal] = []
        weights = self.config.weights
        score = 0.0

        role_tokens = _tokens(" ".join(version.role_focus))
        role_match = 1.0 if role_tokens & job_all else 0.0
        score += weights["ROLE_FAMILY_COMPATIBILITY"] * role_match
        signals.append(RoutingSignal(
            signal_type="ROLE_FAMILY_COMPATIBILITY", value=role_match,
            weight=weights["ROLE_FAMILY_COMPATIBILITY"],
            reason="role focus token overlap", source="deterministic",
        ))

        domain_tokens = _tokens(" ".join(version.domain_focus))
        domain_match = 1.0 if domain_tokens & job_all else 0.0
        score += weights["DOMAIN_COMPATIBILITY"] * domain_match
        signals.append(RoutingSignal(
            signal_type="DOMAIN_COMPATIBILITY", value=domain_match,
            weight=weights["DOMAIN_COMPATIBILITY"],
            reason="domain focus token overlap", source="deterministic",
        ))

        job_location = job.normalized_location.lower()
        scope_location = str(version.scope_definition.get("location", "")).lower()
        location_match = 1.0 if scope_location and scope_location in job_location else 0.0
        score += weights["LOCATION_RELEVANCE"] * location_match
        signals.append(RoutingSignal(
            signal_type="LOCATION_RELEVANCE", value=location_match,
            weight=weights["LOCATION_RELEVANCE"],
            reason="scope location vs job location", source="deterministic",
        ))

        keyword_tokens = _tokens(" ".join(version.explicit_keywords))
        keyword_match = 1.0 if keyword_tokens & (job_all | set(t.lower() for t in job.skills)) else 0.0
        score += weights["EXPLICIT_KEYWORD_MATCH"] * keyword_match
        signals.append(RoutingSignal(
            signal_type="EXPLICIT_KEYWORD_MATCH", value=keyword_match,
            weight=weights["EXPLICIT_KEYWORD_MATCH"],
            reason="explicit keyword overlap", source="deterministic",
        ))

        scope_match = 1.0 if location_match else 0.0
        score += weights["TARGET_SCOPE_MATCH"] * scope_match
        signals.append(RoutingSignal(
            signal_type="TARGET_SCOPE_MATCH", value=scope_match,
            weight=weights["TARGET_SCOPE_MATCH"],
            reason="scope definition match", source="deterministic",
        ))

        # employment type relevance is unknown for v1 job model → 0 signal
        signals.append(RoutingSignal(
            signal_type="EMPLOYMENT_TYPE_RELEVANCE", value=0.0,
            weight=weights["EMPLOYMENT_TYPE_RELEVANCE"],
            reason="employment type not available", source="absent",
        ))

        return score, signals

    def _alternatives(self, scored, *, exclude) -> list[AlternativeTargetAssessment]:
        alternatives = []
        for score, _target, version, _signals in scored:
            if exclude is not None and version.target_version_id == exclude:
                continue
            alternatives.append(AlternativeTargetAssessment(
                target_version_id=version.target_version_id,
                applicability_score=score,
                likely_policy_difference=[],
                reason="counterfactual alternative",
            ))
        return alternatives

    def _decision(
        self, twin_id, intent_version_id, job_fp, method,
        selected_version_id, winner_score, winner_margin, reasons, alternatives, now,
    ) -> TargetRoutingDecision:
        decision = TargetRoutingDecision(
            routing_decision_id=self.id_factory("routing_decision"),
            twin_id=twin_id,
            job_context_fingerprint=job_fp,
            intent_version_id=intent_version_id,
            method=method,
            selected_target_version_id=selected_version_id,
            winner_score=winner_score,
            winner_margin=winner_margin,
            router_version=self.config.router_version,
            reasons=reasons,
            alternatives=alternatives,
            created_at=now,
        )
        with self.db.transaction() as conn:
            self.targets.save_routing_decision(conn, decision=decision)
        return decision
