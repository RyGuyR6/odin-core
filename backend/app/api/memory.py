from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from app.memory.exceptions import MemoryError, MemoryNotFoundError
from app.memory.manager import MemoryManager, get_memory_manager
from app.memory.models import *

router=APIRouter(prefix="/memory",tags=["memory"])
def manager_dep(): return get_memory_manager()
def guard(call):
    try: return call()
    except MemoryNotFoundError as exc: raise HTTPException(404,str(exc))
    except (MemoryError,ValueError) as exc: raise HTTPException(400,str(exc))

@router.post("",response_model=MemoryRecord)
def create_memory(request:MemoryCreate,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.create(request))
@router.get("",response_model=list[MemoryRecord])
def list_memories(limit:int=Query(100,ge=1,le=100),offset:int=Query(0,ge=0),scope:str|None=None,project_id:str|None=None,kind:str|None=None,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.list(limit=limit,offset=offset,scope=scope,project_id=project_id,kind=kind))
@router.get("/telemetry",response_model=MemoryTelemetry)
def telemetry(manager:MemoryManager=Depends(manager_dep)): return manager.telemetry()
@router.post("/search",response_model=list[SearchResult])
def search(request:MemorySearchRequest,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.search(request))
@router.post("/ingest/text",response_model=MemoryRecord)
def ingest_text(request:IngestTextRequest,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.ingest_text(request))
@router.post("/ingest/file",response_model=MemoryRecord)
def ingest_file(path:str,scope:str="global",project_id:str|None=None,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.ingest_file(path,scope=scope,project_id=project_id))
@router.post("/conversations",response_model=MemoryRecord)
def index_conversation(request:ConversationMemoryRequest,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.index_conversation(request))
@router.post("/reindex")
def reindex(request:ReindexRequest,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.reindex(request.memory_ids or None))
@router.get("/export")
def export_memory(manager:MemoryManager=Depends(manager_dep)): return manager.export_data()
@router.post("/import")
def import_memory(request:ImportRequest,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.import_data(request))
@router.post("/graph/edges",response_model=KnowledgeEdge)
def add_edge(request:KnowledgeEdgeCreate,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.add_edge(request))
@router.get("/graph",response_model=list[KnowledgeEdge])
def graph(memory_id:str|None=None,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.graph(memory_id))
@router.get("/{memory_id}",response_model=MemoryRecord)
def get_memory(memory_id:str,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.get(memory_id))
@router.patch("/{memory_id}",response_model=MemoryRecord)
def update_memory(memory_id:str,request:MemoryUpdate,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.update(memory_id,request))
@router.delete("/{memory_id}")
def delete_memory(memory_id:str,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.delete(memory_id))
