from pydantic import BaseModel, Field
from typing import Optional
from onejob.models import CanonicalJob
from onejob.profile import CareerTwin

class AnswerSuggestion(BaseModel):
    answer: Optional[str]
    confidence: int
    needs_user_input: bool
    evidence: list[str] = Field(default_factory=list)

def suggest_answer(question: str, job: CanonicalJob, profile: CareerTwin) -> AnswerSuggestion:
    q = question.lower()
    if 'year' in q and 'experience' in q:
        months = sum(e.months for e in profile.experiences)
        years, rem = divmod(months, 12)
        wording = f'{years} year' + ('s' if years != 1 else '')
        if rem: wording += f' {rem} months'
        return AnswerSuggestion(answer=wording, confidence=98, needs_user_input=False, evidence=[f'Work history totals {months} months'])
    if 'expected salary' in q or 'salary expectation' in q or 'gaji' in q:
        if profile.expected_salary is None:
            return AnswerSuggestion(answer=None, confidence=0, needs_user_input=True, evidence=[])
        return AnswerSuggestion(answer=f'IDR {profile.expected_salary:,}', confidence=100, needs_user_input=False, evidence=['User-confirmed expected salary'])
    if 'available' in q or 'start' in q:
        if profile.available_in_days is None:
            return AnswerSuggestion(answer=None, confidence=0, needs_user_input=True, evidence=[])
        ans = 'Immediately' if profile.available_in_days == 0 else f'In {profile.available_in_days} days'
        return AnswerSuggestion(answer=ans, confidence=100, needs_user_input=False, evidence=['User-confirmed availability'])
    if 'previous' in q and ('job' in q or 'work' in q or 'experience' in q):
        if not profile.experiences:
            return AnswerSuggestion(answer=None, confidence=0, needs_user_input=True, evidence=[])
        exp = profile.experiences[0]
        facts = exp.responsibilities[:2] or [f'Worked as {exp.title}']
        return AnswerSuggestion(answer='; '.join(facts) + '.', confidence=92, needs_user_input=False, evidence=[f'Career Twin: {exp.title}'])
    return AnswerSuggestion(answer=None, confidence=0, needs_user_input=True, evidence=[])
