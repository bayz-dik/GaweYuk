from onejob.service import OneJobService


def test_service_produces_ranked_unified_market_with_all_decisions():
    service = OneJobService.demo()
    jobs = service.list_jobs()
    decisions = {j['decision'] for j in jobs}
    assert len(jobs) == 4
    assert 'APPLY' in decisions
    assert 'SKIP' in decisions
    assert 'BLOCK' in decisions
    production = next(j for j in jobs if 'Production Operator' in j['title'])
    assert len(production['sources']) >= 2
    assert production['match_score'] >= 80


def test_service_answer_uses_same_career_twin():
    service = OneJobService.demo()
    job_id = service.list_jobs()[0]['id']
    result = service.suggest_answer(job_id, 'What is your expected salary?')
    assert result['needs_user_input'] is False
    assert '6,200,000' in result['answer']
