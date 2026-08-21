from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from onejob.career_context.models import (
    ResolvedScope,
    ResolvedTargetViewRecord,
)
from onejob.career_context.repositories import CareerContextRepository
from onejob.career_intent.ontology import temporal_state
from onejob.career_targets.models import RoutingMethod
from onejob.career_targets.resolver import resolve_target_policy
from onejob.career_twin.errors import CareerTwinError
from onejob.persistence.db import Database


RESOLVER_VERSION = "career-context-resolver-v1"


class ContextResolutionFailed(CareerTwinError):
    """Technical failure during context resolution.

    This is a system failure, NOT a domain uncertainty state. It must never be
    downgraded to UNSCOPED/UNKNOWN or a silent legacy success.
    """


class AmbiguousContextRouting(CareerTwinError):
    pass


class IdFactory(Protocol):
    def __call__(self, kind: str) -> str:
        ...


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _canonical(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def resolved_context_fingerprint(canonical_input: dict) -> str:
    payload = json.dumps(
        _canonical(canonical_input),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResolvedContextOutcome:
    twin_id: str
    scope: ResolvedScope
    intent_version_id: str
    target_version_id: str | None
    routing_decision_id: str | None
    routing_method: RoutingMethod
    resolved_statements: list[dict[str, Any]]
    active_temporal_statements: list[dict[str, Any]]
    validation_status: str
    evaluated_at: datetime
    input_fingerprint: str
    requires_user_selection: bool = False
    alternatives: list[dict[str, Any]] = field(default_factory=list)


class CareerContextService:
    def __init__(
        self,
        db: Database,
        *,
        id_factory: IdFactory,
        intent_service,
        target_service,
        compatibility_service,
        routing_service,
    ):
        self.db = db
        self.id_factory = id_factory
        self.intent_service = intent_service
        self.target_service = target_service
        self.compatibility_service = compatibility_service
        self.routing_service = routing_service
        self.repo = CareerContextRepository()
        self.intents = intent_service.intents
        self.targets = target_service.targets

    def resolve(
        self,
        *,
        twin_id: str,
        job,
        evaluated_at: datetime,
        selected_target_id: str | None = None,
    ) -> ResolvedContextOutcome:
        try:
            return self._resolve_inner(
                twin_id=twin_id,
                job=job,
                evaluated_at=evaluated_at,
                selected_target_id=selected_target_id,
            )
        except CareerTwinError:
            raise
        except Exception as exc:  # technical failure, never domain uncertainty
            raise ContextResolutionFailed(str(exc)) from exc

    def _resolve_inner(
        self, *, twin_id, job, evaluated_at, selected_target_id
    ) -> ResolvedContextOutcome:
        with self.db.connection() as conn:
            intent = self.intents.get_for_twin(conn, twin_id)
            if intent is None or intent.active_version_id is None:
                raise ContextResolutionFailed(
                    "no active Career Intent for twin"
                )
            intent_version_id = intent.active_version_id
            intent_statements = self.intents.get_statements(
                conn, intent_version_id
            )

        decision = self.routing_service.route(
            twin_id=twin_id,
            intent_version_id=intent_version_id,
            job=job,
            selected_target_id=selected_target_id,
        )

        if decision.method is RoutingMethod.AMBIGUOUS:
            return ResolvedContextOutcome(
                twin_id=twin_id,
                scope=ResolvedScope.UNSCOPED,
                intent_version_id=intent_version_id,
                target_version_id=None,
                routing_decision_id=decision.routing_decision_id,
                routing_method=decision.method,
                resolved_statements=[],
                active_temporal_statements=[],
                validation_status="AMBIGUOUS",
                evaluated_at=evaluated_at,
                input_fingerprint="",
                requires_user_selection=True,
                alternatives=[a.model_dump() for a in decision.alternatives],
            )

        target_version_id = decision.selected_target_version_id
        overrides = []
        if target_version_id is not None:
            with self.db.connection() as conn:
                overrides = self.targets.get_overrides(conn, target_version_id)

        draft = resolve_target_policy(
            intent_statements=intent_statements,
            target_overrides=overrides,
            at=evaluated_at,
            exception_authority={"actor_type": "USER", "is_owner": True},
        )

        resolved_statements = [
            {
                "predicate": e.predicate,
                "operator": self._operator_for(e.predicate),
                "value": e.value,
                "strength": e.strength,
                "value_type": e.value_type,
                "unknown_policy": e.unknown_policy,
                "effect": e.effect,
                "source_statement_id": e.source_statement_id,
            }
            for e in draft.as_statements()
        ]

        active_temporal = [
            {"statement_id": s.statement_id, "state": temporal_state(s, evaluated_at)}
            for s in intent_statements
        ]

        scope = (
            ResolvedScope.TARGETED
            if target_version_id is not None
            else ResolvedScope.UNSCOPED
        )

        fingerprint = resolved_context_fingerprint(
            {
                "intent_version_id": intent_version_id,
                "target_version_id": target_version_id,
                "resolver_version": RESOLVER_VERSION,
                "job": {
                    "normalized_title": job.normalized_title,
                    "normalized_location": job.normalized_location,
                    "skills": sorted(job.skills),
                    "salary_min": job.salary_min,
                    "salary_max": job.salary_max,
                },
                "temporal": [
                    t for t in active_temporal if t["state"] == "ACTIVE"
                ],
                "statements": resolved_statements,
            }
        )

        return ResolvedContextOutcome(
            twin_id=twin_id,
            scope=scope,
            intent_version_id=intent_version_id,
            target_version_id=target_version_id,
            routing_decision_id=decision.routing_decision_id,
            routing_method=decision.method,
            resolved_statements=resolved_statements,
            active_temporal_statements=active_temporal,
            validation_status="VALID",
            evaluated_at=evaluated_at,
            input_fingerprint=fingerprint,
            alternatives=[a.model_dump() for a in decision.alternatives],
        )

    def materialize(
        self, outcome: ResolvedContextOutcome
    ) -> ResolvedTargetViewRecord:
        if outcome.requires_user_selection:
            raise AmbiguousContextRouting(
                "cannot materialize a resolved view for an ambiguous routing"
            )

        view = ResolvedTargetViewRecord(
            resolved_view_id=self.id_factory("resolved_view"),
            twin_id=outcome.twin_id,
            intent_version_id=outcome.intent_version_id,
            target_version_id=outcome.target_version_id,
            routing_decision_id=outcome.routing_decision_id,
            scope=outcome.scope,
            resolved_statements=outcome.resolved_statements,
            applied_overrides=[],
            explicit_exceptions=[],
            active_temporal_statements=outcome.active_temporal_statements,
            tensions=[],
            validation_status=outcome.validation_status,
            resolver_version=RESOLVER_VERSION,
            evaluated_at=outcome.evaluated_at,
            input_fingerprint=outcome.input_fingerprint,
        )

        try:
            with self.db.transaction() as conn:
                return self.repo.get_or_create_resolved_view(conn, view=view)
        except Exception as exc:
            raise ContextResolutionFailed(
                f"snapshot materialization failed: {exc}"
            ) from exc

    def _operator_for(self, predicate: str) -> str:
        from onejob.career_intent.ontology import get_intent_predicate_definition

        return get_intent_predicate_definition(predicate).operator.value
