from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IntentStrength(str, Enum):
    HARD_CONSTRAINT = "HARD_CONSTRAINT"
    STRONG_PREFERENCE = "STRONG_PREFERENCE"
    SOFT_PREFERENCE = "SOFT_PREFERENCE"


class UnknownPolicy(str, Enum):
    REQUIRE_VERIFICATION = "REQUIRE_VERIFICATION"
    ALLOW_WITH_WARNING = "ALLOW_WITH_WARNING"
    BLOCK_IF_UNVERIFIED = "BLOCK_IF_UNVERIFIED"


class IntentCardinality(str, Enum):
    ONE = "ONE"
    MANY = "MANY"


class IntentOperator(str, Enum):
    EQ = "EQ"
    GTE = "GTE"
    LTE = "LTE"
    IN = "IN"
    NOT_IN = "NOT_IN"


class IntentMergePolicy(str, Enum):
    REPLACE = "REPLACE"
    SET = "SET"
    MIN = "MIN"
    MAX = "MAX"


class StrictnessDirection(str, Enum):
    HIGHER_IS_STRICTER = "HIGHER_IS_STRICTER"
    LOWER_IS_STRICTER = "LOWER_IS_STRICTER"
    NONE = "NONE"


class IntentValueType(str, Enum):
    MONEY = "MONEY"
    DISTANCE = "DISTANCE"
    TEXT = "TEXT"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    LOCATION_REF_OR_TEXT = "LOCATION_REF_OR_TEXT"
    ENUM = "ENUM"


class CareerIntentRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent_id: str
    twin_id: str
    active_version_id: str | None
    created_at: datetime
    created_by_actor_id: str


class CareerIntentVersionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent_version_id: str
    intent_id: str
    version_number: int
    supersedes_version_id: str | None
    created_by_actor_id: str
    created_at: datetime
    input_fingerprint: str


class IntentStatementRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    statement_id: str
    intent_version_id: str
    predicate: str
    operator: IntentOperator
    value: Any
    value_type: str
    strength: IntentStrength
    effective_from: datetime | None = None
    expires_at: datetime | None = None
    unknown_policy: UnknownPolicy | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
