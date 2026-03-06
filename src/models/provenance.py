"""
Provenance models for tracking source of every answer.
Enables auditability and verification of all claims.
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime
import hashlib


class BBox(BaseModel):
    """Bounding box coordinates for spatial provenance"""
    x0: float
    y0: float
    x1: float
    y1: float
    page_num: int
    
    @field_validator('x1')
    def x1_must_be_greater_than_x0(cls, v, info):
        if 'x0' in info.data and v <= info.data['x0']:
            raise ValueError(f'x1 ({v}) must be > x0 ({info.data["x0"]})')
        return v
    
    @field_validator('y1')
    def y1_must_be_greater_than_y0(cls, v, info):
        if 'y0' in info.data and v <= info.data['y0']:
            raise ValueError(f'y1 ({v}) must be > y0 ({info.data["y0"]})')
        return v
    
    def to_tuple(self) -> Tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)


class SourceCitation(BaseModel):
    """Single source citation for a claim"""
    document_name: str
    page_number: int = Field(gt=0)
    bbox: BBox
    content_hash: str = Field(min_length=16, max_length=64)
    extracted_text: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    
    @field_validator('content_hash')
    def validate_hash_format(cls, v):
        if len(v) != 16:
            raise ValueError(f'content_hash must be 16 chars, got {len(v)}')
        try:
            int(v, 16)
        except ValueError:
            raise ValueError(f'content_hash must be hex, got {v}')
        return v


class ProvenanceChain(BaseModel):
    """Complete provenance for an answer - tracks every source"""
    claim: str
    sources: List[SourceCitation] = Field(default_factory=list)  # ← Remove min_length=1
    synthesized_answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    verification_status: str = Field(..., pattern='^(verified|partial|unverifiable)$')
    query_time: datetime = Field(default_factory=datetime.now)
    query_id: str = Field(default_factory=lambda: hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8])
    
    @model_validator(mode='after')
    def validate_verification(self):
        # Verified claims MUST have sources
        if self.verification_status == 'verified' and not self.sources:
            raise ValueError('Verified claim must have at least one source')
        # Verified claims should have high confidence
        if self.verification_status == 'verified' and self.confidence < 0.9:
            raise ValueError(f'Verified claim has low confidence: {self.confidence}')
        # Unverifiable claims should have no sources
        if self.verification_status == 'unverifiable' and self.sources:
            raise ValueError('Unverifiable claim cannot have sources')
        return self
    
    def to_markdown(self) -> str:
        """Format as markdown with citations"""
        lines = [f"**Answer:** {self.synthesized_answer}"]
        lines.append(f"\n*Confidence: {self.confidence:.1%}*")
        lines.append(f"\n**Sources:**")
        
        for i, src in enumerate(self.sources, 1):
            lines.append(f"\n  {i}. 📄 `{src.document_name}`")
            lines.append(f"     Page {src.page_number}, {src.bbox}")
            lines.append(f"     Hash: `{src.content_hash}`")
            if src.extracted_text:
                lines.append(f"     Text: \"{src.extracted_text[:100]}...\"")
        
        lines.append(f"\n*Verification: {self.verification_status}*")
        lines.append(f"*Query ID: {self.query_id}*")
        
        return '\n'.join(lines)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return self.model_dump()


class Fact(BaseModel):
    """A single fact extracted from document"""
    fact_id: str
    document_name: str
    doc_id: str 
    fact_type: str  # 'revenue', 'date', 'name', 'value', etc.
    key: str
    value: str
    page_number: int
    bbox: BBox
    content_hash: str
    confidence: float = Field(ge=0.0, le=1.0)
    context: Optional[str] = None
    extracted_at: datetime = Field(default_factory=datetime.now)
    
    @field_validator('value')
    def value_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Fact value cannot be empty')
        return v.strip()


class FactTable(BaseModel):
    """Collection of facts from a document"""
    document_name: str
    doc_id: str
    facts: List[Fact]
    extraction_date: datetime = Field(default_factory=datetime.now)
    fact_count: int = 0
    
    @model_validator(mode='after')
    def update_count(self):
        self.fact_count = len(self.facts)
        return self