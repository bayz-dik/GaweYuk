from onejob.models import RawJob
from onejob.normalization import normalize_job
from onejob.profile import CareerTwin, CareerPolicy, WorkExperience
from onejob.matching import match_job, evaluate_policy


def profile():
    return CareerTwin(name='Demo User', skills=['machine operation','quality inspection','k3'], preferred_roles=['production operator','machine operator'], preferred_locations=['bekasi'], experiences=[WorkExperience(title='Operator Stamping', months=20, skills=['machine operation','quality inspection'])], policy=CareerPolicy(min_salary=5500000, excluded_roles=['sales']))


def test_match_has_explainable_positive_and_negative_evidence():
    job = normalize_job(RawJob(source='Company Career', external_id='1', title='Production Operator', company='Example', location='Bekasi', description='Machine operation, quality inspection, forklift license preferred.', salary_min=6000000, salary_max=7000000, skills=['machine operation','quality inspection','forklift'], apply_url='https://x'))
    result = match_job(job, profile())
    assert result.score >= 80
    assert any('machine operation' in e.lower() for e in result.positive_evidence)
    assert any('forklift' in e.lower() for e in result.negative_evidence)


def test_policy_rejects_salary_below_hard_minimum():
    job = normalize_job(RawJob(source='Company Career', external_id='1', title='Production Operator', company='Example', location='Bekasi', description='Machine operation.', salary_min=4500000, salary_max=5000000, apply_url='https://x'))
    result = evaluate_policy(job, profile())
    assert result.allowed is False
    assert 'salary' in result.reasons[0].lower()
