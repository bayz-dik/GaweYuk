import hashlib
import re
from onejob.models import RawJob, CanonicalJob, JobSource

COMPANY_PREFIXES = {'pt', 'pt.', 'cv', 'cv.'}

def _clean(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def _company(text: str) -> str:
    tokens = _clean(text).split()
    if tokens and tokens[0] in COMPANY_PREFIXES:
        tokens = tokens[1:]
    return ' '.join(tokens)

def normalize_job(raw: RawJob) -> CanonicalJob:
    nt = _clean(raw.title)
    nc = _company(raw.company)
    nl = _clean(raw.location)
    digest = hashlib.sha1(f'{nc}|{nt}|{nl}'.encode()).hexdigest()[:12]
    return CanonicalJob(
        id=f'oj-{digest}', title=raw.title.strip(), company=raw.company.strip(), location=raw.location.strip(),
        description=raw.description.strip(), normalized_title=nt, normalized_company=nc,
        normalized_location=nl, salary_min=raw.salary_min, salary_max=raw.salary_max,
        skills=[_clean(x) for x in raw.skills], contact_email=raw.contact_email,
        sources=[JobSource(name=raw.source, external_id=raw.external_id, apply_url=raw.apply_url, official=raw.official_source)],
    )
