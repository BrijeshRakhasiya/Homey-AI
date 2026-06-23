"""
schemas/retrieval.py
Chunk metadata + retrieval result types.
Every chunk in the FAISS index must have this metadata attached.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date
from schemas.outbound import TrustReceipt


class ChunkMetadata(BaseModel):
    source_id: str
    source_type: str          # "faq" | "policy" | "listing" | "internal_note"
    owner: str                # "nikunj" | "gabe" | "broker_xyz"
    created_date: date
    sensitivity: str          # "public" | "internal" | "restricted"
    allowed_audience: List[str]  # ["renter"] | ["broker"] | ["all"]
    is_stale: bool = False
    claim_key: Optional[str] = None
    claim_value: Optional[str] = None


class RetrievedChunk(BaseModel):
    text: str
    metadata: ChunkMetadata
    score: float


class RetrievalResult(BaseModel):
    query: str
    audience: str
    chunks: List[RetrievedChunk] = []
    evidence_sufficient: bool = False
    fallback_message: Optional[str] = None
    dashboard_event: dict = {}
    trust_receipt: TrustReceipt = Field(default_factory=TrustReceipt)
