"""K2 source registration and parsing endpoints."""
from functools import lru_cache
from typing import Any
from datetime import date

from fastapi import APIRouter, Depends, File, Form, UploadFile
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
from app.knowledge import extraction_store
from app.knowledge import snapshots
from app.knowledge.schemas import SearchRequest, LocalEntityRequest


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
def evidence(evidence_id: str, service=Depends(get_knowledge_service)):
    return result(service.evidence(evidence_id))


@router.post('/runs', response_model=KnowledgeResponse)
def start(request: RunRequest, service=Depends(get_knowledge_service)):
    return result(service.start(request))


@router.get('/runs/{run_id}', response_model=KnowledgeResponse)
def run(run_id: str, service=Depends(get_knowledge_service)):
    return result(service.run(run_id))


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


@router.get('/candidates', response_model=KnowledgeResponse)
def ontology_candidates(changeset_id: str | None = None, kind: str | None = None,
                        review_status: str | None = None, service=Depends(get_knowledge_service)):
    return result(ontology_schema.candidates(service, changeset_id, kind, review_status))


@router.post('/changes/{changeset_id}/decisions', response_model=KnowledgeResponse)
def decisions(changeset_id: str, request: DecisionRequest, service=Depends(get_knowledge_service)):
    return result(ontology_schema.decide(service, changeset_id, request))


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
