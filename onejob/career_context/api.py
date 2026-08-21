from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from onejob.career_intent.commands import (
    AcceptIntentSuggestionCommand,
    CareerIntentCommandService,
    CreateCareerIntentVersionCommand,
    EditAndAcceptIntentSuggestionCommand,
    NewIntentStatement,
    RejectIntentSuggestionCommand,
    StaleIntentVersion,
    UnsatisfiableIntent,
)
from onejob.career_intent.query import CareerIntentQueryService
from onejob.career_intent.validation import (
    InvalidIntentStatement,
    InvalidTemporalRange,
    UnknownIntentPredicate,
)
from onejob.career_targets.commands import (
    CreateSavedCareerTargetCommand,
    NewTargetOverride,
    ReviseSavedCareerTargetCommand,
    SetTargetLifecycleCommand,
    StaleTargetVersion,
    TargetCommandService,
)
from onejob.career_targets.compatibility import TargetCompatibilityService
from onejob.career_targets.query import CareerTargetQueryService
from onejob.career_targets.routing import (
    AmbiguousTargetRouting,
    TargetNotRoutable,
    TargetRoutingService,
)
from onejob.career_context.service import (
    AmbiguousContextRouting,
    CareerContextService,
    ContextResolutionFailed,
)
from onejob.career_twin.errors import (
    AuthorizationDenied,
    CareerTwinError,
    IdempotencyConflict,
)
from onejob.persistence.db import Database


# error_code + HTTP status mapping.
_ERROR_MAP: dict[type, tuple[int, str]] = {
    StaleIntentVersion: (409, "STALE_VERSION"),
    StaleTargetVersion: (409, "STALE_VERSION"),
    IdempotencyConflict: (409, "IDEMPOTENCY_CONFLICT"),
    UnsatisfiableIntent: (422, "UNSATISFIABLE_INTENT"),
    UnknownIntentPredicate: (422, "UNKNOWN_PREDICATE"),
    InvalidTemporalRange: (400, "INVALID_TEMPORAL_RANGE"),
    InvalidIntentStatement: (422, "INVALID_INTENT_STATEMENT"),
    AuthorizationDenied: (403, "UNAUTHORIZED_ACTOR"),
    TargetNotRoutable: (422, "TARGET_NOT_ROUTABLE"),
    AmbiguousTargetRouting: (409, "AMBIGUOUS_TARGET_ROUTING"),
    AmbiguousContextRouting: (409, "AMBIGUOUS_TARGET_ROUTING"),
    ContextResolutionFailed: (503, "CONTEXT_RESOLUTION_FAILED"),
}


class StatementBody(BaseModel):
    predicate: str
    operator: str
    value: Any
    strength: str
    value_type: str
    unknown_policy: str | None = None


class CreateIntentVersionBody(BaseModel):
    idempotency_key: str
    expected_active_version_id: str | None = None
    statements: list[StatementBody]


class OverrideBody(BaseModel):
    predicate: str
    operation: str
    value: Any | None = None
    strength: str | None = None
    overrides_statement_id: str | None = None
    explicit_exception_authority: str | None = None


class CreateTargetBody(BaseModel):
    idempotency_key: str
    display_name: str
    role_focus: list[str] = Field(default_factory=list)
    domain_focus: list[str] = Field(default_factory=list)
    explicit_keywords: list[str] = Field(default_factory=list)
    scope_definition: dict[str, Any] = Field(default_factory=dict)
    overrides: list[OverrideBody] = Field(default_factory=list)


class ReviseTargetBody(BaseModel):
    idempotency_key: str
    expected_active_version_id: str | None
    display_name: str
    role_focus: list[str] = Field(default_factory=list)
    domain_focus: list[str] = Field(default_factory=list)
    explicit_keywords: list[str] = Field(default_factory=list)
    scope_definition: dict[str, Any] = Field(default_factory=dict)
    overrides: list[OverrideBody] = Field(default_factory=list)


class LifecycleBody(BaseModel):
    idempotency_key: str
    action: str


class RouteBody(BaseModel):
    job_id: str
    selected_target_id: str | None = None


def create_career_context_router(
    db: Database,
    *,
    id_factory: Callable[[str], str],
    actor_resolver: Callable[[], dict],
    now_factory: Callable[[], datetime],
    jobs_provider: Callable[[], list] | None = None,
) -> APIRouter:
    router = APIRouter()
    intent_service = CareerIntentCommandService(db, id_factory=id_factory)
    target_service = TargetCommandService(db, id_factory=id_factory)
    compat_service = TargetCompatibilityService(db, id_factory=id_factory)
    routing_service = TargetRoutingService(db, id_factory=id_factory)
    context_service = CareerContextService(
        db, id_factory=id_factory,
        intent_service=intent_service, target_service=target_service,
        compatibility_service=compat_service, routing_service=routing_service,
    )
    intent_query = CareerIntentQueryService(db)
    target_query = CareerTargetQueryService(db)

    def _fail(exc: Exception) -> HTTPException:
        for exc_type, (status, code) in _ERROR_MAP.items():
            if isinstance(exc, exc_type):
                return HTTPException(status_code=status, detail={"error_code": code})
        if isinstance(exc, CareerTwinError):
            return HTTPException(status_code=422, detail={"error_code": "DOMAIN_ERROR"})
        if isinstance(exc, (KeyError, LookupError)):
            return HTTPException(status_code=404, detail={"error_code": "NOT_FOUND"})
        raise exc

    # -- intent ---------------------------------------------------------

    @router.get("/api/career-intent")
    def get_intent():
        actor = actor_resolver()
        return intent_query.safe_view(twin_id=actor["twin_id"])

    @router.post("/api/career-intent/versions")
    def create_intent_version(body: CreateIntentVersionBody):
        actor = actor_resolver()
        try:
            result = intent_service.create_version(
                CreateCareerIntentVersionCommand(
                    actor_id=actor["actor_id"],
                    twin_id=actor["twin_id"],
                    idempotency_key=body.idempotency_key,
                    expected_active_version_id=body.expected_active_version_id,
                    statements=[
                        NewIntentStatement(
                            predicate=s.predicate, operator=s.operator,
                            value=s.value, strength=s.strength,
                            value_type=s.value_type, unknown_policy=s.unknown_policy,
                        )
                        for s in body.statements
                    ],
                ),
                actor=actor,
                now=now_factory(),
            )
        except Exception as exc:
            raise _fail(exc)
        return {
            "intent_id": result.intent_id,
            "intent_version_id": result.intent_version_id,
            "version_number": result.version_number,
        }

    # -- targets --------------------------------------------------------

    @router.get("/api/career-targets")
    def list_targets():
        actor = actor_resolver()
        return target_query.list_safe(twin_id=actor["twin_id"])

    @router.post("/api/career-targets")
    def create_target(body: CreateTargetBody):
        actor = actor_resolver()
        try:
            result = target_service.create_target(
                CreateSavedCareerTargetCommand(
                    actor_id=actor["actor_id"], twin_id=actor["twin_id"],
                    idempotency_key=body.idempotency_key,
                    display_name=body.display_name, role_focus=body.role_focus,
                    domain_focus=body.domain_focus, explicit_keywords=body.explicit_keywords,
                    scope_definition=body.scope_definition,
                    overrides=[
                        NewTargetOverride(
                            predicate=o.predicate, operation=o.operation, value=o.value,
                            strength=o.strength, overrides_statement_id=o.overrides_statement_id,
                            explicit_exception_authority=o.explicit_exception_authority,
                        )
                        for o in body.overrides
                    ],
                ),
                actor=actor, now=now_factory(),
            )
        except Exception as exc:
            raise _fail(exc)
        return {"target_id": result.target_id, "target_version_id": result.target_version_id}

    @router.get("/api/career-targets/{target_id}")
    def get_target(target_id: str):
        actor = actor_resolver()
        view = target_query.safe_view(twin_id=actor["twin_id"], target_id=target_id)
        if view is None:
            raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND"})
        return view

    @router.post("/api/career-targets/{target_id}/versions")
    def revise_target(target_id: str, body: ReviseTargetBody):
        actor = actor_resolver()
        try:
            result = target_service.revise_target(
                ReviseSavedCareerTargetCommand(
                    actor_id=actor["actor_id"], twin_id=actor["twin_id"],
                    target_id=target_id, idempotency_key=body.idempotency_key,
                    expected_active_version_id=body.expected_active_version_id,
                    display_name=body.display_name, role_focus=body.role_focus,
                    domain_focus=body.domain_focus, explicit_keywords=body.explicit_keywords,
                    scope_definition=body.scope_definition,
                    overrides=[
                        NewTargetOverride(
                            predicate=o.predicate, operation=o.operation, value=o.value,
                            strength=o.strength, overrides_statement_id=o.overrides_statement_id,
                            explicit_exception_authority=o.explicit_exception_authority,
                        )
                        for o in body.overrides
                    ],
                ),
                actor=actor, now=now_factory(),
            )
        except Exception as exc:
            raise _fail(exc)
        return {"target_id": result.target_id, "target_version_id": result.target_version_id}

    def _lifecycle(target_id: str, action: str, idempotency_key: str):
        actor = actor_resolver()
        try:
            result = target_service.set_lifecycle(
                SetTargetLifecycleCommand(
                    actor_id=actor["actor_id"], twin_id=actor["twin_id"],
                    target_id=target_id, idempotency_key=idempotency_key, action=action,
                ),
                actor=actor, now=now_factory(),
            )
        except Exception as exc:
            raise _fail(exc)
        return {"target_id": result.target_id, "lifecycle": result.lifecycle}

    @router.post("/api/career-targets/{target_id}/pause")
    def pause_target(target_id: str, body: LifecycleBody):
        return _lifecycle(target_id, "PAUSE", body.idempotency_key)

    @router.post("/api/career-targets/{target_id}/resume")
    def resume_target(target_id: str, body: LifecycleBody):
        return _lifecycle(target_id, "RESUME", body.idempotency_key)

    @router.post("/api/career-targets/{target_id}/archive")
    def archive_target(target_id: str, body: LifecycleBody):
        return _lifecycle(target_id, "ARCHIVE", body.idempotency_key)

    # -- context --------------------------------------------------------

    def _find_job(job_id: str):
        provider = jobs_provider or (lambda: [])
        for job in provider():
            if job.id == job_id:
                return job
        return None

    @router.post("/api/career-context/route")
    def route(body: RouteBody):
        actor = actor_resolver()
        job = _find_job(body.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND"})
        try:
            decision = routing_service.route(
                twin_id=actor["twin_id"],
                intent_version_id=intent_query.active_version_id(actor["twin_id"]),
                job=job,
                selected_target_id=body.selected_target_id,
            )
        except Exception as exc:
            raise _fail(exc)
        return {
            "method": decision.method.value,
            "selected_target_version_id": decision.selected_target_version_id,
            "alternatives": [a.model_dump() for a in decision.alternatives],
        }

    return router
