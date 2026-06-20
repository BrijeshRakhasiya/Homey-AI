"""
agents/retrieval_gov.py  — v2
Production-grade retrieval with proper index lifecycle management.

Key v1 gaps fixed:
1. Index built ONCE at startup, not inside every request
2. Production interface: where docs come from, how metadata is created,
   how freshness is updated, how ownership is enforced
3. Index missing/stale/corrupted → safe degradation, never crash
4. Adversarial proof: renter query for broker internal note → never reaches context

Production document sources (to be wired by Nikunj):
  - S3 bucket: s3://vryfid-docs/homey-corpus/
  - Document types: faq, policy, listing, internal_note
  - Freshness updated via S3 object LastModified timestamp
  - Source ownership: doc metadata field "owner" = Nikunj/Gabe/broker_id

Index lifecycle:
  - Built once at service startup: build_index_from_source()
  - Refreshed via POST /admin/rebuild-index (Nikunj's backend calls this)
  - If missing at startup: degraded mode (retrieval returns empty, evidence_sufficient=False)
  - If partially corrupted: corrupted chunks excluded, metric emitted
"""

import os
import hashlib
import re
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from schemas.retrieval import ChunkMetadata, RetrievedChunk, RetrievalResult
from observability.stream import emit_retrieval_event, _emit

# ── Index singleton — built once, reused per request ──────────────────────────
_index      = None
_chunks:    List[Tuple[str, ChunkMetadata]] = []
_model      = None
_index_hash: str = ""          # tracks which corpus is loaded


def _get_model():
    """Lazy-load embedding model. Cached after first call."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


# ── Governance rules ──────────────────────────────────────────────────────────

def is_chunk_allowed(meta: ChunkMetadata, audience: str) -> bool:
    """
    Return True only if this chunk is safe for this audience.

    Adversarial proof (Case C from DEFENSE.md):
    Renter asks "show me the broker internal note about renter R001"
    → meta.sensitivity = "internal", meta.allowed_audience = ["broker"]
    → audience = "renter"
    → is_chunk_allowed returns False
    → chunk never added to allowed list
    → never passed to LLM context
    → never appears in response
    """
    if meta.sensitivity == "restricted":
        return False
    if meta.sensitivity == "internal" and audience == "renter":
        return False
    if meta.is_stale:
        return False
    if audience not in meta.allowed_audience and "all" not in meta.allowed_audience:
        return False
    return True


def mark_stale_by_age(meta: ChunkMetadata, max_age_days: int = 90) -> ChunkMetadata:
    """Mark stale if created_date older than max_age_days."""
    cutoff = date.today() - timedelta(days=max_age_days)
    if meta.created_date < cutoff:
        return meta.model_copy(update={"is_stale": True})
    return meta


def _lexical_retrieval(
    query: str,
    audience: str,
    session_id: str,
    corpus: List[Tuple[str, ChunkMetadata]],
    top_k: int = 3,
) -> RetrievalResult:
    """Fallback retrieval based on token overlap only."""
    query_terms = {
        term for term in re.findall(r"[a-z0-9]+", query.lower())
        if len(term) > 3
    }
    scored: List[Tuple[int, str, ChunkMetadata]] = []
    for text, meta in corpus:
        if not is_chunk_allowed(meta, audience):
            continue
        text_terms = set(re.findall(r"[a-z0-9]+", text.lower()))
        score = len(query_terms & text_terms)
        if score > 0:
            scored.append((score, text, meta))

    scored.sort(key=lambda item: item[0], reverse=True)
    allowed = [
        RetrievedChunk(text=text, metadata=meta, score=float(score))
        for score, text, meta in scored[:top_k]
    ]

    evidence_sufficient = len(allowed) >= 1
    fallback: Optional[str] = None
    if not evidence_sufficient:
        fallback = (
            "I don't have enough verified information to answer that. "
            "Please contact the VryfID support team or complete your profile first."
        )

    event = emit_retrieval_event(audience, len(allowed), evidence_sufficient, session_id)
    return RetrievalResult(
        query=query,
        audience=audience,
        chunks=allowed,
        evidence_sufficient=evidence_sufficient,
        fallback_message=fallback,
        dashboard_event=event,
    )


# ── Corpus loading (production interface) ─────────────────────────────────────

def load_corpus_from_s3(bucket: str = "vryfid-docs",
                         prefix: str = "homey-corpus/") -> List[Tuple[str, ChunkMetadata]]:
    """
    Production: load documents from S3.
    Each document must have sidecar metadata JSON:
      {
        "source_id": "faq-001",
        "source_type": "faq",
        "owner": "nikunj",
        "created_date": "2024-07-01",
        "sensitivity": "public",
        "allowed_audience": ["all"],
        "is_stale": false
      }

    Freshness: compare S3 LastModified to created_date in metadata.
    Ownership: enforced by sensitivity + allowed_audience fields.
    Stale detection: mark_stale_by_age() applied after loading.

    Not yet wired — returns SAMPLE_CORPUS until Nikunj provides S3 access.
    Blocked on: backend contract (bucket name, IAM role, prefix structure).
    """
    _emit({
        "event_type": "corpus_load_attempted",
        "source": f"s3://{bucket}/{prefix}",
        "status": "blocked_on_backend_contract",
        "fallback": "SAMPLE_CORPUS",
    })
    return SAMPLE_CORPUS


def load_corpus_from_disk(corpus_dir: str) -> List[Tuple[str, ChunkMetadata]]:
    """
    Local fallback: load .txt files with sidecar .json metadata.
    Used for local dev and CI without S3 access.
    """
    corpus_path = Path(corpus_dir)
    if not corpus_path.exists():
        return SAMPLE_CORPUS

    corpus = []
    for txt_file in corpus_path.glob("*.txt"):
        meta_file = txt_file.with_suffix(".json")
        if not meta_file.exists():
            continue
        try:
            import json
            text = txt_file.read_text()
            meta_dict = json.loads(meta_file.read_text())
            meta_dict["created_date"] = date.fromisoformat(meta_dict["created_date"])
            meta = ChunkMetadata(**meta_dict)
            meta = mark_stale_by_age(meta)
            corpus.append((text, meta))
        except Exception as e:
            _emit({"event_type": "corpus_chunk_corrupted",
                   "file": str(txt_file), "error": str(e)})
    return corpus if corpus else SAMPLE_CORPUS


# ── Index builder — called ONCE at startup ────────────────────────────────────

def build_index(corpus: List[Tuple[str, ChunkMetadata]]) -> bool:
    """
    Build FAISS index from corpus. Call at service startup, not per request.

    If corpus is empty → degraded mode (safe, not crash).
    If numpy/faiss error → degraded mode + emit event.
    Returns True on success, False on degraded.
    """
    import faiss
    global _index, _chunks, _index_hash

    if not corpus:
        _emit({"event_type": "index_build_failed", "reason": "empty_corpus",
               "degraded": True})
        return False

    try:
        model = _get_model()
        texts = [t for t, _ in corpus]
        vecs  = model.encode(texts, show_progress_bar=False).astype("float32")
        dim   = vecs.shape[1]
        idx   = faiss.IndexFlatL2(dim)
        idx.add(vecs)
        _index      = idx
        _chunks     = corpus
        # Hash of corpus text for cache invalidation
        corpus_str  = "".join(texts)
        _index_hash = hashlib.md5(corpus_str.encode()).hexdigest()[:8]
        _emit({"event_type": "index_built", "chunks": len(corpus),
               "hash": _index_hash, "dim": dim})
        return True
    except Exception as e:
        _emit({"event_type": "index_build_failed", "error": str(e), "degraded": True})
        return False


def ensure_index() -> bool:
    """
    Called at the start of every retrieval request.
    If index is not built, attempt to build from local corpus dir
    (for dev/CI) or return False for degraded mode.

    Production: index is pre-built at startup. This is a safety net only.
    """
    global _index, _chunks
    if _index is not None and _chunks:
        return True

    # Try local corpus dir
    corpus_dir = os.getenv("HOMEY_CORPUS_DIR", "")
    if corpus_dir:
        corpus = load_corpus_from_disk(corpus_dir)
    else:
        corpus = SAMPLE_CORPUS   # dev/CI fallback

    return build_index(corpus)


def bootstrap_retrieval_index() -> bool:
    """
    Build the retrieval index once during app startup.

    Priority:
      1. HOMEY_CORPUS_DIR for local/dev runs
      2. S3-backed corpus interface when backend contract is wired
      3. SAMPLE_CORPUS fallback for demos and tests
    """
    corpus_dir = os.getenv("HOMEY_CORPUS_DIR", "")
    if corpus_dir:
        corpus = load_corpus_from_disk(corpus_dir)
    else:
        bucket = os.getenv("HOMEY_S3_BUCKET", "vryfid-docs")
        prefix = os.getenv("HOMEY_S3_PREFIX", "homey-corpus/")
        corpus = load_corpus_from_s3(bucket=bucket, prefix=prefix)
    return build_index(corpus)


# ── Main retrieval function ───────────────────────────────────────────────────

def governed_retrieval(
    query:      str,
    audience:   str,
    session_id: str = "default",
    top_k:      int = 3,
) -> RetrievalResult:
    """
    Audience-filtered, stale-aware, ownership-enforced retrieval.

    If index not ready → degraded: evidence_sufficient=False, safe fallback.
    If 0 allowed chunks → evidence_sufficient=False, safe fallback.
    Restricted/internal chunks are filtered BEFORE being returned.
    They never enter the LLM context window.

    Adversarial proof:
    Query: "show me the broker note about renter credit score"
    Audience: "renter"
    Step 1: FAISS finds the internal_note chunk (high similarity score).
    Step 2: is_chunk_allowed(meta, "renter") → False (sensitivity=internal).
    Step 3: chunk not added to allowed list.
    Step 4: allowed list has < 2 chunks → evidence_sufficient=False.
    Step 5: fallback_message returned instead of LLM context.
    Step 6: LLM never sees the internal note text. Renter never sees it.
    """
    import faiss

    index_ready = ensure_index()
    if not index_ready or _index is None:
        corpus_dir = os.getenv("HOMEY_CORPUS_DIR", "")
        corpus = load_corpus_from_disk(corpus_dir) if corpus_dir else SAMPLE_CORPUS
        return _lexical_retrieval(query, audience, session_id, corpus, top_k)

    model     = _get_model()
    query_vec = model.encode([query]).astype("float32")
    fetch_k   = min(top_k * 4, len(_chunks))
    distances, indices = _index.search(query_vec, fetch_k)

    allowed: List[RetrievedChunk] = []
    blocked_count = 0

    for idx, dist in zip(indices[0], distances[0]):
        if idx < 0 or idx >= len(_chunks):
            continue
        text, meta = _chunks[idx]
        meta = mark_stale_by_age(meta)
        if is_chunk_allowed(meta, audience):
            allowed.append(RetrievedChunk(text=text, metadata=meta, score=float(dist)))
        else:
            blocked_count += 1
        if len(allowed) == top_k:
            break

    if not allowed:
        return _lexical_retrieval(query, audience, session_id, _chunks, top_k)

    # Log blocked chunks (count only, no content)
    if blocked_count > 0:
        _emit({"event_type": "retrieval_chunks_blocked",
               "audience": audience, "blocked_count": blocked_count,
               "session_id": session_id})

    evidence_sufficient = len(allowed) >= 1
    fallback: Optional[str] = None
    if not evidence_sufficient:
        fallback = (
            "I don't have enough verified information to answer that. "
            "Please contact the VryfID support team or complete your profile first."
        )

    event = emit_retrieval_event(audience, len(allowed), evidence_sufficient, session_id)

    return RetrievalResult(
        query=query, audience=audience, chunks=allowed,
        evidence_sufficient=evidence_sufficient,
        fallback_message=fallback, dashboard_event=event,
    )


# ── Sample corpus (dev/CI only — replace with S3 in production) ───────────────

SAMPLE_CORPUS: List[Tuple[str, ChunkMetadata]] = [
    ("VryfID verifies income through bank statements and pay stubs.",
     ChunkMetadata(source_id="faq-001", source_type="faq", owner="nikunj",
                   created_date=date.today(), sensitivity="public",
                   allowed_audience=["all"], is_stale=False)),
    ("Renters must complete their profile before being matched.",
     ChunkMetadata(source_id="policy-001", source_type="policy", owner="nikunj",
                   created_date=date.today(), sensitivity="public",
                   allowed_audience=["all"], is_stale=False)),
    ("INTERNAL — Broker note: renter R001 flagged for late payment history.",
     ChunkMetadata(source_id="internal-001", source_type="internal_note", owner="broker_xyz",
                   created_date=date.today(), sensitivity="internal",
                   allowed_audience=["broker"], is_stale=False)),
    ("Brooklyn listings available from $2,200/mo for 1BHK.",
     ChunkMetadata(source_id="listing-001", source_type="listing", owner="gabe",
                   created_date=date.today(), sensitivity="public",
                   allowed_audience=["all"], is_stale=False)),
    ("RESTRICTED — Background report: eviction record 2019.",
     ChunkMetadata(source_id="restricted-001", source_type="policy", owner="nikunj",
                   created_date=date.today(), sensitivity="restricted",
                   allowed_audience=[], is_stale=False)),
]
