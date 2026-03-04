"""
Multi-signal confidence scoring for extraction strategies.
Uses thresholds from your Phase 0 analysis.
"""

import math


class FastTextConfidence:
    """
    Confidence calculator for FastTextExtractor.
    Uses multiple signals to determine extraction quality.
    
    Signals from Phase 0:
    - Class B (scanned): 24 chars/page → low confidence
    - Class C (digital): 3646 chars/page → high confidence
    - Class A (mixed): 947 chars + 40% images → medium confidence
    """
    
    def __init__(self):
        # Thresholds from your Phase 0 analysis!
        self.thresholds = {
            'char_count': {
                'excellent': 2000,  # Class C territory
                'good': 500,        # Above this is probably digital
                'poor': 50,         # Below this is scanned (Class B)
            },
            'char_density': {
                'excellent': 0.01,   # chars per square point
                'good': 0.001,
                'poor': 0.0001,
            },
            'image_ratio': {
                'excellent': 0.1,    # <10% images
                'good': 0.3,          # <30% images
                'poor': 0.5,           # >50% images = scanned
            }
        }
    
    def calculate(self, char_count: int, char_density: float, 
                  image_ratio: float, has_fonts: bool, 
                  table_count: int, page_area: float) -> float:
        """
        Calculate confidence score (0-1) for a single page.
        
        Returns:
            float: Confidence score where:
                0.9-1.0: Excellent - digital doc with text
                0.7-0.9: Good - readable but maybe some issues
                0.5-0.7: Medium - might need escalation
                <0.5: Poor - should escalate
        """
        
        # Signal 1: Character count (most important)
        if char_count > self.thresholds['char_count']['excellent']:
            char_score = 1.0
        elif char_count > self.thresholds['char_count']['good']:
            char_score = 0.8
        elif char_count > self.thresholds['char_count']['poor']:
            char_score = 0.5
        else:
            char_score = 0.2  # Scanned!
        
        # Signal 2: Image ratio (inverse - less images is better)
        if image_ratio < self.thresholds['image_ratio']['excellent']:
            image_score = 1.0
        elif image_ratio < self.thresholds['image_ratio']['good']:
            image_score = 0.8
        elif image_ratio < self.thresholds['image_ratio']['poor']:
            image_score = 0.5
        else:
            image_score = 0.2  # Too many images
        
        # Signal 3: Font presence (digital docs have fonts)
        font_score = 1.0 if has_fonts else 0.3
        
        # Signal 4: Tables found (bonus if tables detected correctly)
        table_score = min(1.0, 0.5 + (table_count * 0.1))
        
        # Weighted average (character count is most important)
        weights = {
            'char': 0.5,
            'image': 0.2,
            'font': 0.2,
            'table': 0.1
        }
        
        confidence = (
            char_score * weights['char'] +
            image_score * weights['image'] +
            font_score * weights['font'] +
            table_score * weights['table']
        )
        
        return round(confidence, 2)