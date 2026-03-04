# src/models/document.py
from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import hashlib

from .enums import OriginType, LayoutComplexity, DomainHint, StrategyType, ChunkType, ConfidenceLevel


class BBox(BaseModel):
    """Structured bounding box model with validation"""
    x0: float
    y0: float
    x1: float
    y1: float
    page_num: int
    
    @field_validator('x1')
    def x1_must_be_greater_than_x0(cls, v, info):
        if 'x0' in info.data and v <= info.data['x0']:
            raise ValueError(f'x1 ({v}) must be greater than x0 ({info.data["x0"]})')
        return v
    
    @field_validator('y1')
    def y1_must_be_greater_than_y0(cls, v, info):
        if 'y0' in info.data and v <= info.data['y0']:
            raise ValueError(f'y1 ({v}) must be greater than y0 ({info.data["y0"]})')
        return v
    
    @field_validator('page_num')
    def page_num_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError(f'page_num ({v}) must be positive')
        return v
    
    def to_tuple(self) -> Tuple[float, float, float, float]:
        """Convert to tuple for backward compatibility"""
        return (self.x0, self.y0, self.x1, self.y1)
    
    @classmethod
    def from_tuple(cls, bbox_tuple: Tuple[float, float, float, float], page_num: int) -> "BBox":
        """Create from tuple for backward compatibility"""
        return cls(x0=bbox_tuple[0], y0=bbox_tuple[1], x1=bbox_tuple[2], y1=bbox_tuple[3], page_num=page_num)


class PageAnalysis(BaseModel):
    """Analysis results for a single page"""
    page_number: int = Field(gt=0)
    char_count: int = Field(ge=0)
    image_count: int = Field(ge=0)
    image_ratio: float = Field(ge=0.0, le=1.0)
    table_count: int = Field(ge=0)
    has_text: bool
    likely_scanned: bool
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    
    @field_validator('image_ratio')
    def validate_image_ratio(cls, v):
        if v < 0 or v > 1:
            raise ValueError(f'image_ratio must be between 0 and 1, got {v}')
        return v
    
    @property
    def char_density(self) -> float:
        """Characters per square point"""
        area = self.width * self.height
        return self.char_count / area if area > 0 else 0


class DocumentProfile(BaseModel):
    """Complete profile of a document after triage analysis"""
    doc_id: str = Field(min_length=8, max_length=32)
    filename: str
    file_path: str
    file_size_mb: float = Field(gt=0)
    total_pages: int = Field(gt=0)
    analyzed_pages: int = Field(ge=1, le=10, default=5)

    origin_type: OriginType
    origin_confidence: float = Field(ge=0.0, le=1.0)
    origin_signals: Dict[str, Any] = Field(default_factory=dict)

    avg_chars_per_page: float = Field(ge=0)
    min_chars_per_page: float = Field(ge=0)
    max_chars_per_page: float = Field(ge=0)
    chars_std_dev: Optional[float] = Field(None, ge=0)

    avg_image_ratio: float = Field(ge=0.0, le=1.0)
    pages_with_images: int = Field(ge=0)
    total_images: int = Field(ge=0)

    layout_complexity: LayoutComplexity
    layout_confidence: float = Field(ge=0.0, le=1.0)
    has_tables: bool
    has_multi_column: bool
    has_figures: bool

    domain_hint: DomainHint
    domain_confidence: float = Field(ge=0.0, le=1.0)
    domain_keywords_found: Dict[str, int] = Field(default_factory=dict)

    language: str = "en"
    language_confidence: float = Field(ge=0.0, le=1.0, default=0.9)

    recommended_strategy: StrategyType
    recommendation_reason: str

    estimated_cost_usd: float = Field(ge=0)
    processing_time_estimate_sec: int = Field(ge=0)

    profile_confidence: ConfidenceLevel

    page_details: List[PageAnalysis] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.now)
    profile_version: str = "1.0"
    
    @field_validator('min_chars_per_page')
    def min_less_than_max(cls, v, info):
        if 'max_chars_per_page' in info.data and v > info.data['max_chars_per_page']:
            raise ValueError(f'min_chars_per_page ({v}) cannot be greater than max_chars_per_page ({info.data["max_chars_per_page"]})')
        return v
    
    @field_validator('avg_chars_per_page')
    def avg_between_min_and_max(cls, v, info):
        if 'min_chars_per_page' in info.data and 'max_chars_per_page' in info.data:
            if v < info.data['min_chars_per_page'] or v > info.data['max_chars_per_page']:
                raise ValueError(f'avg_chars_per_page ({v}) must be between min ({info.data["min_chars_per_page"]}) and max ({info.data["max_chars_per_page"]})')
        return v
    
    @model_validator(mode='after')
    def validate_confidence_consistency(self):
        """Ensure confidence levels match the numeric values"""
        avg_conf = (self.origin_confidence + self.layout_confidence + self.domain_confidence) / 3
        if self.profile_confidence == ConfidenceLevel.HIGH and avg_conf < 0.9:
            raise ValueError(f'Profile confidence is HIGH but average confidence ({avg_conf}) is < 0.9')
        if self.profile_confidence == ConfidenceLevel.MEDIUM and (avg_conf < 0.7 or avg_conf >= 0.9):
            raise ValueError(f'Profile confidence is MEDIUM but average confidence ({avg_conf}) is not between 0.7 and 0.9')
        if self.profile_confidence == ConfidenceLevel.LOW and avg_conf >= 0.7:
            raise ValueError(f'Profile confidence is LOW but average confidence ({avg_conf}) is >= 0.7')
        return self

    def save(self, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{self.doc_id}.json"
        output_path.write_text(self.model_dump_json(indent=2))
        return output_path


class TextBlock(BaseModel):
    """A block of text with spatial information"""
    text: str = Field(min_length=1)
    bbox: BBox
    block_type: str = "text"
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    
    @field_validator('text')
    def text_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Text block cannot be empty')
        return v.strip()
    
    @field_validator('block_type')
    def validate_block_type(cls, v):
        valid_types = ['text', 'title', 'heading', 'paragraph', 'list', 'caption', 'footer', 'header']
        if v not in valid_types:
            raise ValueError(f'block_type must be one of {valid_types}, got {v}')
        return v


class Table(BaseModel):
    """Extracted table structure"""
    headers: List[str]
    rows: List[List[str]]
    bbox: BBox
    caption: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    
    @model_validator(mode='after')
    def validate_rows_match_headers(self):
        if self.headers and self.rows:
            expected_cols = len(self.headers)
            for i, row in enumerate(self.rows):
                if len(row) != expected_cols:
                    raise ValueError(f'Row {i} has {len(row)} columns, expected {expected_cols}')
        return self
    
    @field_validator('headers')
    def headers_not_empty(cls, v):
        if not v:
            raise ValueError('Table headers cannot be empty')
        return v


class Figure(BaseModel):
    """Extracted figure with caption"""
    caption: Optional[str] = None
    bbox: BBox
    image_path: Optional[Path] = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    
    @field_validator('image_path')
    def validate_image_path(cls, v):
        if v is not None and not v.exists():
            raise ValueError(f'Image path does not exist: {v}')
        return v


class ExtractedDocument(BaseModel):
    """Normalized extraction result from any strategy"""
    doc_id: str
    filename: str
    total_pages: int = Field(gt=0)
    text_blocks: List[TextBlock] = Field(default_factory=list)
    tables: List[Table] = Field(default_factory=list)
    figures: List[Figure] = Field(default_factory=list)
    extraction_strategy: StrategyType
    confidence_score: float = Field(ge=0.0, le=1.0)
    confidence_breakdown: Dict[str, float] = Field(default_factory=dict)
    processing_time_sec: float = Field(ge=0)
    cost_usd: float = Field(ge=0)
    extraction_errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    
    @model_validator(mode='after')
    def validate_consistency(self):
        """Ensure at least one of text_blocks, tables, or figures is present"""
        if not self.text_blocks and not self.tables and not self.figures and not self.extraction_errors:
            raise ValueError('ExtractedDocument must have at least one text block, table, figure, or error')
        return self
    
    def to_json(self) -> str:
        return self.model_dump_json(indent=2)


class LDU(BaseModel):
    """Logical Document Unit - semantic chunk"""
    ldu_id: str
    content: str = Field(min_length=1)
    chunk_type: ChunkType
    page_refs: List[int] = Field(min_length=1)
    bbox: Optional[BBox] = None
    parent_section: Optional[str] = None
    token_count: int = Field(gt=0)
    content_hash: str = Field(min_length=16, max_length=64)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @field_validator('content_hash')
    def validate_hash(cls, v, info):
        """Ensure content_hash matches content"""
        if 'content' in info.data:
            expected = hashlib.sha256(info.data['content'].encode()).hexdigest()[:16]
            if v != expected:
                raise ValueError(f'Content hash {v} does not match content (expected {expected})')
        return v
    
    @field_validator('page_refs')
    def validate_page_refs(cls, v):
        if not v:
            raise ValueError('page_refs cannot be empty')
        for page in v:
            if page <= 0:
                raise ValueError(f'page_refs must be positive, got {page}')
        return sorted(v)
    
    @model_validator(mode='after')
    def validate_token_count(self):
        """Ensure token_count is reasonable for content"""
        approx_tokens = len(self.content.split())
        if abs(self.token_count - approx_tokens) > 10:
            raise ValueError(f'token_count ({self.token_count}) is far from estimated tokens ({approx_tokens})')
        return self


class PageIndexNode(BaseModel):
    """Node in PageIndex navigation tree - RECURSIVE"""
    id: str
    title: str = Field(min_length=1)
    page_start: int = Field(gt=0)
    page_end: int = Field(gt=0)
    child_sections: List["PageIndexNode"] = Field(default_factory=list)
    key_entities: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    data_types_present: List[str] = Field(default_factory=list)
    
    @field_validator('page_end')
    def page_end_must_be_greater_than_page_start(cls, v, info):
        if 'page_start' in info.data and v < info.data['page_start']:
            raise ValueError(f'page_end ({v}) must be >= page_start ({info.data["page_start"]})')
        return v
    
    @model_validator(mode='after')
    def validate_child_pages(self):
        """Ensure child sections are within parent's page range"""
        for child in self.child_sections:
            if child.page_start < self.page_start or child.page_end > self.page_end:
                raise ValueError(f'Child section "{child.title}" pages ({child.page_start}-{child.page_end}) outside parent range ({self.page_start}-{self.page_end})')
        return self


# Forward reference for recursive model
PageIndexNode.model_rebuild()


class PageIndex(BaseModel):
    """Complete navigation tree for document"""
    doc_id: str
    filename: str
    root_sections: List[PageIndexNode] = Field(default_factory=list)
    total_pages: int = Field(gt=0)
    created_at: datetime = Field(default_factory=datetime.now)
    
    @model_validator(mode='after')
    def validate_pages_in_range(self):
        """Ensure all sections are within total_pages"""
        def check_node(node: PageIndexNode):
            if node.page_end > self.total_pages:
                raise ValueError(f'Section "{node.title}" ends at page {node.page_end}, but document has only {self.total_pages} pages')
            for child in node.child_sections:
                check_node(child)
        
        for section in self.root_sections:
            check_node(section)
        return self


class Source(BaseModel):
    """Source citation for provenance"""
    document_name: str
    page_number: int = Field(gt=0)
    bbox: BBox
    content_hash: str = Field(min_length=16, max_length=64)
    
    @field_validator('content_hash')
    def validate_hash_format(cls, v):
        if len(v) != 16:
            raise ValueError(f'content_hash must be 16 characters, got {len(v)}')
        # Check if it's a valid hex string
        try:
            int(v, 16)
        except ValueError:
            raise ValueError(f'content_hash must be hexadecimal, got {v}')
        return v


class ProvenanceChain(BaseModel):
    """Complete provenance for an answer"""
    claim: str
    sources: List[Source] = Field(min_length=1)
    verified: bool = False
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    
    @model_validator(mode='after')
    def validate_verified_matches_confidence(self):
        if self.verified and self.confidence < 0.9:
            raise ValueError(f'Verified claim has low confidence: {self.confidence}')
        return self


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