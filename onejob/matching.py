from pydantic import BaseModel, Field
from onejob.models import CanonicalJob
from onejob.profile import CareerTwin

class MatchResult(BaseModel):
    score: int
    positive_evidence: list[str] = Field(default_factory=list)
    negative_evidence: list[str] = Field(default_factory=list)

class PolicyResult(BaseModel):
    allowed: bool
    reasons: list[str] = Field(default_factory=list)

def evaluate_policy(job: CanonicalJob, profile: CareerTwin) -> PolicyResult:
    reasons: list[str] = []
    title = job.normalized_title
    for excluded in profile.policy.excluded_roles:
        if excluded.lower() in title:
            reasons.append(f'Role violates excluded role policy: {excluded}')
    if profile.policy.min_salary is not None and job.salary_max is not None and job.salary_max < profile.policy.min_salary:
        reasons.append(f'Salary maximum {job.salary_max} is below user minimum {profile.policy.min_salary}')
    return PolicyResult(allowed=not reasons, reasons=reasons)

def match_job(job: CanonicalJob, profile: CareerTwin) -> MatchResult:
    positives, negatives = [], []
    score = 25
    title_tokens = set(job.normalized_title.split())
    role_hit = max((len(title_tokens & set(r.lower().split())) / max(1, len(set(r.lower().split()))) for r in profile.preferred_roles), default=0)
    if role_hit >= .5:
        score += 25; positives.append('Preferred role alignment')
    if any(loc.lower() in job.normalized_location for loc in profile.preferred_locations):
        score += 15; positives.append('Preferred location match')
    user_skills = {s.lower() for s in profile.skills}
    required = {s.lower() for s in job.skills}
    matched = sorted(required & user_skills)
    missing = sorted(required - user_skills)
    if required:
        ratio = len(matched) / len(required)
        score += round(30 * ratio)
        positives.extend([f'Skill match: {s}' for s in matched])
        negatives.extend([f'Missing skill: {s}' for s in missing])
    else:
        desc = job.description.lower()
        inferred = [s for s in user_skills if s in desc]
        if inferred:
            score += min(30, 10 * len(inferred)); positives.extend([f'Skill evidence: {s}' for s in inferred])
    if profile.experiences:
        score += 5; positives.append(f'Work history available: {sum(e.months for e in profile.experiences)} months')
    return MatchResult(score=max(0, min(100, score)), positive_evidence=positives, negative_evidence=negatives)
