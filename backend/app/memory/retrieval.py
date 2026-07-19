from __future__ import annotations
import json, math, re
from .embeddings import cosine_similarity

def keyword_similarity(query: str, text: str) -> float:
    q=set(re.findall(r"[a-z0-9_]+",query.lower())); t=set(re.findall(r"[a-z0-9_]+",text.lower()))
    if not q: return 0.0
    return len(q & t) / len(q)

def combine_scores(semantic: float, keyword: float, mode: str) -> float:
    semantic=max(0.0,(semantic+1.0)/2.0)
    if mode == "semantic": return semantic
    if mode == "keyword": return keyword
    return 0.68*semantic + 0.32*keyword

def metadata_matches(row, request) -> bool:
    if request.scope and row["scope"] != request.scope: return False
    if request.project_id and row["project_id"] != request.project_id: return False
    if request.conversation_id and row["conversation_id"] != request.conversation_id: return False
    if request.kinds and row["kind"] not in request.kinds: return False
    tags=json.loads(row["tags_json"])
    if request.tags and not set(request.tags).issubset(set(tags)): return False
    return True
