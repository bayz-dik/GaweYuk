from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from onejob.service import OneJobService
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
