from __future__ import annotations

from fastapi import APIRouter, HTTPException

from onejob.catalog.service import CatalogService
from onejob.persistence.db import Database


def create_catalog_router(db: Database) -> APIRouter:
    router = APIRouter(prefix="/api/catalog")
    service = CatalogService(db)

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
