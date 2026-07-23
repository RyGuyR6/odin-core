from __future__ import annotations
import json, sqlite3, threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping
from app.storage.base import StorageBackend, StorageRecord, utc_now_iso
from odin_shared.sqlite_persistence import connect_sqlite

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
        return connect_sqlite(self.database_path, check_same_thread=False, synchronous="NORMAL", busy_timeout_ms=30000)
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
