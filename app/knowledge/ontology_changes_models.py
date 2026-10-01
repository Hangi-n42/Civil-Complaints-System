"""A3 review records; canonical definitions live in immutable ontology versions."""
from typing import Any, Literal

from pydantic import BaseModel, Field
from .discovery_models import Direction


class Record(BaseModel):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}


class EvidenceRef(Record):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': False}
    evidence_id: str
    block_id: str
    source_version_id: str
    parse_run_id: str
    span: tuple[int, int]
    quote: str = Field(min_length=1)
    locator: dict[str, Any]


class Qualifiers(Record):
    scope: str = ''
    time: str = ''
    negation: Literal['affirmed', 'negated', 'unknown'] = 'unknown'
    statement_type: Literal['definition', 'rule', 'instance', 'design_proposal', 'unresolved'] = 'unresolved'


class Definition(Record):
    name: str = ''
    definition: str = ''
    inclusion: str = ''
    exclusion: str = ''
    domain_id: str | None = None
    range: str = 'string'
    required: bool = False
    multivalued: bool = False
    enum_values: list[str] = Field(default_factory=list)
    child_id: str | None = None
    parent_id: str | None = None
    relation: Literal['is_a', 'instance_of', 'broader', 'related', 'part_of'] | None = None
    alias_of: str | None = None
    canonical_id: str | None = None
    direction: Literal['subject_to_object', 'unresolved'] = 'unresolved'


class DirectionalReview(BaseModel):
    # Keep A2 IDs, validation and endpoint metadata alongside the typed judgments.
    model_config = {'extra': 'allow'}
    a_to_b: Direction
    b_to_a: Direction


class HierarchyReview(Record):
    builder: DirectionalReview
    critic: list[DirectionalReview] = Field(default_factory=list)
    review_status: str = 'unreviewed'
    possible_equivalence: bool = False


class OntologyChangeV2(Record):
    change_id: str
    target_id: str
    symbol: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_]*$')
    operation: Literal['add', 'update', 'merge', 'deprecate'] = 'add'
    target_kind: Literal['class', 'attribute', 'relation', 'vocabulary_concept', 'hierarchy', 'alias']
    before: dict[str, Any] | None = None
    after: dict[str, Any]
    dependency_ids: list[str] = Field(default_factory=list)
    affected_reference_ids: list[str] = Field(default_factory=list)
    consumer_resolution: dict[str, Any] = Field(default_factory=dict)
    support_type: Literal['explicit', 'design_proposal', 'unresolved'] = 'unresolved'
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    counter_evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    qualifiers: Qualifiers = Field(default_factory=Qualifiers)
    cq_ids: list[str] = Field(default_factory=list)
    scope_item_ids: list[str] = Field(default_factory=list)
    rationale: str = ''
    unresolved_issues: list[Any] = Field(default_factory=list)
    hierarchy_review: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    review_status: Literal['unreviewed', 'accepted', 'deferred', 'rejected'] = 'unreviewed'
    origin: dict[str, Any] = Field(default_factory=dict)


class AddOntologyChanges(Record):
    expected_changeset_revision: int = Field(ge=0)
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    # Individual malformed proposals are retained with errors, not dropped by request parsing.
    candidates: list[dict[str, Any]] = Field(min_length=1)
