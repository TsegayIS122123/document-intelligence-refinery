"""
Extraction models for normalized output from all strategies.
This is your unified schema - all strategies must output this!
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
from .enums import StrategyType


class TextBlock(BaseModel):
    """A block of text with spatial information"""
    text: str
    bbox: Tuple[float, float, float, float]  # x1, y1, x2, y2
    page_num: int
    block_type: str = "text"  # title, paragraph, list, etc.
    confidence: float = 1.0


class TableCell(BaseModel):
    """A single cell in a table"""
    text: str
    row_idx: int
    col_idx: int
    is_header: bool = False
    bbox: Optional[Tuple[float, float, float, float]] = None


class Table(BaseModel):
    """Extracted table structure"""
    headers: List[str]
    rows: List[List[str]]
    cells: List[TableCell] = Field(default_factory=list)
    bbox: Tuple[float, float, float, float]
    page_num: int
    caption: Optional[str] = None
    confidence: float = 1.0


class Figure(BaseModel):
    """Extracted figure with caption"""
    caption: Optional[str]
    bbox: Tuple[float, float, float, float]
    page_num: int
    image_path: Optional[str] = None
    confidence: float = 1.0


class ExtractedDocument(BaseModel):
    """
    Normalized extraction result from ANY strategy.
    This is what Strategy A, B, and C must output!
    """
    doc_id: str
    filename: str
    total_pages: int
    
    # Extracted content
    text_blocks: List[TextBlock] = Field(default_factory=list)
    tables: List[Table] = Field(default_factory=list)
    figures: List[Figure] = Field(default_factory=list)
    
    # Metadata
    extraction_strategy: StrategyType
    confidence_score: float
    confidence_breakdown: Dict[str, float] = Field(default_factory=dict)
    processing_time_sec: float
    cost_usd: float
    
    # For provenance
    extraction_errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    
    created_at: datetime = Field(default_factory=datetime.now)
    
    def to_json(self) -> str:
        """Export to JSON"""
        return self.model_dump_json(indent=2)
    
    @property
    def has_tables(self) -> bool:
        return len(self.tables) > 0
    
    @property
    def has_figures(self) -> bool:
        return len(self.figures) > 0
    
    @property
    def total_text_length(self) -> int:
        return sum(len(tb.text) for tb in self.text_blocks)