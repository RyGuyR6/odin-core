from fastapi import APIRouter,HTTPException,Query
from app.storage.service import storage_service
router=APIRouter(prefix='/storage',tags=['Storage'])

@router.get('/health')
def storage_health(): return storage_service.health()

def repository_for(namespace):
    repos={'jobs':storage_service.jobs,'contexts':storage_service.contexts,'planner-runs':storage_service.planner_runs,'planner_runs':storage_service.planner_runs}
    repo=repos.get(namespace)
    if repo is None: raise HTTPException(404,f'Unknown storage namespace: {namespace}')
    return repo

@router.get('/records/{namespace}')
def list_records(namespace:str,limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0)):
    records=repository_for(namespace).list_payloads(limit=limit,offset=offset)
    return {'namespace':namespace,'count':len(records),'offset':offset,'limit':limit,'records':records}

@router.get('/records/{namespace}/{record_id}')
def get_record(namespace:str,record_id:str):
    record=repository_for(namespace).get_payload(record_id)
    if record is None: raise HTTPException(404,f'Record not found: {record_id}')
    return record

@router.get('/events')
def persisted_events(event_type:str|None=None,context_id:str|None=None,job_id:str|None=None,limit:int=Query(100,ge=1,le=500),after_id:int|None=Query(None,ge=0)):
    events=storage_service.list_persisted_events(event_type=event_type,context_id=context_id,job_id=job_id,limit=limit,after_id=after_id)
    return {'count':len(events),'events':events}
