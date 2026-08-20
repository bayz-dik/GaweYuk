from onejob.models import RawJob
from onejob.normalization import normalize_job
from onejob.trust import assess_trust


def test_official_cross_source_job_scores_high_trust():
    job = normalize_job(RawJob(source='Company Career', external_id='1', title='Production Operator', company='Example', location='Bekasi', description='Operate machines safely.', apply_url='https://careers.example.com/jobs/1', official_source=True, contact_email='hr@example.com'))
    job.sources.append(job.sources[0].model_copy(update={'name':'LinkedIn','official':False}))
    result = assess_trust(job)
    assert result.score >= 75
    assert result.hard_block is False


def test_payment_request_creates_hard_block():
    job = normalize_job(RawJob(source='Unknown', external_id='2', title='Admin Online', company='Example', location='Remote', description='Transfer biaya administrasi Rp250.000 untuk proses seleksi.', apply_url='https://odd.site/x', contact_email='example.jobs@gmail.com'))
    result = assess_trust(job)
    assert result.hard_block is True
    assert result.score < 40
    assert any('payment' in r.lower() or 'biaya' in r.lower() for r in result.risk_reasons)
