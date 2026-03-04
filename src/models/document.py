# src/models/document.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from .enums import OriginType, LayoutComplexity, DomainHint, StrategyType, ChunkType, ConfidenceLevel

class PageAnalysis(BaseModel):
    """Analysis results for a single page"""
    page_number: int
    char_count: int
    image_count: int
    image_ratio: float
    table_count: int
    has_text: bool
    likely_scanned: bool
    width: float
    height: float

class DocumentProfile(BaseModel):
    """Complete profile of a document after triage analysis"""
    doc_id: str
    filename: str
    file_path: str
    file_size_mb: float
    total_pages: int
    analyzed_pages: int = 5
    
    origin_type: OriginType
    origin_confidence: float
    origin_signals: Dict[str, Any] = Field(default_factory=dict)
    
    avg_chars_per_page: float
    min_chars_per_page: float
    max_chars_per_page: float
    chars_std_dev: Optional[float] = None
    
    avg_image_ratio: float
    pages_with_images: int
    total_images: int
    
    layout_complexity: LayoutComplexity
    layout_confidence: float
    has_tables: bool
    has_multi_column: bool
    has_figures: bool
    
    domain_hint: DomainHint
    domain_confidence: float
    domain_keywords_found: Dict[str, int] = Field(default_factory=dict)
    
    language: str = "en"
    language_confidence: float = 0.9
    
    recommended_strategy: StrategyType
    recommendation_reason: str
    
    estimated_cost_usd: float
    processing_time_estimate_sec: int
    
    profile_confidence: ConfidenceLevel
    
    page_details: List[PageAnalysis] = Field(default_factory=list)
    
    created_at: datetime = Field(default_factory=datetime.now)
    profile_version: str = "1.0"
    
    def save(self, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{self.doc_id}.json"
        output_path.write_text(self.model_dump_json(indent=2))
        return output_path

class TextBlock(BaseModel):
    """A block of text with spatial information"""
    text: str
    bbox: Tuple[float, float, float, float]  # x1, y1, x2, y2
    page_num: int
    block_type: str = "text"

class Table(BaseModel):
    """Extracted table structure"""
    headers: List[str]
    rows: List[List[str]]
    bbox: Tuple[float, float, float, float]
    page_num: int
    caption: Optional[str] = None

class Figure(BaseModel):
    """Extracted figure with caption"""
    caption: Optional[str]
    bbox: Tuple[float, float, float, float]
    page_num: int
    image_path: Optional[str] = None

class ExtractedDocument(BaseModel):
    """Normalized extraction result from any strategy"""
    doc_id: str
    filename: str
    total_pages: int
    text_blocks: List[TextBlock] = Field(default_factory=list)
    tables: List[Table] = Field(default_factory=list)
    figures: List[Figure] = Field(default_factory=list)
    extraction_strategy: StrategyType
    confidence_score: float
    processing_time_sec: float
    cost_usd: float
    created_at: datetime = Field(default_factory=datetime.now)

class LDU(BaseModel):
    """Logical Document Unit - semantic chunk"""
    ldu_id: str
    content: str
    chunk_type: ChunkType
    page_refs: List[int]
    bbox: Optional[Tuple[float, float, float, float]] = None
    parent_section: Optional[str] = None
    token_count: int
    content_hash: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class PageIndexNode(BaseModel):
    """Node in PageIndex navigation tree"""
    id: str
    title: str
    page_start: int
    page_end: int
    child_sections: List["PageIndexNode"] = Field(default_factory=list)
    key_entities: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    data_types_present: List[str] = Field(default_factory=list)

class PageIndex(BaseModel):
    """Complete navigation tree for document"""
    doc_id: str
    filename: str
    root_sections: List[PageIndexNode] = Field(default_factory=list)
    total_pages: int
    created_at: datetime = Field(default_factory=datetime.now)

class Source(BaseModel):
    """Source citation for provenance"""
    document_name: str
    page_number: int
    bbox: Tuple[float, float, float, float]
    content_hash: str

class ProvenanceChain(BaseModel):
    """Complete provenance for an answer"""
    claim: str
    sources: List[Source] = Field(default_factory=list)
    verified: bool = False
    confidence: float = 1.0
class DocumentProfileSummary(BaseModel):
    """Lightweight summary for quick viewing"""
    doc_id: str
    filename: str
    origin_type: OriginType
    layout_complexity: LayoutComplexity
    domain_hint: DomainHint
    recommended_strategy: StrategyType
    profile_confidence: ConfidenceLevel
    estimated_cost_usd: float
    created_at: datetime
    
    @classmethod
    def from_profile(cls, profile: DocumentProfile) -> "DocumentProfileSummary":
        return cls(
            doc_id=profile.doc_id,
            filename=profile.filename,
            origin_type=profile.origin_type,
            layout_complexity=profile.layout_complexity,
            domain_hint=profile.domain_hint,
            recommended_strategy=profile.recommended_strategy,
            profile_confidence=profile.profile_confidence,
            estimated_cost_usd=profile.estimated_cost_usd,
            created_at=profile.created_at
        )