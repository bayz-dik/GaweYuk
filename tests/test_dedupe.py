from onejob.models import RawJob
from onejob.normalization import normalize_job
from onejob.dedupe import deduplicate_jobs


def test_deduplicate_merges_same_opportunity_from_different_sources():
    jobs = [
        normalize_job(RawJob(source='LinkedIn', external_id='1', title='Production Operator', company='PT Example', location='Bekasi', description='Operate production machines and inspect product quality.', apply_url='https://x/1')),
        normalize_job(RawJob(source='JobStreet', external_id='2', title='Operator Production', company='Example', location='Bekasi', description='Operate production machines and inspect product quality daily.', apply_url='https://x/2')),
        normalize_job(RawJob(source='Company Career', external_id='3', title='Warehouse Staff', company='Example', location='Bekasi', description='Manage inventory and warehouse stock.', apply_url='https://x/3')),
    ]
    result = deduplicate_jobs(jobs)
    assert len(result) == 2
    merged = next(j for j in result if 'production' in j.normalized_title)
    assert {s.name for s in merged.sources} == {'LinkedIn', 'JobStreet'}
