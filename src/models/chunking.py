"""
Chunking models for semantic chunking engine.
Defines LDU (Logical Document Unit) with validation.
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from enum import Enum
import hashlib

from ..utils.hashing import SpatialHasher


class ChunkType(str, Enum):
    """Types of logical document units"""
    TEXT = "text"
    TABLE = "table"
    FIGURE = "figure"
    LIST = "list"
    SECTION_HEADER = "section_header"
    FOOTNOTE = "footnote"
    CAPTION = "caption"
    FORMULA = "formula"
    CODE = "code"


class ChunkRelationship(str, Enum):
    """Relationships between chunks"""
    PARENT_CHILD = "parent_child"
    SIBLING = "sibling"
    CROSS_REFERENCE = "cross_reference"
    CONTINUATION = "continuation"


class LDU(BaseModel):
    """
    Logical Document Unit - semantic chunk with full provenance.
    This is the core unit for RAG retrieval.
    """
    
    # Core identifiers
    ldu_id: str = Field(..., min_length=8, max_length=32)
    doc_id: str = Field(..., min_length=8, max_length=32)
    chunk_type: ChunkType
    
    # Content
    content: str = Field(..., min_length=1)
    content_hash: str = Field(..., min_length=16, max_length=16)
    
    # Spatial provenance (from Week 1 pattern!)
    page_refs: List[int] = Field(..., min_length=1)
    primary_page: int = Field(..., gt=0)
    bbox: Optional[Tuple[float, float, float, float]] = None
    
    # Structural context
    section_path: List[str] = Field(default_factory=list)  # Hierarchical path
    parent_section: Optional[str] = None
    section_depth: int = Field(default=0, ge=0)
    
    # Relationships
    child_chunks: List[str] = Field(default_factory=list)  # IDs of child chunks
    parent_chunk: Optional[str] = None
    next_chunk: Optional[str] = None  # For reading order
    prev_chunk: Optional[str] = None
    cross_references: List[str] = Field(default_factory=list)  # IDs of referenced chunks
    
    # Metadata
    token_count: int = Field(..., gt=0)
    embedding_id: Optional[str] = None  # ID in vector store
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    version: str = "1.0"
    
    @field_validator('content_hash')
    def validate_content_hash(cls, v, info):
        """Ensure content_hash matches content (spatial hashing)"""
        if 'content' in info.data and 'page_refs' in info.data and 'bbox' in info.data:
            content = info.data['content']
            page = info.data['page_refs'][0] if info.data['page_refs'] else 1
            bbox = info.data.get('bbox')
            context = info.data.get('parent_section')
            
            expected = SpatialHasher.generate_content_hash(
                text=content,
                page_num=page,
                bbox=bbox,
                context=context
            )
            if v != expected:
                raise ValueError(
                    f"Content hash {v} does not match content (expected {expected})"
                )
        return v
    
    @field_validator('token_count')
    def validate_token_count(cls, v, info):
        """Ensure token count is reasonable"""
        if 'content' in info.data:
            content = info.data['content']
            # Rough estimate: ~1.3 tokens per word
            estimated = int(len(content.split()) * 1.3)
            if abs(v - estimated) > 50:
                raise ValueError(
                    f"Token count {v} far from estimated {estimated}"
                )
        return v
    
    @model_validator(mode='after')
    def validate_page_refs(self):
        """Validate page references"""
        if not self.page_refs:
            raise ValueError("LDU must have at least one page reference")
        
        # Ensure primary_page is in page_refs
        if self.primary_page not in self.page_refs:
            raise ValueError(
                f"Primary page {self.primary_page} not in page_refs {self.page_refs}"
            )
        
        # Sort page_refs
        self.page_refs = sorted(self.page_refs)
        
        return self
    
    @model_validator(mode='after')
    def validate_section_depth(self):
        """Validate section depth matches section_path"""
        if self.section_path and len(self.section_path) != self.section_depth:
            raise ValueError(
                f"Section depth {self.section_depth} doesn't match path length {len(self.section_path)}"
            )
        return self
    
    @property
    def spatial_signature(self) -> str:
        """Get spatial signature for provenance"""
        if self.bbox:
            return f"p{self.primary_page}_r{self.bbox[0]}_{self.bbox[1]}_{self.bbox[2]}_{self.bbox[3]}"
        return f"p{self.primary_page}"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return self.model_dump()
    
    @classmethod
    def from_dict(cls, data: dict) -> "LDU":
        """Create from dictionary"""
        return cls(**data)


class ChunkRelation(BaseModel):
    """Represents a relationship between chunks"""
    source_id: str
    target_id: str
    relationship_type: ChunkRelationship
    strength: float = Field(1.0, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChunkGroup(BaseModel):
    """
    A group of related chunks (e.g., a table with its caption)
    """
    group_id: str
    group_type: str  # 'table_group', 'figure_group', 'section'
    chunks: List[str]  # LDU IDs
    primary_chunk: str  # Main chunk ID
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChunkingResult(BaseModel):
    """Result of chunking operation"""
    doc_id: str
    filename: str
    chunks: List[LDU]
    groups: List[ChunkGroup] = Field(default_factory=list)
    relations: List[ChunkRelation] = Field(default_factory=list)
    rule_violations: List[str] = Field(default_factory=list)
    stats: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)