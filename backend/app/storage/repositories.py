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
