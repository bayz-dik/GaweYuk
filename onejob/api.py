from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from onejob.service import OneJobService

service = OneJobService.demo()
app = FastAPI(title='ONEJOB MVP', version='0.1.0')
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
