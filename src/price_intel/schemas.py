from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator


class ExtractorKind(StrEnum):
    HTTP = "http"
    BROWSER = "browser"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD = "dead"


class SelectorSpec(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    css: str = Field(min_length=1)
    attr: str | None = None
    required: bool = False
    many: bool = False


class ProxyConfig(BaseModel):
    url: str
    username: str | None = None
    password: str | None = None


class TargetConfig(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: AnyHttpUrl
    extractor: ExtractorKind = ExtractorKind.HTTP
    selectors: list[SelectorSpec] = Field(min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    user_agents: list[str] = Field(default_factory=list)
    proxies: list[ProxyConfig] = Field(default_factory=list)
    retry_budget: int | None = Field(default=None, ge=0, le=10)
    timeout_seconds: float | None = Field(default=None, ge=1.0, le=120.0)
    wait_for_selector: str | None = None

    @field_validator("user_agents")
    @classmethod
    def non_empty_agents(cls, value: list[str]) -> list[str]:
        return [agent for agent in value if agent.strip()]


class ExtractionRequest(BaseModel):
    targets: list[TargetConfig] = Field(min_length=1, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunCreated(BaseModel):
    run_id: UUID
    status: RunStatus
    queued_tasks: int


class ExtractedItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: UUID
    target_name: str
    url: str
    success: bool
    values: dict[str, Any]
    errors: list[str]
    created_at: datetime


class RunResponse(BaseModel):
    run_id: UUID
    status: RunStatus
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class HealthResponse(BaseModel):
    service: str
    status: str
    database: str

