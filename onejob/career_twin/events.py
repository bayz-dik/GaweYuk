from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CareerEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    twin_id: str
    event_type: str
    subject_id: str | None
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    causation_id: str | None = None
    correlation_id: str | None = None
