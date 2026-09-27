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


class CompetencyQuestion(BaseModel):
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)


class CandidateEvidence(BaseModel):
    evidence_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class Candidate(BaseModel):
    model_config = {'extra': 'forbid'}
    id: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_]*$')
    kind: Literal['concept', 'attribute', 'relation']
    name: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    inclusion: str = Field(min_length=1)
    exclusion: str = Field(min_length=1)
    domain_id: str | None = None
    range: str = 'string'
    required: bool = False
    multivalued: bool = False
    enum_values: list[str] = Field(default_factory=list)
    evidence: list[CandidateEvidence] = Field(min_length=1)
    cq_ids: list[str] = Field(min_length=1)


class CandidateDecision(BaseModel):
    model_config = {'extra': 'forbid'}
    candidate_id: str
    action: Literal['accept', 'modify', 'defer', 'reject']
    patch: dict[str, Any] | None = None
    reason: str = ''


class DecisionRequest(BaseModel):
    expected_changeset_revision: int = Field(ge=0)
    actor: str = Field(min_length=1)
    decisions: list[CandidateDecision] = Field(min_length=1)


class RunRequest(BaseModel):
    kind: Literal['parse', 'extract', 'ontology', 'change'] = 'parse'
    source_version_ids: list[str] = Field(default_factory=list)
    retry_of_run_id: str | None = None
    unit_ids: list[str] | None = None
    cqs: list[CompetencyQuestion] = Field(default_factory=list)
    base_ontology_version_id: str | None = None
