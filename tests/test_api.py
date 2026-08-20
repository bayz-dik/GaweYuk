from fastapi.testclient import TestClient
from onejob.api import app

client = TestClient(app)

def test_health_and_jobs_api():
    assert client.get('/health').json() == {'status':'ok'}
    response = client.get('/api/jobs')
    assert response.status_code == 200
    assert len(response.json()) >= 3


def test_answer_api():
    job_id = client.get('/api/jobs').json()[0]['id']
    response = client.post('/api/answers/suggest', json={'job_id': job_id, 'question':'What is your expected salary?'})
    assert response.status_code == 200
    assert response.json()['confidence'] == 100
