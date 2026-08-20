from onejob.models import RawJob
from onejob.normalization import normalize_job


def test_normalize_job_keeps_provenance_and_normalizes_identity():
    raw = RawJob(source='LinkedIn', external_id='a1', title=' Production Operator ', company='PT. Example Indonesia', location='Bekasi, Jawa Barat', description='Operate production machines.', salary_min=5500000, salary_max=6500000, apply_url='https://example.com/a1', official_source=False)
    job = normalize_job(raw)
    assert job.normalized_title == 'production operator'
    assert job.normalized_company == 'example indonesia'
    assert job.normalized_location == 'bekasi jawa barat'
    assert job.sources[0].name == 'LinkedIn'
