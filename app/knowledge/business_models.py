"""Persistent public requirements and the selectable source-graph workflow."""
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from .discovery_meanings import SourceMeaning


class RequirementInput(BaseModel):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}
    id: str = Field(min_length=1)
    question_ids: list[str] = Field(min_length=1)
    question: str = Field(min_length=1)
    target: str = Field(min_length=1)
    situation: str = Field(min_length=1)
    period: str = Field(min_length=1)
    criterion: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    required: bool = True
    expected_revision: int = Field(ge=0, default=0)


class BusinessRunRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    source_version_ids: list[str] = Field(min_length=1)
    requirement_ids: list[str] = Field(min_length=1)
    block_ids: list[str] = Field(default_factory=list)
    selection_reason: str = ''
    neighbor_mode: Literal['structured', 'plain'] = 'plain'
    model: str | None = None
    review_model: str | None = None
    context_tokens: int = Field(default=49152, ge=4096)
    extraction_target_chars: int = Field(default=1000, ge=1)
    representation_context_tokens: int | None = Field(default=None, ge=4096)
    extraction_tokens: int = Field(default=4096, ge=256)
    concept_tokens: int = Field(default=512, ge=64)
    review_tokens: int = Field(default=4096, ge=256)
    representation_tokens: int | None = Field(default=None, ge=256)
    source_tokens: int | None = Field(default=None, ge=256)
    source_reassessment_tokens: int | None = Field(default=None, ge=256)
    timeout: float = Field(default=1800, gt=0)
    think: bool = False
    repair: bool = True
    resume_run_id: str | None = None
    reuse_run_id: str | None = None
    reassess_run_id: str | None = None
    conceptualize: bool = True


class EvidenceQuote(BaseModel):
    block_id: str
    quote: str = Field(min_length=1)


class MeaningCheck(BaseModel):
    key: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    source_status: Literal['supported', 'refuted', 'unknown']
    availability: Literal['provided', 'unread', 'unselected', 'missing', 'ambiguous']
    evidence: list[EvidenceQuote]
    conditions: list[str]
    exceptions: list[str]
    period: str
    references: list[str]
    reason: str
    premise_keys: list[str] | None = None  # None means dependencies have not been established.


class MeaningAnnotation(BaseModel):
    meaning_keys: list[str]
    text: str


class GroundingCheck(BaseModel):
    examined_block_ids: list[str]
    meanings: list[MeaningCheck]
    completeness: Literal['complete', 'partial', 'unknown']
    gaps: list[str]
    conjunctions: list[str]
    meaning_gaps: list[MeaningAnnotation] = Field(default_factory=list)
    meaning_conjunctions: list[MeaningAnnotation] = Field(default_factory=list)


class SourceFinding(BaseModel):
    kind: Literal['local_not_found', 'reference_missing_here', 'interpretation_uncertain']
    meaning_keys: list[str]
    text: str


class LocalSourceCheck(BaseModel):
    examined_block_ids: list[str]
    inspection_status: Literal['complete', 'partial', 'unknown']
    meanings: list[MeaningCheck]
    findings: list[SourceFinding]
    conjunctions: list[str]
    meaning_conjunctions: list[MeaningAnnotation] = Field(default_factory=list)


class FindingResolution(BaseModel):
    finding_id: str
    status: Literal['resolved', 'not_required', 'required_gap', 'source_error', 'claim_error', 'unresolved']
    meaning_keys: list[str]
    claim_ids: list[str]
    fields: list[str]
    evidence: list[EvidenceQuote]
    reason: str


class RepresentationCheck(BaseModel):
    meaning_key: str
    status: Literal['represented', 'partial', 'missing', 'incorrect', 'unknown']
    claim_ids: list[str]
    incorrect_claim_ids: list[str] = Field(...)
    reason: str


class PreservationCheck(BaseModel):
    target_id: str
    status: Literal['preserved', 'lost', 'unknown']
    before_normal_meanings: list[str]
    after_locations: list[str]
    reason: str


class SourceMeaningCheck(BaseModel):
    meaning_key: str
    required_for_requirement: bool
    field_checks: dict[Literal['statement', 'conditions', 'exceptions', 'period', 'references'],
                       Literal['supported', 'refuted', 'unknown', 'not_applicable']]
    reason: str


class MeaningChallenge(BaseModel):
    meaning_key: str
    claim_ids: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    reason: str


class MeaningDependency(BaseModel):
    meaning_key: str
    premise_keys: list[str] | None


class LocalRepresentationCheck(BaseModel):
    source_checks: list[SourceMeaningCheck]
    checks: list[RepresentationCheck]
    source_challenges: list[str]
    preservation_checks: list[PreservationCheck] = Field(default_factory=list)
    meaning_challenges: list[MeaningChallenge] = Field(default_factory=list)
    dependencies: list[MeaningDependency] = Field(default_factory=list)


class RequirementCheck(LocalRepresentationCheck):
    satisfied: bool
    conjunctions_satisfied: bool
    reason: str
    source_completeness: Literal['complete', 'partial', 'unknown'] = 'unknown'
    unselected_source_required: bool | None = None
    finding_resolutions: list[FindingResolution] = Field(default_factory=list)


class RequirementJoinCheck(RequirementCheck):
    source_completeness: Literal['complete', 'partial', 'unknown'] = Field(...)
    unselected_source_required: bool | None = Field(...)


class ClaimPatch(BaseModel):
    meaning_key: str
    target_id: str | None
    statement: str
    head: str
    relation: str
    tail: str
    role: Literal['entity_relation', 'event_relation'] | None = None
    conversion_reason: str = ''
    evidence: list[EvidenceQuote]
    conditions: list[str]
    exceptions: list[str]
    period: str
    references: list[str]
    scope: 'ExtractionScope | None' = None
    reuse_claim_ids: list[str] = Field(default_factory=list)


class Repairs(BaseModel):
    patches: list[ClaimPatch]
    unresolved: list[str]


class BusinessDecision(BaseModel):
    expected_revision: int = Field(ge=0)
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    accept_ids: list[str]  # An explicit empty review approves no claims.


class BusinessQuery(BaseModel):
    question: str = Field(min_length=1)
    choices: list[str] = Field(default_factory=list)
    snapshot_id: str | None = None
    source_run_id: str | None = None
    requirement_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=12, ge=1, le=50)
    retrieval: Literal['bm25', 'dense', 'hipporag2'] = 'hipporag2'
    graph_variant: Literal['entity', 'entity_event', 'full'] = 'full'

    @model_validator(mode='after')
    def one_source(self):
        if bool(self.snapshot_id) == bool(self.source_run_id):
            raise ValueError('snapshot_id 또는 source_run_id 중 하나를 선택하세요.')
        if self.source_run_id and self.requirement_ids:
            raise ValueError('원문 QA는 요구 충족 판정이 아닙니다. 요구별 승인 지식 활용에는 snapshot을 선택하세요.')
        return self


class ChangeRequest(BaseModel):
    before_version_id: str
    after_version_id: str
    requirement_ids: list[str] = Field(default_factory=list)
    key_fields: list[str] = Field(default_factory=list)


class ConceptRunRequest(BaseModel):
    parent_run_id: str
    target_ids: list[str] = Field(min_length=1)
    neighbor_mode: Literal['plain', 'structured']


class ExtractionQualifier(BaseModel):
    """Text and its availability travel together; a status is never the text."""
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}
    state: Literal['present']
    text: str = Field(min_length=1, description='Actual nonempty source wording. A present qualifier cannot have null text.')


class UnresolvedQualifier(BaseModel):
    model_config = {'extra': 'forbid'}
    state: Literal['unresolved', 'unavailable']
    text: str | None = Field(description='Known source wording, or null when its content is unknown or unavailable. This does not mean absent.')


class AbsentQualifier(BaseModel):
    model_config = {'extra': 'forbid'}
    state: Literal['absent']
    text: None


class ExtractionParticipant(BaseModel):
    model_config = {'extra': 'forbid'}
    field: Literal['Head', 'Tail', 'Event', 'Entity']
    entity_index: int | None = Field(ge=0, description='Zero-based Entity array index; null for Head/Tail/Event.')
    evidence: list[EvidenceQuote]


class ExtractionPremises(BaseModel):
    model_config = {'extra': 'forbid'}
    state: Literal['present', 'absent', 'unresolved', 'unavailable']
    meaning_indices: list[int] = Field(description='Zero-based positions in this Scope.meanings only; not source block numbers.')


class ExtractionMeaning(BaseModel):
    """Unverified extraction interpretation; never a source truth judgment."""
    model_config = {'extra': 'forbid'}
    statement_type: SourceMeaning.model_fields['statement_type'].annotation
    relation_kind: SourceMeaning.model_fields['relation_kind'].annotation
    subject: str
    action: str
    object: str
    applies_to: str
    modality: Literal['definition', 'obligation', 'permission', 'prohibition', 'occurrence', 'unresolved']
    conditions: ExtractionQualifier | UnresolvedQualifier | AbsentQualifier
    exceptions: ExtractionQualifier | UnresolvedQualifier | AbsentQualifier
    time: ExtractionQualifier | UnresolvedQualifier | AbsentQualifier
    local_negation: ExtractionQualifier | UnresolvedQualifier | AbsentQualifier
    references: ExtractionQualifier | UnresolvedQualifier | AbsentQualifier
    premises: ExtractionPremises
    evidence: list[EvidenceQuote]
    participants: list[ExtractionParticipant]


class ExtractionScope(BaseModel):
    model_config = {'extra': 'forbid'}
    evidence: list[EvidenceQuote]
    meanings: list[ExtractionMeaning] = Field(min_length=1)


ClaimPatch.model_rebuild()
Repairs.model_rebuild()
