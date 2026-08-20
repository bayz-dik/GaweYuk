from __future__ import annotations
from onejob.answers import suggest_answer
from onejob.decision import decide
from onejob.dedupe import deduplicate_jobs
from onejob.matching import evaluate_policy, match_job
from onejob.normalization import normalize_job
from onejob.repository import DemoRepository
from onejob.trust import assess_trust

class OneJobService:
    def __init__(self, repo: DemoRepository):
        self.repo = repo
        self.profile = repo.load_profile()
        self.jobs = deduplicate_jobs([normalize_job(raw) for raw in repo.load_jobs()])

    @classmethod
    def demo(cls) -> 'OneJobService':
        return cls(DemoRepository())

    def _evaluate(self, job):
        match = match_job(job, self.profile)
        policy = evaluate_policy(job, self.profile)
        trust = assess_trust(job)
        decision = decide(match, trust, policy)
        return {
            'id': job.id,
            'title': job.title,
            'company': job.company,
            'location': job.location,
            'salary_min': job.salary_min,
            'salary_max': job.salary_max,
            'sources': [s.model_dump() for s in job.sources],
            'match_score': match.score,
            'trust_score': trust.score,
            'decision': decision.status,
            'decision_reasons': decision.reasons,
            'positive_evidence': match.positive_evidence,
            'negative_evidence': match.negative_evidence,
            'trust_positive': trust.positive_reasons,
            'trust_risks': trust.risk_reasons,
        }

    def list_jobs(self) -> list[dict]:
        ranked = [self._evaluate(j) for j in self.jobs]
        priority = {'APPLY': 4, 'REVIEW': 3, 'SKIP': 2, 'BLOCK': 1}
        ranked.sort(key=lambda x: (priority[x['decision']], x['match_score'], x['trust_score']), reverse=True)
        return ranked

    def get_job(self, job_id: str) -> dict:
        job = next((j for j in self.jobs if j.id == job_id), None)
        if job is None:
            raise KeyError(job_id)
        data = self._evaluate(job)
        data['description'] = job.description
        data['skills'] = job.skills
        return data

    def suggest_answer(self, job_id: str, question: str) -> dict:
        job = next((j for j in self.jobs if j.id == job_id), None)
        if job is None:
            raise KeyError(job_id)
        return suggest_answer(question, job, self.profile).model_dump()

    def profile_view(self) -> dict:
        return self.profile.model_dump()
