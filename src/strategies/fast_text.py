"""
Strategy A: Fast Text Extraction using pdfplumber.
For simple digital documents with single-column layout.
Includes multi-signal confidence scoring from your Phase 0 analysis.
"""

import pdfplumber
from pathlib import Path
import time
import math
from typing import Optional, List, Dict, Any
from .base import BaseExtractor
from ..models.extraction import ExtractedDocument, TextBlock, Table, TableCell, Figure
from ..models.document import DocumentProfile
from ..utils.confidence import FastTextConfidence


class FastTextExtractor(BaseExtractor):
    """
    Strategy A: Fast text extraction using pdfplumber.
    Cost: $0.001 per page
    Best for: Simple digital documents with single-column layout
    """
    
    def __init__(self):
        super().__init__()
        self.name = "FastTextExtractor"
        self.cost_per_page = 0.001  # $0.001 per page
        self.confidence_calculator = FastTextConfidence()
    
    def estimate_cost(self, pdf_path: Path) -> float:
        """Estimate cost based on page count"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                return len(pdf.pages) * self.cost_per_page
        except:
            return 0.01  # Default if can't open
    
    def extract(self, pdf_path: Path, profile: Optional[DocumentProfile] = None) -> ExtractedDocument:
        """
        Extract text using pdfplumber with multi-signal confidence.
        
        The confidence scoring uses:
        1. Character density (chars per page area)
        2. Image ratio (if >50% page is images, confidence drops)
        3. Font consistency (presence of font metadata)
        4. Table detection success
        """
        start_time = time.time()
        
        text_blocks = []
        tables = []
        figures = []
        page_confidences = []
        confidence_signals = {
            'char_density': [],
            'image_ratio': [],
            'font_present': [],
            'table_quality': []
        }
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                
                for page_num, page in enumerate(pdf.pages):
                    # Extract text
                    text = page.extract_text() or ""
                    char_count = len(text)
                    
                    # Calculate page area
                    page_width = page.width or 1
                    page_height = page.height or 1
                    page_area = page_width * page_height
                    
                    # Character density (chars per square point)
                    char_density = char_count / page_area if page_area > 0 else 0
                    
                    # Image analysis
                    images = page.images
                    image_area = sum(
                        img.get('height', 0) * img.get('width', 0) 
                        for img in images
                    ) if images else 0
                    image_ratio = image_area / page_area if page_area > 0 else 0
                    
                    # Font metadata presence
                    has_fonts = False
                    words = page.extract_words()
                    if words and 'fontname' in words[0]:
                        has_fonts = True
                    
                    # Table detection
                    page_tables = page.find_tables()
                    table_count = len(page_tables)
                    
                    # Create text blocks
                    if text:
                        text_blocks.append(TextBlock(
                            text=text[:1000],  # Limit for demo
                            bbox=(0, 0, page_width, page_height),  # Approx
                            page_num=page_num + 1,
                            block_type="text"
                        ))
                    
                    # Extract tables
                    for table_idx, table in enumerate(page_tables):
                        try:
                            table_data = table.extract()
                            if table_data and len(table_data) > 0:
                                # First row as headers
                                headers = table_data[0] if table_data else []
                                rows = table_data[1:] if len(table_data) > 1 else []
                                
                                tables.append(Table(
                                    headers=[str(h) for h in headers if h],
                                    rows=[[str(cell) for cell in row] for row in rows],
                                    bbox=(0, 0, page_width, page_height),  # Approx
                                    page_num=page_num + 1,
                                    confidence=0.7  # Base confidence for pdfplumber tables
                                ))
                        except:
                            pass
                    
                    # Calculate page confidence using multiple signals
                    page_conf = self.confidence_calculator.calculate(
                        char_count=char_count,
                        char_density=char_density,
                        image_ratio=image_ratio,
                        has_fonts=has_fonts,
                        table_count=table_count,
                        page_area=page_area
                    )
                    
                    page_confidences.append(page_conf)
                    confidence_signals['char_density'].append(char_density)
                    confidence_signals['image_ratio'].append(image_ratio)
                    confidence_signals['font_present'].append(1 if has_fonts else 0)
                    confidence_signals['table_quality'].append(1 if table_count > 0 else 0)
            
            # Overall confidence (average of pages)
            overall_confidence = sum(page_confidences) / len(page_confidences) if page_confidences else 0.5
            
            # Confidence breakdown for debugging
            confidence_breakdown = {
                'avg_char_density': sum(confidence_signals['char_density']) / len(confidence_signals['char_density']) if confidence_signals['char_density'] else 0,
                'avg_image_ratio': sum(confidence_signals['image_ratio']) / len(confidence_signals['image_ratio']) if confidence_signals['image_ratio'] else 0,
                'pages_with_fonts': sum(confidence_signals['font_present']),
                'tables_detected': len(tables)
            }
            
            processing_time = time.time() - start_time
            cost = total_pages * self.cost_per_page
            
            # Create extracted document
            extracted = ExtractedDocument(
                doc_id=profile.doc_id if profile else pdf_path.stem,
                filename=pdf_path.name,
                total_pages=total_pages,
                text_blocks=text_blocks,
                tables=tables,
                figures=figures,
                extraction_strategy=profile.recommended_strategy if profile else "fast_text",
                confidence_score=overall_confidence,
                confidence_breakdown=confidence_breakdown,
                processing_time_sec=processing_time,
                cost_usd=cost
            )
            
            return extracted
            
        except Exception as e:
            self.extraction_errors.append(str(e))
            # Return minimal document with error info
            return ExtractedDocument(
                doc_id=pdf_path.stem,
                filename=pdf_path.name,
                total_pages=0,
                extraction_strategy="fast_text",
                confidence_score=0.0,
                processing_time_sec=time.time() - start_time,
                cost_usd=0.001,
                extraction_errors=[str(e)]
            )
    
    def confidence_score(self, extracted: ExtractedDocument) -> float:
        """Return the confidence score from extraction"""
        return extracted.confidence_score