from onejob.answers import suggest_answer
from onejob.models import RawJob
from onejob.normalization import normalize_job
from onejob.profile import CareerTwin, CareerPolicy, WorkExperience


def profile():
    return CareerTwin(name='Demo User', skills=['machine operation','quality inspection'], preferred_roles=['production operator'], preferred_locations=['bekasi'], experiences=[WorkExperience(title='Operator Stamping', months=20, skills=['machine operation','quality inspection'], responsibilities=['Operated stamping machines','Inspected production quality'])], policy=CareerPolicy(min_salary=5500000), expected_salary=6200000, available_in_days=0)


def job():
    return normalize_job(RawJob(source='Company Career', external_id='1', title='Production Operator', company='Example', location='Bekasi', description='Need machine operation and quality inspection.', apply_url='https://x'))


def test_answer_years_of_experience_uses_profile_facts():
    result = suggest_answer('How many years of manufacturing experience do you have?', job(), profile())
    assert result.needs_user_input is False
    assert '1 year' in result.answer.lower()
    assert result.confidence >= 90


def test_unknown_personal_fact_requests_user_input():
    result = suggest_answer('What is your passport number?', job(), profile())
    assert result.needs_user_input is True
    assert result.answer is None
