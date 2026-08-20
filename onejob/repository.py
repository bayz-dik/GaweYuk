from __future__ import annotations
import json
from pathlib import Path
from onejob.models import RawJob
from onejob.profile import CareerTwin

DATA_DIR = Path(__file__).parent / 'data'

class DemoRepository:
    def load_jobs(self) -> list[RawJob]:
        payload = json.loads((DATA_DIR / 'demo_jobs.json').read_text())
        return [RawJob.model_validate(item) for item in payload]

    def load_profile(self) -> CareerTwin:
        return CareerTwin.model_validate(json.loads((DATA_DIR / 'demo_profile.json').read_text()))
