#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=""; BACKEND=""; PYTHON_BIN=""; BACKUP_DIR=""
step(){ printf '\n▶ %s\n' "$1"; }
ok(){ printf '✅ %s\n' "$1"; }
die(){ printf '❌ %s\n' "$1" >&2; exit 1; }
trap 'printf "\n❌ Milestone 12 failed at line %s\n" "$LINENO"; [[ -n "${BACKUP_DIR:-}" ]] && printf "Backups: %s\n" "$BACKUP_DIR"' ERR

for d in "${ODIN_ROOT:-}" "$(pwd)" /workspaces/odin-core "$(git rev-parse --show-toplevel 2>/dev/null || true)"; do
  [[ -n "$d" ]] || continue
  if [[ -d "$d/backend/app" ]]; then ROOT="$(cd "$d" && pwd)"; BACKEND="$ROOT/backend"; break; fi
done
[[ -n "$ROOT" ]] || die "Could not locate odin-core"
for p in "$BACKEND/.venv/bin/python" "$ROOT/.venv/bin/python" "$(command -v python || true)" "$(command -v python3 || true)"; do
  [[ -x "$p" ]] && PYTHON_BIN="$p" && break
done
[[ -n "$PYTHON_BIN" ]] || die "Python not found"

printf '\n============================================================\nODIN MILESTONE 12 — PERSISTENT SQLITE STORAGE\n============================================================\n'
printf 'Repository: %s\nBackend: %s\nPython: %s\n' "$ROOT" "$BACKEND" "$PYTHON_BIN"
"$PYTHON_BIN" --version

step "Checking dependencies"
"$PYTHON_BIN" - <<'PY'
import importlib.util
missing=[x for x in ('fastapi','pydantic') if importlib.util.find_spec(x) is None]
if missing: raise SystemExit('Missing: '+', '.join(missing))
print('Dependencies available.')
PY
ok "Dependencies available"

step "Preparing directories and backups"
BACKUP_DIR="$ROOT/.odin-backups/milestone12/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR" "$BACKEND/app/storage" "$BACKEND/app/api" "$BACKEND/data"
for rel in app/main.py app/jobs/manager.py app/events/bus.py app/api/storage.py app/storage/__init__.py app/storage/base.py app/storage/sqlite.py app/storage/repositories.py app/storage/service.py; do
  if [[ -f "$BACKEND/$rel" ]]; then mkdir -p "$BACKUP_DIR/$(dirname "$rel")"; cp -p "$BACKEND/$rel" "$BACKUP_DIR/$rel"; fi
done
ok "Backup created: $BACKUP_DIR"

step "Writing storage contracts"
cat > "$BACKEND/app/storage/base.py" <<'PY'
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping

def utc_now_iso() -> str: return datetime.now(UTC).isoformat()

@dataclass(slots=True, frozen=True)
class StorageRecord:
    namespace: str
    key: str
    payload: dict[str, Any]
    created_at: str
    updated_at: str
    version: int = 1

class StorageBackend(ABC):
    @abstractmethod
    def initialize(self) -> None: ...
    @abstractmethod
    def health(self) -> dict[str, Any]: ...
    @abstractmethod
    def put_record(self, namespace: str, key: str, payload: Mapping[str, Any]) -> StorageRecord: ...
    @abstractmethod
    def get_record(self, namespace: str, key: str) -> StorageRecord | None: ...
    @abstractmethod
    def list_records(self, namespace: str, *, limit: int=100, offset: int=0) -> list[StorageRecord]: ...
    @abstractmethod
    def delete_record(self, namespace: str, key: str) -> bool: ...
    @abstractmethod
    def count_records(self, namespace: str) -> int: ...
    @abstractmethod
    def append_event(self, event_id: str, event_type: str, payload: Mapping[str, Any], *, created_at: str, source: str|None=None, context_id: str|None=None, job_id: str|None=None) -> None: ...
    @abstractmethod
    def list_events(self, *, event_type: str|None=None, context_id: str|None=None, job_id: str|None=None, limit: int=100, after_id: int|None=None) -> list[dict[str, Any]]: ...
    @abstractmethod
    def close(self) -> None: ...
PY

step "Writing SQLite backend"
cat > "$BACKEND/app/storage/sqlite.py" <<'PY'
from __future__ import annotations
import json, sqlite3, threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping
from app.storage.base import StorageBackend, StorageRecord, utc_now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY,name TEXT NOT NULL,applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS records(namespace TEXT NOT NULL,key TEXT NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(namespace,key));
CREATE INDEX IF NOT EXISTS idx_records_ns_updated ON records(namespace,updated_at DESC);
CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT NOT NULL UNIQUE,event_type TEXT NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL,source TEXT,context_id TEXT,job_id TEXT);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type,sequence DESC);
CREATE INDEX IF NOT EXISTS idx_events_context ON events(context_id,sequence DESC);
CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id,sequence DESC);
"""

class SQLiteBackend(StorageBackend):
    def __init__(self,database_path: str|Path):
        self.database_path=Path(database_path).expanduser().resolve(); self._lock=threading.RLock(); self._initialized=False
    def _connect(self):
        self.database_path.parent.mkdir(parents=True,exist_ok=True)
        c=sqlite3.connect(self.database_path,timeout=30,check_same_thread=False); c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA synchronous=NORMAL'); c.execute('PRAGMA busy_timeout=30000')
        return c
    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        c=self._connect()
        try: yield c; c.commit()
        except Exception: c.rollback(); raise
        finally: c.close()
    def initialize(self):
        with self._lock, self.connection() as c:
            c.executescript(SCHEMA)
            c.execute('INSERT OR IGNORE INTO schema_migrations VALUES(1,?,?)',('initial persistent storage schema',utc_now_iso()))
        self._initialized=True
    def _ready(self):
        if not self._initialized: self.initialize()
    @staticmethod
    def _dump(payload): return json.dumps(dict(payload),sort_keys=True,separators=(',',':'),default=str)
    @staticmethod
    def _record(r): return StorageRecord(r['namespace'],r['key'],json.loads(r['payload_json']),r['created_at'],r['updated_at'],r['version'])
    def health(self):
        self._ready()
        with self.connection() as c:
            m=c.execute('SELECT COUNT(*) n FROM schema_migrations').fetchone()['n']; r=c.execute('SELECT COUNT(*) n FROM records').fetchone()['n']; e=c.execute('SELECT COUNT(*) n FROM events').fetchone()['n']
        return {'status':'ok','backend':'sqlite','database_path':str(self.database_path),'database_exists':self.database_path.exists(),'migration_count':m,'record_count':r,'event_count':e}
    def put_record(self,namespace,key,payload):
        self._ready(); namespace=namespace.strip(); key=key.strip()
        if not namespace or not key: raise ValueError('namespace and key are required')
        now=utc_now_iso()
        with self._lock, self.connection() as c:
            old=c.execute('SELECT created_at,version FROM records WHERE namespace=? AND key=?',(namespace,key)).fetchone()
            if old:
                created=old['created_at']; version=old['version']+1
                c.execute('UPDATE records SET payload_json=?,updated_at=?,version=? WHERE namespace=? AND key=?',(self._dump(payload),now,version,namespace,key))
            else:
                created=now; version=1
                c.execute('INSERT INTO records VALUES(?,?,?,?,?,?)',(namespace,key,self._dump(payload),created,now,version))
        return StorageRecord(namespace,key,dict(payload),created,now,version)
    def get_record(self,namespace,key):
        self._ready()
        with self.connection() as c: row=c.execute('SELECT * FROM records WHERE namespace=? AND key=?',(namespace,key)).fetchone()
        return None if row is None else self._record(row)
    def list_records(self,namespace,*,limit=100,offset=0):
        self._ready()
        if limit<1 or offset<0: raise ValueError('invalid pagination')
        with self.connection() as c: rows=c.execute('SELECT * FROM records WHERE namespace=? ORDER BY updated_at DESC,key LIMIT ? OFFSET ?',(namespace,limit,offset)).fetchall()
        return [self._record(x) for x in rows]
    def delete_record(self,namespace,key):
        self._ready()
        with self._lock, self.connection() as c: return c.execute('DELETE FROM records WHERE namespace=? AND key=?',(namespace,key)).rowcount>0
    def count_records(self,namespace):
        self._ready()
        with self.connection() as c: return int(c.execute('SELECT COUNT(*) n FROM records WHERE namespace=?',(namespace,)).fetchone()['n'])
    def append_event(self,event_id,event_type,payload,*,created_at,source=None,context_id=None,job_id=None):
        self._ready()
        with self._lock, self.connection() as c: c.execute('INSERT OR IGNORE INTO events(event_id,event_type,payload_json,created_at,source,context_id,job_id) VALUES(?,?,?,?,?,?,?)',(event_id,event_type,self._dump(payload),created_at,source,context_id,job_id))
    def list_events(self,*,event_type=None,context_id=None,job_id=None,limit=100,after_id=None):
        self._ready(); clauses=[]; params=[]
        for col,val in (('event_type',event_type),('context_id',context_id),('job_id',job_id)):
            if val is not None: clauses.append(f'{col}=?'); params.append(val)
        if after_id is not None: clauses.append('sequence>?'); params.append(after_id)
        where=(' WHERE '+' AND '.join(clauses)) if clauses else ''; params.append(limit)
        with self.connection() as c: rows=c.execute('SELECT * FROM events'+where+' ORDER BY sequence ASC LIMIT ?',params).fetchall()
        return [{'sequence':r['sequence'],'id':r['event_id'],'type':r['event_type'],'payload':json.loads(r['payload_json']),'created_at':r['created_at'],'source':r['source'],'context_id':r['context_id'],'job_id':r['job_id']} for r in rows]
    def close(self): pass
PY

step "Writing repositories and service"
cat > "$BACKEND/app/storage/repositories.py" <<'PY'
from __future__ import annotations
from dataclasses import asdict,is_dataclass
from enum import Enum
from typing import Any,Mapping

def to_payload(item:Any):
    if isinstance(item,Mapping): return dict(item)
    if callable(getattr(item,'to_dict',None)): return dict(item.to_dict())
    if callable(getattr(item,'model_dump',None)): return dict(item.model_dump(mode='json'))
    if is_dataclass(item): return asdict(item)
    if hasattr(item,'__dict__'): return {k:(v.value if isinstance(v,Enum) else v) for k,v in vars(item).items() if not k.startswith('_')}
    raise TypeError(f'Cannot serialize {type(item).__name__}')

class JsonRepository:
    def __init__(self,backend,namespace): self.backend=backend; self.namespace=namespace
    def save_payload(self,item_id,payload): return dict(self.backend.put_record(self.namespace,item_id,payload).payload)
    def save(self,item):
        p=to_payload(item); item_id=str(getattr(item,'id',None) or getattr(item,'context_id',None) or p.get('id') or p.get('context_id') or '')
        if not item_id: raise ValueError(f'{self.namespace} item has no id')
        self.save_payload(item_id,p); return item
    def get_payload(self,item_id):
        r=self.backend.get_record(self.namespace,item_id); return None if r is None else dict(r.payload)
    def list_payloads(self,*,limit=100,offset=0): return [dict(r.payload) for r in self.backend.list_records(self.namespace,limit=limit,offset=offset)]
    def delete(self,item_id): return self.backend.delete_record(self.namespace,item_id)
    def count(self): return self.backend.count_records(self.namespace)

class JobRepository(JsonRepository):
    def __init__(self,b): super().__init__(b,'jobs')
class ContextRepository(JsonRepository):
    def __init__(self,b): super().__init__(b,'contexts')
class PlannerRunRepository(JsonRepository):
    def __init__(self,b): super().__init__(b,'planner_runs')
PY

cat > "$BACKEND/app/storage/service.py" <<'PY'
from __future__ import annotations
import os
from pathlib import Path
from typing import Any,Mapping
from app.storage.repositories import JobRepository,ContextRepository,PlannerRunRepository
from app.storage.sqlite import SQLiteBackend

def resolve_database_path():
    configured=os.getenv('ODIN_DATABASE_PATH') or os.getenv('DATABASE_PATH')
    return Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parents[2]/'data'/'odin.db'

class StorageService:
    def __init__(self,database_path=None):
        self.backend=SQLiteBackend(database_path or resolve_database_path()); self.jobs=JobRepository(self.backend); self.contexts=ContextRepository(self.backend); self.planner_runs=PlannerRunRepository(self.backend)
    def initialize(self): self.backend.initialize()
    def health(self):
        h=self.backend.health(); h['namespaces']={'jobs':self.jobs.count(),'contexts':self.contexts.count(),'planner_runs':self.planner_runs.count()}; return h
    def save_job(self,job): self.jobs.save(job); return job
    def delete_job(self,job_id): return self.jobs.delete(job_id)
    def persist_event(self,event:Any):
        data=dict(event) if isinstance(event,Mapping) else (dict(event.to_dict()) if callable(getattr(event,'to_dict',None)) else {k:v for k,v in vars(event).items() if not k.startswith('_')})
        event_id=str(data.get('id') or data.get('event_id') or ''); event_type=str(data.get('type') or data.get('event_type') or ''); created_at=str(data.get('created_at') or ''); payload=data.get('payload') or {}
        if not event_id or not event_type or not created_at: raise ValueError('event requires id, type, and created_at')
        if not isinstance(payload,Mapping): payload={'value':payload}
        self.backend.append_event(event_id,event_type,payload,created_at=created_at,source=data.get('source'),context_id=data.get('context_id'),job_id=data.get('job_id'))
    def list_persisted_events(self,**kwargs): return self.backend.list_events(**kwargs)
    def close(self): self.backend.close()

storage_service=StorageService()
PY

cat > "$BACKEND/app/storage/__init__.py" <<'PY'
from app.storage.base import StorageBackend,StorageRecord
from app.storage.sqlite import SQLiteBackend
from app.storage.repositories import JsonRepository,JobRepository,ContextRepository,PlannerRunRepository
from app.storage.service import StorageService,storage_service
__all__=['StorageBackend','StorageRecord','SQLiteBackend','JsonRepository','JobRepository','ContextRepository','PlannerRunRepository','StorageService','storage_service']
PY
ok "Storage package created"

step "Writing storage API"
cat > "$BACKEND/app/api/storage.py" <<'PY'
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
PY
ok "Storage API created"

step "Patching main.py"
"$PYTHON_BIN" - "$BACKEND/app/main.py" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); t=p.read_text()
if 'from app.api.storage import router as storage_router' not in t:
    a='from app.api.health import router as health_router'
    if a not in t: raise SystemExit('health import anchor missing')
    t=t.replace(a,a+'\nfrom app.api.storage import router as storage_router',1)
if 'from app.storage.service import storage_service' not in t:
    a='from app.mcp_server import mcp'
    if a not in t: raise SystemExit('mcp import anchor missing')
    t=t.replace(a,a+'\nfrom app.storage.service import storage_service',1)
if 'storage_service.initialize()' not in t:
    a='async def lifespan(app: FastAPI):'
    if a not in t: raise SystemExit('lifespan anchor missing')
    t=t.replace(a,a+'\n    storage_service.initialize()',1)
if 'app.include_router(storage_router)' not in t:
    for a in ('app.include_router(events_router)','app.include_router(jobs_router)','app.include_router(health_router)'):
        if a in t: t=t.replace(a,a+'\napp.include_router(storage_router)',1); break
    else: raise SystemExit('router anchor missing')
p.write_text(t)
print('main.py patched')
PY
ok "main.py patched"

step "Adding best-effort persistence hooks"
"$PYTHON_BIN" - "$BACKEND/app/jobs/manager.py" "$BACKEND/app/events/bus.py" <<'PY'
from pathlib import Path
import sys
imp='from app.storage.service import storage_service'
for filename,kind in ((sys.argv[1],'job'),(sys.argv[2],'event')):
    p=Path(filename); t=p.read_text()
    if imp not in t:
        lines=t.splitlines(); idx=0
        while idx<len(lines) and (not lines[idx].strip() or lines[idx].startswith('from __future__')): idx+=1
        lines.insert(idx,imp); t='\n'.join(lines)+'\n'
    if kind=='job' and 'storage_service.save_job(job)' not in t:
        for old,new in [('        return job\n','        storage_service.save_job(job)\n        return job\n'),('            return job\n','            storage_service.save_job(job)\n            return job\n')]:
            if old in t: t=t.replace(old,new)
    if kind=='event' and 'storage_service.persist_event(event)' not in t:
        for old in ('            self._history.append(event)\n','        self._history.append(event)\n','            self.history.append(event)\n','        self.history.append(event)\n'):
            if old in t:
                ind=old[:len(old)-len(old.lstrip())]
                t=t.replace(old,old+ind+'try:\n'+ind+'    storage_service.persist_event(event)\n'+ind+'except Exception:\n'+ind+'    pass\n',1); break
    p.write_text(t)
print('Persistence hooks processed')
PY
ok "Persistence hooks processed"

step "Updating .gitignore"
touch "$ROOT/.gitignore"
for x in '.odin-backups/' '__pycache__/' '*.py[cod]' 'backend/data/*.db' 'backend/data/*.db-shm' 'backend/data/*.db-wal'; do grep -qxF "$x" "$ROOT/.gitignore" || echo "$x" >> "$ROOT/.gitignore"; done
ok ".gitignore updated"

printf '\n============================================================\nVALIDATING MILESTONE 12\n============================================================\n'
cd "$BACKEND"
step "Compiling files"
"$PYTHON_BIN" -m py_compile app/storage/base.py app/storage/sqlite.py app/storage/repositories.py app/storage/service.py app/api/storage.py app/main.py
ok "Syntax validation passed"

step "Testing persistence"
ODIN_DATABASE_PATH="$BACKUP_DIR/test-storage.db" "$PYTHON_BIN" - <<'PY'
import os
from app.storage.sqlite import SQLiteBackend
b=SQLiteBackend(os.environ['ODIN_DATABASE_PATH']); b.initialize()
a=b.put_record('tests','alpha',{'value':1}); assert a.version==1
a=b.put_record('tests','alpha',{'value':2}); assert a.version==2
assert b.get_record('tests','alpha').payload['value']==2
b.append_event('e1','test.created',{'ok':True},created_at='2026-01-01T00:00:00+00:00',job_id='j1')
assert b.list_events(job_id='j1')[0]['payload']['ok'] is True
assert b.health()['status']=='ok'
print('SQLite tests passed.')
PY
ok "Persistence tests passed"

step "Testing API routes"
ODIN_DATABASE_PATH="$BACKUP_DIR/test-api.db" "$PYTHON_BIN" - <<'PY'
from app.main import app
paths=set(app.openapi().get('paths',{}))
required={'/storage/health','/storage/events','/storage/records/{namespace}','/storage/records/{namespace}/{record_id}'}
missing=required-paths
if missing:
    print('Discovered routes:',*sorted(paths),sep='\n  ')
    raise AssertionError(f'Missing routes: {sorted(missing)}')
print('Storage routes passed.')
PY
ok "API route validation passed"

step "Compiling full backend"
"$PYTHON_BIN" -m compileall -q app
ok "Full backend compilation passed"

printf '\n============================================================\n✅ ODIN MILESTONE 12 INSTALLED SUCCESSFULLY\n============================================================\n'
cat <<EOF
Created:
  backend/app/storage/base.py
  backend/app/storage/sqlite.py
  backend/app/storage/repositories.py
  backend/app/storage/service.py
  backend/app/storage/__init__.py
  backend/app/api/storage.py

Updated:
  backend/app/main.py
  backend/app/jobs/manager.py
  backend/app/events/bus.py
  .gitignore

Default database:
  backend/data/odin.db

Override with:
  ODIN_DATABASE_PATH=/absolute/path/to/odin.db

Backups:
  $BACKUP_DIR
EOF
cd "$ROOT"
git status --short || true
printf '\nRecommended commit:\n'
printf 'git add . && git commit -m "Milestone 12: persistent SQLite storage foundation"\n'
