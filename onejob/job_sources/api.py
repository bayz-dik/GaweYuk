from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, HTTPException

from onejob.job_sources.repository import SourceRepository
from onejob.persistence.db import Database


_OPERATOR_ROLES = {"trust_admin", "source_operator"}


def _require_operator(actor: dict) -> None:
    roles = set(actor.get("roles", ()))
    if not (roles & _OPERATOR_ROLES):
        raise HTTPException(status_code=403, detail={"error_code": "UNAUTHORIZED_ACTOR"})


def create_internal_sources_router(
    db: Database, *, actor_resolver: Callable[[], dict]
) -> APIRouter:
    router = APIRouter(prefix="/internal/sources")
    repo = SourceRepository()

    @router.get("")
    def list_sources():
        _require_operator(actor_resolver())
        with db.connection() as conn:
            return [source.model_dump() for source in repo.list_all(conn)]

    @router.get("/{source_id}")
    def get_source(source_id: str):
        _require_operator(actor_resolver())
        with db.connection() as conn:
            source = repo.get_by_id(conn, source_id)
        if source is None:
            raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND"})
        return source.model_dump()

    return router
