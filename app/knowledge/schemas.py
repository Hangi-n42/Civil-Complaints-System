"""K2 inputs; later knowledge workflows add their own contracts when implemented."""
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


class Rights(BaseModel):
    status: Literal['unknown', 'local_only', 'allowed', 'restricted'] = 'unknown'
    note: str = ''


class SourceRegistration(BaseModel):
    source_id: str | None = None
    title: str = ''
    publisher: str = ''
    namespace: str = ''
    external_id: str | None = None
    source_url: str | None = None
    rights: Rights = Field(default_factory=Rights)
    dates: list[dict[str, Any]] = Field(default_factory=list)
    selected_scope: dict[str, Any] = Field(default_factory=dict)
    acquired_at: str | None = None
    supersedes_version_id: str | None = None

    @model_validator(mode='after')
    def source_identity(self):
        if not self.source_id and not all(v.strip() for v in (self.title, self.publisher, self.namespace)):
            raise ValueError('새 출처는 title, publisher, namespace가 필요합니다.')
        return self


class RunRequest(BaseModel):
    kind: Literal['parse', 'extract', 'ontology', 'change'] = 'parse'
    source_version_ids: list[str] = Field(default_factory=list)
    retry_of_run_id: str | None = None
    unit_ids: list[str] | None = None
