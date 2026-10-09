"""K2 source registration and parsing endpoints."""
from functools import lru_cache
from typing import Any
from datetime import date

from fastapi import APIRouter, Depends, File, Form, UploadFile, Query
from fastapi.responses import FileResponse
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ValidationError

from app.api.error_utils import error_response, make_request_id, now_iso
from app.core.config import settings
from app.core.exceptions import GenerationError
from app.knowledge.schemas import DecisionRequest, ManualAssertionRequest, RunRequest, SourceRegistration
from app.knowledge.schemas import SnapshotRequest, ActivateSnapshotRequest, AvailabilityRequest
from app.knowledge.service import KnowledgeConflict, KnowledgeService
from app.knowledge import ontology_schema
from app.knowledge import ontology_changes
from app.knowledge.ontology_changes_models import AddOntologyChanges
from app.knowledge import ontology_consumer
from app.knowledge import extraction_store
from app.knowledge import snapshots
from app.knowledge.schemas import SearchRequest, LocalEntityRequest
from app.knowledge import business_store, business_use
from app.knowledge.business_models import RequirementInput, BusinessRunRequest, BusinessDecision, BusinessEventEdit, BusinessQuery, ChangeRequest, ConceptRunRequest


class KnowledgeRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            if not settings.KNOWLEDGE_ENABLED:
                return error_response(request_id=make_request_id(), error_code='KNOWLEDGE_DISABLED',
                                      message='회사 지식 기능이 비활성화되어 있습니다.', status_code=503)
            try:
                return await original(request)
            except GenerationError as exc:
                return error_response(request_id=make_request_id(), error_code=exc.code, message=str(exc))
            except KeyError:
                return error_response(request_id=make_request_id(), error_code='NOT_FOUND', message='등록 항목을 찾을 수 없습니다.', status_code=404)
            except ontology_schema.VersionConflict as exc:
                return error_response(request_id=make_request_id(), error_code='VERSION_CONFLICT', message=str(exc), status_code=409)
            except KnowledgeConflict as exc:
                return error_response(request_id=make_request_id(), error_code='RUN_BUSY', message=str(exc), status_code=409)
            except (ValueError, ValidationError, RequestValidationError) as exc:
                return error_response(request_id=make_request_id(), error_code='VALIDATION_ERROR', message=str(exc), status_code=422)
        return handler


router = APIRouter(prefix='/knowledge', tags=['knowledge'], route_class=KnowledgeRoute)


class KnowledgeResponse(BaseModel):
    success: bool = True
    request_id: str
    timestamp: str
    data: dict[str, Any]


def result(data):
    return dict(success=True, request_id=make_request_id(), timestamp=now_iso(), data=data)


@lru_cache(maxsize=1)
def get_knowledge_service():
    return KnowledgeService(settings.KNOWLEDGE_DB_PATH)


def shutdown_knowledge_service():
    if get_knowledge_service.cache_info().currsize:
        get_knowledge_service().shutdown()
        get_knowledge_service.cache_clear()


@router.post('/sources', response_model=KnowledgeResponse)
def register(file: UploadFile = File(...), metadata: str = Form(...), service=Depends(get_knowledge_service)):
    try:
        registration = SourceRegistration.model_validate_json(metadata)
        return result(service.register(file.filename, file.file.read(), registration))
    finally:
        file.file.close()


@router.get('/sources', response_model=KnowledgeResponse)
def sources(source_id: str | None = None, service=Depends(get_knowledge_service)):
    return result(service.sources(source_id))


@router.get('/sources/{source_id}/versions/{version_id}', response_model=KnowledgeResponse)
def version(source_id: str, version_id: str, service=Depends(get_knowledge_service)):
    return result(service.version(source_id, version_id))


@router.get('/sources/{source_id}/versions/{version_id}/raw')
def raw(source_id: str, version_id: str, service=Depends(get_knowledge_service)):
    value = service.version(source_id, version_id)['version']
    return FileResponse(service.raw_path(value), filename=value['filename'])


@router.get('/sources/{source_id}/versions/{version_id}/blocks', response_model=KnowledgeResponse)
def blocks(source_id: str, version_id: str, service=Depends(get_knowledge_service)):
    return result(service.blocks(source_id, version_id))


@router.get('/evidence/{evidence_id}', response_model=KnowledgeResponse)
def evidence(evidence_id: str, run_id: str | None = None, service=Depends(get_knowledge_service)):
    if run_id:
        from app.knowledge.discovery_run import evidence_context
        return result(evidence_context(service, run_id, evidence_id))
    return result(service.evidence(evidence_id))


@router.post('/runs', response_model=KnowledgeResponse)
def start(request: RunRequest, service=Depends(get_knowledge_service)):
    return result(service.start(request))


@router.put('/requirements/{requirement_id}', response_model=KnowledgeResponse)
def put_requirement(requirement_id: str, request: RequirementInput, service=Depends(get_knowledge_service)):
    if request.id != requirement_id:
        raise ValueError('요구 ID가 일치하지 않습니다.')
    return result(business_store.put_requirement(service, request))


@router.get('/requirements', response_model=KnowledgeResponse)
def requirements(service=Depends(get_knowledge_service)):
    return result(business_store.requirements(service))


@router.post('/business/runs', response_model=KnowledgeResponse)
def start_business(request: BusinessRunRequest, service=Depends(get_knowledge_service)):
    return result(service.start_business(request))


@router.post('/business/concepts', response_model=KnowledgeResponse)
def business_concepts(request: ConceptRunRequest, service=Depends(get_knowledge_service)):
    from app.knowledge.business_concepts import start
    return result(start(service, request))


@router.get('/business/runs', response_model=KnowledgeResponse)
def business_runs(service=Depends(get_knowledge_service)):
    import json
    with service.repository.connect() as db:
        items = [dict(id=r['id'], status=r['status'], started_at=r['started_at'],
                      questions=[q['question'] for q in r['requirements']])
                 for row in db.execute('SELECT payload FROM runs ORDER BY rowid DESC')
                 if (r := json.loads(row['payload'])).get('kind') == 'business']
    return result(dict(items=items))


@router.get('/business/changes/{changeset_id}', response_model=KnowledgeResponse)
def business_change(changeset_id: str, service=Depends(get_knowledge_service)):
    return result(business_use.change_view(service, changeset_id))


@router.post('/business/changes/{changeset_id}/decisions', response_model=KnowledgeResponse)
def business_decision(changeset_id: str, request: BusinessDecision, service=Depends(get_knowledge_service)):
    return result(business_use.decide(service, changeset_id, request))


@router.post('/business/changes/{changeset_id}/edits', response_model=KnowledgeResponse)
def business_edit(changeset_id: str, request: BusinessEventEdit, service=Depends(get_knowledge_service)):
    from app.knowledge.business_edit import start
    return result(start(service, changeset_id, request))


@router.get('/business/snapshots', response_model=KnowledgeResponse)
def business_snapshots(service=Depends(get_knowledge_service)):
    return result(business_use.snapshots(service))


@router.post('/business/search', response_model=KnowledgeResponse)
def business_search(request: BusinessQuery, service=Depends(get_knowledge_service)):
    return result(business_use.query(service, request))


@router.post('/business/changes', response_model=KnowledgeResponse)
def business_version_change(request: ChangeRequest, service=Depends(get_knowledge_service)):
    from app.knowledge.business_changes import analyze
    return result(analyze(service, request))


@router.get('/runs/{run_id}', response_model=KnowledgeResponse)
def run(run_id: str, service=Depends(get_knowledge_service)):
    return result(service.run(run_id))


@router.get('/runs', response_model=KnowledgeResponse)
def discovery_runs(limit: int = 30, before: int | None = None, service=Depends(get_knowledge_service)):
    from app.knowledge.discovery_run import list_analysis_runs
    return result(list_analysis_runs(service, limit, before))


@router.post('/runs/{run_id}/cancel', response_model=KnowledgeResponse)
def cancel(run_id: str, service=Depends(get_knowledge_service)):
    return result(service.cancel(run_id))


@router.get('/ontology-cqs', response_model=KnowledgeResponse)
def ontology_cqs(service=Depends(get_knowledge_service)):
    return result(ontology_schema.default_cqs())


@router.get('/ontologies', response_model=KnowledgeResponse)
def ontologies(service=Depends(get_knowledge_service)):
    return result(ontology_schema.list_ontologies(service))


@router.get('/ontologies/{ontology_id}', response_model=KnowledgeResponse)
def ontology(ontology_id: str, service=Depends(get_knowledge_service)):
    return result(ontology_schema.get_ontology(service, ontology_id))


@router.get('/ontologies/{ontology_id}/consumer', response_model=KnowledgeResponse)
def ontology_consumer_contract(ontology_id: str, service=Depends(get_knowledge_service)):
    return result(ontology_consumer.inspect(service, ontology_id))


@router.post('/ontologies/{ontology_id}/consumer', response_model=KnowledgeResponse)
def review_consumer_contract(ontology_id: str, request: ontology_consumer.MappingReview, service=Depends(get_knowledge_service)):
    return result(ontology_consumer.review(service, ontology_id, request))


@router.get('/candidates', response_model=KnowledgeResponse)
def ontology_candidates(changeset_id: str | None = None, kind: str | None = None,
                        review_status: str | None = None, service=Depends(get_knowledge_service)):
    return result(ontology_schema.candidates(service, changeset_id, kind, review_status))


@router.post('/changes/{changeset_id}/decisions', response_model=KnowledgeResponse)
def decisions(changeset_id: str, request: DecisionRequest, service=Depends(get_knowledge_service)):
    return result(ontology_schema.decide(service, changeset_id, request))


@router.post('/runs/{run_id}/ontology-changes', response_model=KnowledgeResponse)
def discovery_changes(run_id: str, service=Depends(get_knowledge_service)):
    return result(ontology_changes.publish(service, run_id))


@router.post('/changes/{changeset_id}/ontology-candidates', response_model=KnowledgeResponse)
def add_ontology_candidates(changeset_id: str, request: AddOntologyChanges, service=Depends(get_knowledge_service)):
    return result(ontology_changes.add(service, changeset_id, request))


@router.get('/changes/{changeset_id}/schema-preview', response_model=KnowledgeResponse)
def ontology_preview(changeset_id: str, candidate_ids: list[str] | None = Query(default=None), service=Depends(get_knowledge_service)):
    return result(ontology_changes.preview(service, changeset_id, candidate_ids))


@router.get('/entities', response_model=KnowledgeResponse)
def entities(concept_id: str | None = None, namespace: str | None = None, official_id: str | None = None,
             q: str | None = None, service=Depends(get_knowledge_service)):
    return result(extraction_store.list_entities(service, concept_id, namespace, official_id, q))


@router.get('/entities/{entity_id}', response_model=KnowledgeResponse)
def entity(entity_id: str, service=Depends(get_knowledge_service)):
    return result(extraction_store.get_entity(service, entity_id))


@router.post('/changes/{changeset_id}/assertions', response_model=KnowledgeResponse)
def add_assertion(changeset_id: str, request: ManualAssertionRequest, service=Depends(get_knowledge_service)):
    return result(extraction_store.add_manual(service, changeset_id, request))


@router.post('/snapshots', response_model=KnowledgeResponse)
def create_snapshot(request: SnapshotRequest, service=Depends(get_knowledge_service)):
    return result(snapshots.create(service, request))


@router.get('/snapshots', response_model=KnowledgeResponse)
def snapshot_list(service=Depends(get_knowledge_service)):
    return result(snapshots.list_snapshots(service))


@router.get('/snapshots/{snapshot_id}', response_model=KnowledgeResponse)
def snapshot_detail(snapshot_id: str, entity_id: str | None = None, as_of: date | None = None,
                    service=Depends(get_knowledge_service)):
    return result(snapshots.get_snapshot(service, None if snapshot_id == 'active' else snapshot_id, entity_id, as_of))


@router.post('/snapshots/{snapshot_id}/activate', response_model=KnowledgeResponse)
def activate_snapshot(snapshot_id: str, request: ActivateSnapshotRequest, service=Depends(get_knowledge_service)):
    return result(snapshots.activate(service, snapshot_id, request))


@router.get('/availability', response_model=KnowledgeResponse)
def availability(type: str, id: str, service=Depends(get_knowledge_service)):
    return result(snapshots.availability(service, type, id))


@router.post('/availability', response_model=KnowledgeResponse)
def set_availability(request: AvailabilityRequest, service=Depends(get_knowledge_service)):
    return result(snapshots.set_availability(service, request))


@router.get('/export', response_model=KnowledgeResponse)
def export_snapshot(snapshot_id: str | None = None, format: str = 'json', entity_id: str | None = None,
                    as_of: date | None = None, service=Depends(get_knowledge_service)):
    return result(snapshots.export(service, snapshot_id, format, entity_id, as_of))


@router.post('/search', response_model=KnowledgeResponse)
def local_search(request: SearchRequest, service=Depends(get_knowledge_service)):
    from app.knowledge.search import search
    return result(search(service, request))


@router.post('/entities', response_model=KnowledgeResponse)
def register_entity(request: LocalEntityRequest, service=Depends(get_knowledge_service)):
    return result(extraction_store.register_local_entity(service, request))


@router.get('/discovery/sources', response_model=KnowledgeResponse)
def discovery_sources(scope: str | None = None, step: int | None = None,
                      run_id: str | None = None, service=Depends(get_knowledge_service)):
    if run_id is not None:
        from app.knowledge.discovery_run import catalog
        return result(catalog(service, run_id, scope, step))
    from app.knowledge.discovery_inputs import catalog
    return result(catalog('current_discovery' if scope is None else scope, 0 if step is None else step))


@router.get('/discovery/read', response_model=KnowledgeResponse)
def discovery_read(file_id: str, scope: str | None = None, step: int | None = None,
                   offset: int = 0, limit: int = 20, run_id: str | None = None,
                   service=Depends(get_knowledge_service)):
    if run_id is not None:
        from app.knowledge.discovery_run import read
        return result(read(service, run_id, file_id, scope, step, offset, limit))
    from app.knowledge.discovery_inputs import read
    return result(read(file_id, 'current_discovery' if scope is None else scope,
                       0 if step is None else step, offset, limit))


@router.get('/discovery/search', response_model=KnowledgeResponse)
def discovery_search(q: str, scope: str | None = None, step: int | None = None, limit: int = 20,
                     run_id: str | None = None, service=Depends(get_knowledge_service)):
    if run_id is not None:
        from app.knowledge.discovery_run import search
        return result(search(service, run_id, q, scope, step, limit))
    from app.knowledge.discovery_inputs import search
    return result(search(q, 'current_discovery' if scope is None else scope, 0 if step is None else step, limit))


@router.get('/discovery/terms', response_model=KnowledgeResponse)
def discovery_terms(run_id: str, label: str, term_type: str = 'any', service=Depends(get_knowledge_service)):
    from app.knowledge.discovery_analysis import terms
    return result(terms(service, run_id, label, term_type))
