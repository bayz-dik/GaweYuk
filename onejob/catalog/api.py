from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, FastAPI, HTTPException

from onejob.catalog.service import CatalogService
from onejob.persistence.db import Database


class CatalogUnavailable(RuntimeError):
    """The verified catalog subsystem could not initialize.

    Raised instead of silently swallowing the error so the app can fail closed
    with a deterministic 503 rather than serving unverified data.
    """


def create_catalog_router(db, *, verify_ready: bool = False) -> APIRouter:
    service = CatalogService(db)

    if verify_ready:
        # Confirm the catalog can actually open a connection at wiring time so
        # a broken subsystem fails visibly rather than at first request.
        try:
            with db.connection():
                pass
        except Exception as exc:
            raise CatalogUnavailable(str(exc)) from exc

    router = APIRouter(prefix="/api/catalog")

    @router.get("/jobs")
    def list_jobs():
        return [job.model_dump() for job in service.list_jobs()]

    @router.get("/jobs/{job_id}")
    def get_job(job_id: str):
        job = service.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND"})
        return job.model_dump()

    @router.get("/jobs/{job_id}/verification")
    def get_verification(job_id: str):
        summary = service.get_verification(job_id)
        if summary is None:
            raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND"})
        return summary.model_dump()

    return router


def mount_catalog_or_503(app: FastAPI, factory: Callable[[], APIRouter]) -> None:
    """Mount the catalog router, or a fail-closed 503 stub if it cannot init.

    When the catalog subsystem is expected but unavailable, we must not fall
    back to unverified data. Instead the public catalog routes return a
    deterministic 503 with a stable error code and no internal detail leakage.
    """
    try:
        app.include_router(factory())
    except CatalogUnavailable:
        fallback = APIRouter(prefix="/api/catalog")

        @fallback.get("/jobs")
        def _jobs_unavailable():
            raise HTTPException(
                status_code=503, detail={"error_code": "CATALOG_UNAVAILABLE"}
            )

        @fallback.get("/jobs/{job_id}")
        def _job_unavailable(job_id: str):
            raise HTTPException(
                status_code=503, detail={"error_code": "CATALOG_UNAVAILABLE"}
            )

        @fallback.get("/jobs/{job_id}/verification")
        def _verification_unavailable(job_id: str):
            raise HTTPException(
                status_code=503, detail={"error_code": "CATALOG_UNAVAILABLE"}
            )

        app.include_router(fallback)
