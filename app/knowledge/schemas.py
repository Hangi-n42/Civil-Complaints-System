"""K2 inputs; later knowledge workflows add their own contracts when implemented."""
from datetime import date
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
    action: Literal['accept', 'modify', 'defer', 'reject', 'unlink']
    patch: dict[str, Any] | None = None
    reason: str = ''


class DecisionRequest(BaseModel):
    expected_changeset_revision: int = Field(ge=0)
    actor: str = Field(min_length=1)
    decisions: list[CandidateDecision] = Field(min_length=1)


class RunRequest(BaseModel):
    kind: Literal['parse', 'extract', 'ontology', 'change', 'discovery'] = 'parse'
    source_version_ids: list[str] = Field(default_factory=list)
    retry_of_run_id: str | None = None
    unit_ids: list[str] | None = None
    cqs: list[CompetencyQuestion] = Field(default_factory=list)
    base_ontology_version_id: str | None = None
    ontology_version_id: str | None = None
    registry_source_version_id: str | None = None
    local_entity_ids: list[str] = Field(default_factory=list)
    block_ids: list[str] = Field(default_factory=list)
    parser_options: dict[str, Any] | None = None
    bundle_id: str | None = None
    manifest_hash: str | None = None
    scope: Literal['current_discovery', 'contrast_extension', 'historical_change'] | None = None
    step: int | None = Field(default=None, ge=0)
    file_ids: list[str] | None = Field(default=None, min_length=1)
    discovery_mode: Literal['inputs', 'analyze'] = 'inputs'
    input_run_id: str | None = None
    scope_items: list[CompetencyQuestion] = Field(default_factory=list)
    baseline_version: Literal['discovery-empty-v1'] = 'discovery-empty-v1'
    lineage_id: str | None = None
    analysis_block_ids: list[str] | None = Field(default=None, min_length=1)
    analysis_selection_reason: str = ''
    discovery_budgets: dict[str, int] = Field(default_factory=dict)


class ManualAssertionRequest(BaseModel):
    expected_changeset_revision: int = Field(ge=0)
    actor: str = Field(min_length=1)
    reason: str = ''
    subject_link_id: str
    object_link_id: str | None = None
    predicate_id: str
    block_id: str
    quote: str = ''
    raw_value: str = ''
    scope: str = '미확인'


class SnapshotSelection(BaseModel):
    model_config = {'extra': 'forbid'}
    changeset_id: str
    expected_changeset_revision: int = Field(ge=0)
    candidate_ids: list[str] = Field(min_length=1)


class RecordedAction(BaseModel):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ActivateSnapshotRequest(RecordedAction):
    expected_active_id: str | None


class SnapshotRequest(ActivateSnapshotRequest):
    selections: list[SnapshotSelection] = Field(min_length=1)


class AvailabilityTarget(BaseModel):
    model_config = {'extra': 'forbid'}
    type: Literal['assertion', 'evidence', 'source_version']
    id: str = Field(min_length=1)


class AvailabilityRequest(RecordedAction):
    targets: list[AvailabilityTarget] = Field(min_length=1)
    state: Literal['allowed', 'needs_review', 'blocked']
    expected_status_revision: int = Field(ge=0)


class LocalEntityRequest(RecordedAction):
    ontology_version_id: str
    concept_id: str
    name: str = Field(min_length=1)
    source_version_id: str
    evidence_ids: list[str] = Field(min_length=1)


class SearchScope(BaseModel):
    model_config = {'extra': 'forbid'}
    entity_ids: list[str] = Field(default_factory=list)
    text: str | None = None


class SearchRequest(BaseModel):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}
    query: str = Field(min_length=1, max_length=4000)
    mode: Literal['local', 'global']
    snapshot_id: str | None = None
    source_ids: list[str] | None = Field(default=None, min_length=1)
    scope: SearchScope | None = None
    as_of: date | None = None
