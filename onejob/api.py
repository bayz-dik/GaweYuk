from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from onejob.service import (
    CareerTwinQueryNotConfigured,
    OneJobService,
)
import os
from onejob.persistence.db import Database
from onejob.trust_engine.explainability import TrustExplainabilityService

service = OneJobService.demo()
app = FastAPI(title='ONEJOB MVP', version='0.1.0')


_trust_db_path = os.getenv(
    "GAWEYUK_DB_PATH"
)

trust_explainer = (
    TrustExplainabilityService(
        Database(_trust_db_path)
    )
    if _trust_db_path
    else None
)
STATIC = Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC), name='static')

# Career Twin v2 Slice 3 contextual API is mounted when a database is
# configured. It is frontend-independent and reuses the safe command/query
# services. Left unmounted in the demo default to preserve legacy behavior.
if _trust_db_path:
    try:
        from onejob.career_context.api import create_career_context_router

        _slice3_db = Database(_trust_db_path)

        def _default_actor() -> dict:
            return {
                "actor_id": os.getenv("GAWEYUK_ACTOR_ID", "user-1"),
                "twin_id": os.getenv("GAWEYUK_TWIN_ID", "twin-1"),
                "is_owner": True,
                "actor_type": "USER",
            }

        def _uuid_ids(kind: str) -> str:
            import uuid

            return f"{kind}-{uuid.uuid4().hex}"

        def _now():
            from datetime import datetime, timezone

            return datetime.now(timezone.utc)

        app.include_router(
            create_career_context_router(
                _slice3_db,
                id_factory=_uuid_ids,
                actor_resolver=_default_actor,
                now_factory=_now,
                jobs_provider=lambda: service.jobs,
            )
        )
    except Exception:
        # Contextual API is optional; never break the base app if unavailable.
        pass

# Slice 4A public catalog. Mounted only when a database is configured. The
# repository filters PUBLISHABLE at the SQL boundary; legacy /api/jobs is left
# unchanged for compatibility.
if _trust_db_path:
    try:
        from onejob.catalog.api import create_catalog_router

        app.include_router(create_catalog_router(Database(_trust_db_path)))
    except Exception:
        pass

class AnswerRequest(BaseModel):
    job_id: str
    question: str

@app.get('/')
def home():
    return FileResponse(STATIC / 'index.html')

@app.get('/health')
def health():
    return {'status':'ok'}

@app.get('/api/jobs')
def jobs():
    return service.list_jobs()

@app.get('/api/jobs/{job_id}')
def job(job_id: str):
    try:
        return service.get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail='Job not found')

@app.get('/api/profile')
def profile():
    return service.profile_view()

@app.post('/api/answers/suggest')
def answer(req: AnswerRequest):
    try:
        return service.suggest_answer(req.job_id, req.question)
    except KeyError:
        raise HTTPException(status_code=404, detail='Job not found')

@app.get("/api/jobs/{job_id}/trust")
def job_trust(job_id: str):
    if trust_explainer is None:
        raise HTTPException(
            status_code=503,
            detail="Trust database not configured",
        )

    if not trust_explainer.job_exists(
        job_id
    ):
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    explanation = (
        trust_explainer.latest_explanation(
            job_id
        )
    )

    if explanation is None:
        raise HTTPException(
            status_code=404,
            detail="Trust evaluation not found",
        )

    return explanation


@app.get("/api/career-twin")
def career_twin():
    try:
        return service.career_twin_view()
    except CareerTwinQueryNotConfigured:
        raise HTTPException(
            status_code=503,
            detail="Career Twin v2 is not configured",
        )
