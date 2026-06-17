"""
agents/retrieval_gov.py  — Task 3: Retrieval Governance
Source-filtered RAG. Makes retrieval behave like controlled evidence.

Rules:
  - internal_note chunks NEVER surface to renter audience
  - restricted chunks are blocked for ALL audiences
  - stale sources change answer behavior (fallback, not silence)
  - insufficient evidence → safe fallback message, not hallucination

Why a structured layer?
  - Audience filtering is a policy, not a prompt instruction
  - Stale-source detection is deterministic — no LLM needed
  - Each rule is independently testable
  - Dhruv can track evidence_sufficient rate as a content gap metric
"""

from datetime import date, timedelta
from typing import List, Optional, Tuple
import numpy as np

from schemas.retrieval import ChunkMetadata, RetrievedChunk, RetrievalResult
from observability.stream import emit_retrieval_event

# ─── Lazy-load heavy deps ─────────────────────────────────────────────────────
_model = None
_index = None
_chunks: List[Tuple[str, ChunkMetadata]] = []


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


# ─── Governance rules ─────────────────────────────────────────────────────────

def is_chunk_allowed(meta: ChunkMetadata, audience: str) -> bool:
    """
    Return True only if this chunk is safe to show to this audience.

    Failure case: internal_note requested by renter → blocked silently.
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


def mark_stale(meta: ChunkMetadata, max_age_days: int = 90) -> ChunkMetadata:
    """Mark a chunk stale if its created_date is older than max_age_days."""
    cutoff = date.today() - timedelta(days=max_age_days)
    if meta.created_date < cutoff:
        meta = meta.model_copy(update={"is_stale": True})
    return meta


# ─── Index builder (call once at startup) ────────────────────────────────────

def build_index(corpus: List[Tuple[str, ChunkMetadata]]):
    """Build FAISS index from (text, metadata) pairs."""
    import faiss
    global _index, _chunks
    model = _get_model()
    texts = [text for text, _ in corpus]
    vecs  = model.encode(texts, show_progress_bar=False).astype("float32")
    dim   = vecs.shape[1]
    _index = faiss.IndexFlatL2(dim)
    _index.add(vecs)
    _chunks = corpus
    return _index


# ─── Sample corpus for demo / tests ──────────────────────────────────────────

SAMPLE_CORPUS: List[Tuple[str, ChunkMetadata]] = [
    (
        "VryfID verifies income through bank statement uploads and pay stubs.",
        ChunkMetadata(
            source_id="faq-001", source_type="faq", owner="nikunj",
            created_date=date.today(), sensitivity="public",
            allowed_audience=["all"], is_stale=False,
        ),
    ),
    (
        "Renters must complete their profile before being matched with a listing.",
        ChunkMetadata(
            source_id="policy-001", source_type="policy", owner="nikunj",
            created_date=date.today(), sensitivity="public",
            allowed_audience=["all"], is_stale=False,
        ),
    ),
    (
        "Broker note: this renter's credit report shows 620 score — flag for review.",
        ChunkMetadata(
            source_id="internal-001", source_type="internal_note", owner="broker_xyz",
            created_date=date.today(), sensitivity="internal",
            allowed_audience=["broker"], is_stale=False,
        ),
    ),
    (
        "Brooklyn listings are available from $2,200/mo for 1BHK.",
        ChunkMetadata(
            source_id="listing-001", source_type="listing", owner="gabe",
            created_date=date.today(), sensitivity="public",
            allowed_audience=["all"], is_stale=False,
        ),
    ),
    (
        "Restricted background report: eviction record found in 2019.",
        ChunkMetadata(
            source_id="restricted-001", source_type="policy", owner="nikunj",
            created_date=date.today(), sensitivity="restricted",
            allowed_audience=[], is_stale=False,
        ),
    ),
    (
        "Old listing policy from 2021 — superseded by current guidelines.",
        ChunkMetadata(
            source_id="stale-001", source_type="policy", owner="nikunj",
            created_date=date(2021, 1, 1), sensitivity="public",
            allowed_audience=["all"], is_stale=True,
        ),
    ),
]


# ─── Main retrieval function ──────────────────────────────────────────────────

def governed_retrieval(
    query: str,
    audience: str,
    session_id: str = "default",
    top_k: int = 3,
) -> RetrievalResult:
    """
    Run audience-filtered, stale-aware retrieval.

    Failure case: 0 allowed chunks → evidence_sufficient=False → safe fallback returned.
    Dashboard event: retrieval_governed with chunks_returned and evidence_sufficient.
    """
    import faiss

    if _index is None or not _chunks:
        build_index(SAMPLE_CORPUS)

    model = _get_model()
    query_vec = model.encode([query]).astype("float32")
    fetch_k   = min(top_k * 4, len(_chunks))
    distances, indices = _index.search(query_vec, fetch_k)

    allowed: List[RetrievedChunk] = []
    for idx, dist in zip(indices[0], distances[0]):
        if idx < 0 or idx >= len(_chunks):
            continue
        text, meta = _chunks[idx]
        meta = mark_stale(meta)
        if is_chunk_allowed(meta, audience):
            allowed.append(RetrievedChunk(text=text, metadata=meta, score=float(dist)))
        if len(allowed) == top_k:
            break

    evidence_sufficient = len(allowed) >= 2
    fallback: Optional[str] = None
    if not evidence_sufficient:
        fallback = (
            "I don't have enough verified information to answer that right now. "
            "Please contact the VryfID support team or check back after completing your profile."
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
