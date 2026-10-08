"""Persistent public requirements and the selectable source-graph workflow."""
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from .discovery_meanings import SourceMeaning
from .vendor.autoschemakg.validate_json_schema import ATLAS_SCHEMA


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


class SourceFieldJudgment(BaseModel):
    status: Literal['supported', 'refuted', 'unknown', 'not_applicable']
    reason: str = Field(min_length=1)
    statement_affected: bool = True


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
    field_judgments: dict[Literal['statement', 'conditions', 'exceptions', 'period', 'references'], SourceFieldJudgment] = Field(default_factory=dict)
    premise_keys: list[str] | None = None  # None means dependencies have not been established.

    @model_validator(mode='after')
    def field_content(self):
        for field, judgment in self.field_judgments.items():
            if judgment.status == 'supported' and not getattr(self, field) or judgment.status == 'not_applicable' and getattr(self, field):
                raise ValueError('필드의 추가 주장과 지지/해당 없음 판정이 일치해야 합니다.')
        return self


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
                       Literal['supported', 'refuted', 'unknown', 'not_applicable', 'not_assessed']]
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


class RequiredMeaningCheck(MeaningCheck):
    required_for_requirement: bool


class RequirementLink(BaseModel):
    requested_fact: str = Field(description='The fact requested by question/criterion, not a restatement of every source fact. Empty when no requested fact needs this meaning.')
    applicability: Literal['applicable', 'outside_scope', 'unresolved']
    contribution: Literal['direct_answer', 'necessary_premise', 'background']
    reason: str = Field(description='Compare target/situation/period; explain which requested fact cannot be answered without this meaning, or why it is background.')


def requirement_link_before_decision(schema):
    properties = schema['properties']
    schema['properties'] = {**{k: v for k, v in properties.items() if k != 'required_for_requirement'},
                            'required_for_requirement': properties['required_for_requirement']}


class ScopedRequiredMeaningCheck(RequiredMeaningCheck):
    model_config = dict(json_schema_extra=requirement_link_before_decision)
    requirement_link: RequirementLink

    @model_validator(mode='after')
    def consistent_requirement_link(self):
        if self.required_for_requirement and (self.requirement_link.applicability == 'outside_scope'
                or self.requirement_link.contribution == 'background' or not self.requirement_link.requested_fact.strip()):
            raise ValueError('A required meaning needs an applicable requested fact or its necessary premise')
        return self


class RequirementSourceCheck(LocalSourceCheck):
    meanings: list[RequiredMeaningCheck]


class RequirementGroundingCheck(GroundingCheck):
    meanings: list[RequiredMeaningCheck]


class ScopedRequirementSourceCheck(RequirementSourceCheck):
    meanings: list[ScopedRequiredMeaningCheck]


class ScopedRequirementGroundingCheck(RequirementGroundingCheck):
    meanings: list[ScopedRequiredMeaningCheck]


class RootedRequirementLink(RequirementLink):
    requirement_quote: str = Field(description='Exact question/criterion quotation that requests this direct answer. Empty for a premise or background; situation alone is not a requested fact.')


class RootedRequiredMeaningCheck(ScopedRequiredMeaningCheck):
    requirement_link: RootedRequirementLink


class RootedRequirementSourceCheck(ScopedRequirementSourceCheck):
    meanings: list[RootedRequiredMeaningCheck]


class RootedRequirementGroundingCheck(ScopedRequirementGroundingCheck):
    meanings: list[RootedRequiredMeaningCheck]


class MeaningContent(BaseModel):
    statement: str = Field(min_length=1)
    conditions: list[str]
    exceptions: list[str]
    period: str
    references: list[str]


class MeaningSelection(BaseModel):
    meaning_id: str
    source_status: Literal['supported', 'refuted', 'unknown']
    evidence: list[EvidenceQuote]
    requirement_link: RootedRequirementLink
    premise_keys: list[str] | None
    reason: str
    correction: MeaningContent | None = Field(description='Only if the stored meaning needs a source-grounded correction or narrower scope; otherwise null. Preserve the whole subject/condition/time meaning.')


class SelectedRequirementSourceCheck(BaseModel):
    examined_block_ids: list[str]
    inspection_status: Literal['complete', 'partial', 'unknown']
    selections: list[MeaningSelection]
    additions: list[RootedRequiredMeaningCheck]
    findings: list[SourceFinding]
    conjunctions: list[str]
    meaning_conjunctions: list[MeaningAnnotation]


class RequirementLinkUpdate(BaseModel):
    key: str
    requirement_link: RootedRequirementLink
    premise_keys: list[str] | None
    evidence: list[EvidenceQuote]
    reason: str
    required_for_requirement: bool


class RequirementLinkReassessment(GroundingCheck):
    meanings: list[RequirementLinkUpdate]


class MeaningApplicability(BaseModel):
    model_config = {'extra': 'forbid'}
    item_id: str
    key: str
    requirement_link: RequirementLink
    required_for_requirement: bool


class GroundedMeaningChallenge(MeaningChallenge):
    evidence: list[EvidenceQuote]


class RequirementApplicationCheck(BaseModel):
    model_config = {'extra': 'forbid'}
    links: list[MeaningApplicability]
    meaning_challenges: list[GroundedMeaningChallenge]


def expression_evidence_before_verdict(schema):
    properties = schema['properties']
    schema['properties'] = {**{key: value for key, value in properties.items() if key not in {'reason', 'status'}},
                            'reason': properties['reason'], 'status': properties['status']}
    schema['$comment'] = 'expression-evidence-before-verdict-v1'


class LocatedExpressionCheck(RepresentationCheck):
    model_config = dict(json_schema_extra=expression_evidence_before_verdict)
    status: Literal['represented', 'partial', 'missing', 'incorrect', 'unknown'] = Field(
        description='Only this meaning_key, not the whole requirement. When this meaning is fully expressed, use represented even if other required meanings are absent from this batch. partial requires a missing part of this same meaning.')
    claim_support: dict[str, Literal['supported', 'incorrect', 'unknown', 'not_assessed']] = Field(
        description='Whole-candidate support. not_assessed means this call did not judge all its clauses; unknown means an actual unresolved candidate field, attributed in error_fields with error_evidence. Neither means false.')
    error_fields: dict[str, list[str]] = Field(description='Incorrect or unresolved candidate ID to its disputed raw/Scope fields; empty when none.')
    error_evidence: list[EvidenceQuote]


class ExpressionReviewCheck(BaseModel):
    checks: list[LocatedExpressionCheck]
    source_challenges: list[str]
    meaning_challenges: list[GroundedMeaningChallenge]
    preservation_checks: list[PreservationCheck] = Field(default_factory=list)
    dependencies: list[MeaningDependency]


class CandidateSourceCheck(BaseModel):
    claim_id: str
    claim_support: Literal['supported', 'incorrect', 'unknown']
    evidence: list[EvidenceQuote]
    error_fields: list[str]
    error_evidence: list[EvidenceQuote]
    reason: str


class CandidateSourceReview(BaseModel):
    checks: list[CandidateSourceCheck]
    preservation_checks: list[PreservationCheck]


class ExpressionRevision(LocatedExpressionCheck):
    revision_basis: Literal['new_evidence', 'contradiction', 'prior_misreading', 'combined_expression']
    evidence: list[EvidenceQuote]


class RequirementSynthesisCheck(BaseModel):
    """Only changed expressions, premises and unresolved findings return from join."""
    checks: list[ExpressionRevision]
    dependencies: list[MeaningDependency]
    source_challenges: list[str]
    meaning_challenges: list[GroundedMeaningChallenge]
    preservation_checks: list[PreservationCheck] = Field(default_factory=list)
    satisfied: bool
    conjunctions_satisfied: bool
    reason: str
    source_completeness: Literal['complete', 'partial', 'unknown']
    unselected_source_required: bool | None
    finding_resolutions: list[FindingResolution]


class ContributionCheck(BaseModel):
    model_config = {'extra': 'forbid'}
    meaning_key: str
    status: Literal['represented', 'partial', 'missing', 'unknown']
    claim_ids: list[str]
    reason: str


class ContributionReviewCheck(ExpressionReviewCheck):
    checks: list[ContributionCheck]
    candidate_challenges: list[GroundedMeaningChallenge]


class ContributionRevision(ContributionCheck):
    revision_basis: Literal['new_evidence', 'contradiction', 'prior_misreading', 'combined_expression']
    evidence: list[EvidenceQuote]


class ContributionSynthesisCheck(RequirementSynthesisCheck):
    checks: list[ContributionRevision]
    candidate_challenges: list[GroundedMeaningChallenge]


class ClaimPatchBase(BaseModel):
    model_config = {'extra': 'forbid'}
    meaning_key: str
    target_id: str | None
    conversion_reason: str = ''
    evidence: list[EvidenceQuote]
    conditions: list[str]
    exceptions: list[str]
    period: str
    references: list[str]
    scope: 'ExtractionScope | None' = None
    reuse_claim_ids: list[str] = Field(default_factory=list)


class ClaimPatch(ClaimPatchBase):
    statement: str
    head: str
    relation: str
    tail: str
    role: Literal['entity_relation', 'event_relation'] | None = None


class EventClaimPatch(ClaimPatchBase):
    role: Literal['event_entity']
    raw: dict = Field(json_schema_extra=ATLAS_SCHEMA['event_entity']['items'])


class Repairs(BaseModel):
    patches: list[ClaimPatch | EventClaimPatch]
    unresolved: list[str]


class BusinessDecision(BaseModel):
    expected_revision: int = Field(ge=0)
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    accept_ids: list[str]  # An explicit empty review approves no claims.
    confirm_source_correction_ids: list[str] = Field(default_factory=list)


class SourceMeaningEdit(BaseModel):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}
    requirement_id: str
    meaning_key: str
    expected_meaning_version: str
    mode: Literal['reassess', 'replace']
    reason: str = Field(min_length=1)
    evidence: list[EvidenceQuote] = Field(min_length=1)
    statement: str | None = None
    conditions: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    period: str = ''
    references: list[str] = Field(default_factory=list)
    premise_keys: list[str] | None = None
    fields: list[Literal['statement', 'conditions', 'exceptions', 'period', 'references', 'premise_keys']] = Field(
        default_factory=lambda: ['statement', 'conditions', 'exceptions', 'period', 'references', 'premise_keys'])
    field_judgments: dict[Literal['statement', 'conditions', 'exceptions', 'period', 'references'], SourceFieldJudgment] = Field(default_factory=dict)

    @model_validator(mode='after')
    def replacement_content(self):
        if self.mode == 'replace' and not (self.statement or '').strip():
            raise ValueError('명시적 원문 해석 정정에는 문장이 필요합니다.')
        if self.mode == 'reassess' and self.statement is not None:
            raise ValueError('자동 재판정 요청에 정정문을 제공하지 않습니다.')
        if self.mode == 'reassess' and self.field_judgments:
            raise ValueError('자동 재판정 요청에 정정 판정을 제공하지 않습니다.')
        if self.mode == 'replace' and any(j.status == 'supported' and not getattr(self, k)
                                        or j.status == 'not_applicable' and getattr(self, k)
                                        for k, j in self.field_judgments.items()):
            raise ValueError('필드의 추가 주장과 지지/해당 없음 판정이 일치해야 합니다.')
        return self


class BusinessEventEdit(BaseModel):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}
    expected_revision: int = Field(ge=0)
    expected_claim_version: str = Field(min_length=1)
    claim_id: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    event: str = Field(min_length=1)
    evidence: list[EvidenceQuote] = Field(min_length=1)
    error_owner: Literal['candidate', 'source', 'both'] = 'candidate'
    source_edits: list[SourceMeaningEdit] = Field(default_factory=list)

    @model_validator(mode='after')
    def edit_owner(self):
        if bool(self.source_edits) != (self.error_owner in {'source', 'both'}):
            raise ValueError('오류 귀속과 원문 해석 정정 대상이 일치해야 합니다.')
        return self


class PublicAnswerItem(BaseModel):
    """Execution-only decomposition of an unchanged public request, never an expected answer."""
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}
    id: str = Field(min_length=1)
    requirement_id: str
    requirement_revision: int = Field(ge=0)
    field: Literal['question', 'criterion']
    request_quote: str = Field(min_length=1)


class BusinessQuery(BaseModel):
    question: str = Field(min_length=1)
    choices: list[str] = Field(default_factory=list)
    snapshot_id: str | None = None
    source_run_id: str | None = None
    requirement_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=12, ge=1, le=50)
    retrieval: Literal['bm25', 'dense', 'hipporag2'] = 'hipporag2'
    graph_variant: Literal['entity', 'entity_event', 'full'] = 'full'
    answer_mode: Literal['synthesis', 'source_quotes', 'items', 'reviewed_items'] = 'synthesis'
    answer_items: list[PublicAnswerItem] = Field(default_factory=list)

    @model_validator(mode='after')
    def one_source(self):
        if bool(self.snapshot_id) == bool(self.source_run_id):
            raise ValueError('snapshot_id 또는 source_run_id 중 하나를 선택하세요.')
        if self.source_run_id and self.requirement_ids:
            raise ValueError('원문 QA는 요구 충족 판정이 아닙니다. 요구별 승인 지식 활용에는 snapshot을 선택하세요.')
        if self.answer_mode in {'items', 'reviewed_items'} and not self.answer_items:
            raise ValueError('항목별 답변에는 공개 요청에서 고정한 answer_items가 필요합니다.')
        if self.answer_items and (self.answer_mode not in {'items', 'reviewed_items'} or not self.requirement_ids):
            raise ValueError('answer_items는 요구를 선택한 항목별 답변에서만 사용합니다.')
        if len({i.id for i in self.answer_items}) != len(self.answer_items):
            raise ValueError('공개 답변 항목 ID가 중복됩니다.')
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
