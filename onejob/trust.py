from pydantic import BaseModel, Field
from onejob.models import CanonicalJob

class TrustResult(BaseModel):
    score: int
    positive_reasons: list[str] = Field(default_factory=list)
    risk_reasons: list[str] = Field(default_factory=list)
    hard_block: bool = False

PAYMENT_TERMS = ['biaya administrasi', 'transfer biaya', 'deposit', 'uang seragam', 'biaya training']
FREE_EMAILS = ['gmail.com','yahoo.com','outlook.com','hotmail.com']

def assess_trust(job: CanonicalJob) -> TrustResult:
    score = 50; positives=[]; risks=[]; hard=False
    if any(s.official for s in job.sources):
        score += 25; positives.append('Found on an official company source')
    if len(job.sources) >= 2:
        score += 10; positives.append('Cross-source corroboration')
    text = job.description.lower()
    if any(term in text for term in PAYMENT_TERMS):
        score -= 60; risks.append('Payment/biaya request detected'); hard=True
    if job.contact_email:
        domain = job.contact_email.split('@')[-1].lower()
        if domain in FREE_EMAILS:
            score -= 15; risks.append('Recruitment contact uses a free email domain')
        else:
            score += 5; positives.append('Contact uses a custom domain')
    if not job.sources:
        score -= 15; risks.append('No source provenance')
    return TrustResult(score=max(0,min(100,score)), positive_reasons=positives, risk_reasons=risks, hard_block=hard)
