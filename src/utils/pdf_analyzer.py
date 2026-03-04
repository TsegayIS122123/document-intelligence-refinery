"""
PDF analysis utilities for character density, image detection, etc.
This implements the core metrics you discovered in Phase 0.
"""

import pdfplumber
from pathlib import Path
from typing import List, Dict, Any, Tuple
import statistics
from ..models.document import PageAnalysis


class PDFAnalyzer:
    """
    Analyzes PDF files to extract metrics for triage.
    Uses your Phase 0 discoveries about character density thresholds.
    """
    
    def __init__(self, sample_pages: int = 5):
        self.sample_pages = sample_pages
        self.thresholds = {
            'scanned_max_chars': 50,      # From Class B: 24 chars
            'digital_min_chars': 100,     # From Class C: 3646 chars
            'scanned_min_image_ratio': 0.5,  # From Class B: 0.803
            'digital_max_image_ratio': 0.3,  # From Class C: 0.001
        }
    
    def analyze(self, pdf_path: Path) -> Tuple[Dict[str, Any], List[PageAnalysis]]:
        """
        Analyze PDF and return signals + page details.
        
        Returns:
            signals: Dictionary of aggregate metrics
            page_details: List of per-page analysis
        """
        signals = {
            'total_pages': 0,
            'analyzed_pages': 0,
            'avg_chars_per_page': 0,
            'min_chars_per_page': float('inf'),
            'max_chars_per_page': 0,
            'chars_list': [],
            'avg_image_ratio': 0,
            'pages_with_images': 0,
            'total_images': 0,
            'has_tables': False,
            'has_multi_column': False,
            'total_tables': 0,
        }
        
        page_details = []
        
        with pdfplumber.open(pdf_path) as pdf:
            signals['total_pages'] = len(pdf.pages)
            pages_to_analyze = min(self.sample_pages, len(pdf.pages))
            
            for page_num in range(pages_to_analyze):
                page = pdf.pages[page_num]
                
                # Extract text
                text = page.extract_text() or ""
                char_count = len(text)
                
                # Calculate image area
                images = page.images
                page_area = (page.width or 1) * (page.height or 1)
                image_area = sum(
                    img.get('height', 0) * img.get('width', 0) 
                    for img in images
                ) if images else 0
                image_ratio = image_area / page_area if page_area > 0 else 0
                
                # Detect tables
                tables = page.find_tables()
                if tables:
                    signals['has_tables'] = True
                    signals['total_tables'] += len(tables)
                
                # Multi-column detection heuristic
                words = page.extract_words()
                if len(words) > 10:
                    # Group words by their x-position clusters
                    x_positions = [w['x0'] for w in words if 'x0' in w]
                    if x_positions:
                        # Rough clustering - if words start in different regions
                        x_clusters = len(set(round(x/50) for x in x_positions))
                        if x_clusters > 2:
                            signals['has_multi_column'] = True
                
                # Page analysis object
                page_analysis = PageAnalysis(
                    page_number=page_num + 1,
                    char_count=char_count,
                    image_count=len(images),
                    image_ratio=round(image_ratio, 3),
                    table_count=len(tables),
                    has_text=char_count > 50,
                    likely_scanned=char_count < 50 and image_ratio > 0.5,
                    width=page.width or 0,
                    height=page.height or 0
                )
                page_details.append(page_analysis)
                
                # Update signals
                signals['chars_list'].append(char_count)
                if char_count < signals['min_chars_per_page']:
                    signals['min_chars_per_page'] = char_count
                if char_count > signals['max_chars_per_page']:
                    signals['max_chars_per_page'] = char_count
                
                signals['avg_image_ratio'] += image_ratio
                if images:
                    signals['pages_with_images'] += 1
                    signals['total_images'] += len(images)
            
            # Calculate averages
            signals['analyzed_pages'] = pages_to_analyze
            signals['avg_chars_per_page'] = sum(signals['chars_list']) / pages_to_analyze
            signals['avg_image_ratio'] /= pages_to_analyze
            
            # Calculate standard deviation if multiple pages
            if len(signals['chars_list']) > 1:
                signals['chars_std_dev'] = statistics.stdev(signals['chars_list'])
            
            # Determine if document is mixed based on variance
            if signals.get('chars_std_dev', 0) > 500:
                signals['is_mixed_confidence'] = 'high_variance'
        
        return signals, page_details
    
    def classify_origin(self, signals: Dict) -> Tuple[str, float, Dict]:
        """
        Classify document origin type using your Phase 0 thresholds.
        This is the core intelligence!
        """
        avg_chars = signals['avg_chars_per_page']
        avg_image = signals['avg_image_ratio']
        
        decision_signals = {
            'avg_chars_per_page': avg_chars,
            'avg_image_ratio': avg_image,
            'thresholds_used': self.thresholds
        }
        
        # Your 50/100 rule from Phase 0!
        if avg_chars < self.thresholds['scanned_max_chars'] and avg_image > self.thresholds['scanned_min_image_ratio']:
            # Class B: 24 chars, 0.803 ratio → SCANNED
            return 'scanned_image', 0.95, decision_signals
        
        elif avg_chars > self.thresholds['digital_min_chars'] and avg_image < self.thresholds['digital_max_image_ratio']:
            # Class C: 3646 chars, 0.001 ratio → DIGITAL
            return 'native_digital', 0.90, decision_signals
        
        elif 50 <= avg_chars <= 100:
            # Borderline case - need more analysis
            return 'mixed', 0.70, decision_signals
        
        else:
            # Class A: 947 chars but 0.4 image ratio → MIXED
            return 'mixed', 0.60, decision_signals