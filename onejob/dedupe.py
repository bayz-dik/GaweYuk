from difflib import SequenceMatcher
from onejob.models import CanonicalJob

def _title_equivalent(a: str, b: str) -> bool:
    ta, tb = a.split(), b.split()
    return set(ta) == set(tb) or SequenceMatcher(None, a, b).ratio() >= 0.72

def _desc_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def deduplicate_jobs(jobs: list[CanonicalJob]) -> list[CanonicalJob]:
    out: list[CanonicalJob] = []
    for job in jobs:
        match = None
        for current in out:
            same_identity = current.normalized_company == job.normalized_company and current.normalized_location == job.normalized_location
            if same_identity and _title_equivalent(current.normalized_title, job.normalized_title) and _desc_sim(current.description, job.description) >= 0.65:
                match = current
                break
        if not match:
            out.append(job.model_copy(deep=True))
            continue
        existing = {(s.name, s.external_id) for s in match.sources}
        for source in job.sources:
            if (source.name, source.external_id) not in existing:
                match.sources.append(source)
        match.skills = sorted(set(match.skills) | set(job.skills))
        if any(s.official for s in job.sources) and not any(s.official for s in match.sources):
            match.title, match.company, match.location, match.description = job.title, job.company, job.location, job.description
    return out
