"""
Strategy B: Layout-Aware Extraction using Docling.
For complex documents with multi-column layout, tables, and figures.
Includes adapter pattern to normalize Docling output to your schema.
"""

import time
from pathlib import Path
from typing import Optional, List
from .base import BaseExtractor
from ..models.extraction import ExtractedDocument, TextBlock, Table, TableCell, Figure
from ..models.document import DocumentProfile
from ..models.enums import StrategyType

# Try to import Docling, but handle gracefully if not installed
try:
    from docling.document_converter import DocumentConverter
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False
    print("⚠️ Docling not installed. Strategy B will use fallback.")


class DoclingAdapter:
    """
    Adapter pattern: Converts Docling's native output to your ExtractedDocument schema.
    This is the key to making all strategies output the SAME format.
    """
    
    def __init__(self):
        self.converter = None
        if DOCLING_AVAILABLE:
            try:
                # Configure Docling pipeline
                pipeline_options = PdfPipelineOptions()
                pipeline_options.do_ocr = True
                pipeline_options.do_table_structure = True
                
                self.converter = DocumentConverter()
            except Exception as e:
                print(f"⚠️ Docling initialization error: {e}")
    
    def convert(self, docling_doc) -> ExtractedDocument:
        """
        Convert Docling document to your ExtractedDocument schema.
        This preserves all bounding boxes and structure!
        """
        text_blocks = []
        tables = []
        figures = []
        
        # Extract text blocks with bounding boxes
        if hasattr(docling_doc, 'texts'):
            for text_item in docling_doc.texts:
                if hasattr(text_item, 'text') and text_item.text:
                    bbox = (0, 0, 0, 0)  # Default
                    if hasattr(text_item, 'bbox'):
                        bbox = (
                            text_item.bbox.l,
                            text_item.bbox.t,
                            text_item.bbox.r,
                            text_item.bbox.b
                        )
                    
                    text_blocks.append(TextBlock(
                        text=text_item.text[:1000],  # Limit for demo
                        bbox=bbox,
                        page_num=getattr(text_item, 'page_num', 1),
                        block_type=getattr(text_item, 'type', 'text'),
                        confidence=0.95  # Docling is confident!
                    ))
        
        # Extract tables with structure
        if hasattr(docling_doc, 'tables'):
            for table_item in docling_doc.tables:
                if hasattr(table_item, 'data') and table_item.data:
                    # Convert to your Table format
                    headers = []
                    rows = []
                    
                    # Extract headers (first row)
                    if table_item.data and len(table_item.data) > 0:
                        headers = [str(cell) for cell in table_item.data[0]]
                        
                        # Extract data rows
                        for row_idx, row in enumerate(table_item.data[1:], 1):
                            row_data = [str(cell) for cell in row]
                            rows.append(row_data)
                            
                            # Create individual cells for provenance
                            for col_idx, cell_text in enumerate(row):
                                if hasattr(table_item, 'get_cell_bbox'):
                                    cell_bbox = table_item.get_cell_bbox(row_idx, col_idx)
                                else:
                                    cell_bbox = (0, 0, 0, 0)
                    
                    bbox = (0, 0, 0, 0)
                    if hasattr(table_item, 'bbox'):
                        bbox = (
                            table_item.bbox.l,
                            table_item.bbox.t,
                            table_item.bbox.r,
                            table_item.bbox.b
                        )
                    
                    tables.append(Table(
                        headers=headers,
                        rows=rows,
                        bbox=bbox,
                        page_num=getattr(table_item, 'page_num', 1),
                        caption=getattr(table_item, 'caption', None),
                        confidence=0.95
                    ))
        
        # Extract figures
        if hasattr(docling_doc, 'pictures'):
            for pic in docling_doc.pictures:
                bbox = (0, 0, 0, 0)
                if hasattr(pic, 'bbox'):
                    bbox = (
                        pic.bbox.l,
                        pic.bbox.t,
                        pic.bbox.r,
                        pic.bbox.b
                    )
                
                # Try to find caption
                caption = None
                if hasattr(pic, 'caption') and pic.caption:
                    caption = pic.caption
                elif hasattr(pic, 'get_caption'):
                    caption = pic.get_caption()
                
                figures.append(Figure(
                    caption=caption,
                    bbox=bbox,
                    page_num=getattr(pic, 'page_num', 1),
                    confidence=0.95
                ))
        
        # Create extracted document
        return ExtractedDocument(
            doc_id="temp",  # Will be set by caller
            filename="temp",
            total_pages=len(docling_doc.pages) if hasattr(docling_doc, 'pages') else 0,
            text_blocks=text_blocks,
            tables=tables,
            figures=figures,
            extraction_strategy=StrategyType.LAYOUT_AWARE,
            confidence_score=0.95,
            processing_time_sec=0,
            cost_usd=0
        )


class LayoutExtractor(BaseExtractor):
    """
    Strategy B: Layout-aware extraction using Docling.
    Cost: $0.01 per page
    Best for: Multi-column documents, tables, figures
    """
    
    def __init__(self):
        super().__init__()
        self.name = "LayoutExtractor"
        self.cost_per_page = 0.01  # $0.01 per page
        self.adapter = DoclingAdapter()
    
    def estimate_cost(self, pdf_path: Path) -> float:
        """Estimate cost based on page count"""
        try:
            import pypdf
            with open(pdf_path, 'rb') as f:
                pdf = pypdf.PdfReader(f)
                return len(pdf.pages) * self.cost_per_page
        except:
            return 0.10  # Default estimate
    
    def extract(self, pdf_path: Path, profile: Optional[DocumentProfile] = None) -> ExtractedDocument:
        """
        Extract using Docling, then normalize through adapter.
        """
        start_time = time.time()
        
        # Check if Docling is available
        if not DOCLING_AVAILABLE or not self.adapter.converter:
            return ExtractedDocument(
                doc_id=pdf_path.stem,
                filename=pdf_path.name,
                total_pages=0,
                extraction_strategy=StrategyType.LAYOUT_AWARE,
                confidence_score=0.0,
                processing_time_sec=time.time() - start_time,
                cost_usd=0.01,
                extraction_errors=["Docling not available - install with: pip install docling"]
            )
        
        try:
            # Limit to first 10 pages for memory (from your Phase 0 discovery!)
            result = self.adapter.converter.convert(pdf_path, max_num_pages=10)
            doc = result.document
            
            # Convert to your schema
            extracted = self.adapter.convert(doc)
            
            # Update metadata
            extracted.doc_id = profile.doc_id if profile else pdf_path.stem
            extracted.filename = pdf_path.name
            extracted.processing_time_sec = time.time() - start_time
            extracted.cost_usd = extracted.total_pages * self.cost_per_page
            
            return extracted
            
        except Exception as e:
            self.extraction_errors.append(str(e))
            return ExtractedDocument(
                doc_id=pdf_path.stem,
                filename=pdf_path.name,
                total_pages=0,
                extraction_strategy=StrategyType.LAYOUT_AWARE,
                confidence_score=0.0,
                processing_time_sec=time.time() - start_time,
                cost_usd=0.01,
                extraction_errors=[f"Docling error: {str(e)}"]
            )
    
    def confidence_score(self, extracted: ExtractedDocument) -> float:
        """Return confidence - Docling is generally confident"""
        if extracted.extraction_errors:
            return 0.3
        return 0.9  # Base confidence for successful Docling extraction