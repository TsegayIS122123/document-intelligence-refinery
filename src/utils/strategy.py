"""
Strategy recommendation based on document profile.
Uses your Phase 0 decision tree.
"""

from typing import Tuple
from ..models.enums import OriginType, LayoutComplexity, StrategyType
from ..config.settings import settings


class StrategyRecommender:
    """
    Recommends extraction strategy based on document profile.
    Implements the decision tree from your Phase 0 analysis.
    """
    
    def __init__(self):
        self.costs = {
            StrategyType.FAST_TEXT: 0.001,
            StrategyType.LAYOUT_AWARE: 0.01,
            StrategyType.VISION_AUGMENTED: 0.10
        }
        
        self.speeds = {
            StrategyType.FAST_TEXT: 0.5,   # seconds per page
            StrategyType.LAYOUT_AWARE: 2,
            StrategyType.VISION_AUGMENTED: 5
        }
    
    def recommend(
        self,
        origin_type: OriginType,
        layout: LayoutComplexity,
        has_tables: bool,
        total_pages: int
    ) -> Tuple[StrategyType, str, float, int]:
        """
        Recommend strategy based on document characteristics.
        
        Returns:
            strategy: StrategyType
            reason: Explanation for recommendation
            cost: Estimated cost in USD
            time: Estimated processing time in seconds
        """
        
        # Decision tree from your Mermaid diagram!
        if origin_type == OriginType.SCANNED_IMAGE:
            # Class B: Scanned needs Vision
            strategy = StrategyType.VISION_AUGMENTED
            reason = "Scanned document requires vision model for OCR"
            
        elif origin_type == OriginType.NATIVE_DIGITAL:
            if layout in [LayoutComplexity.SINGLE_COLUMN] and not has_tables:
                # Simple digital document
                strategy = StrategyType.FAST_TEXT
                reason = "Simple digital document - fast extraction sufficient"
            else:
                # Complex layout needs layout-aware
                strategy = StrategyType.LAYOUT_AWARE
                reason = f"Complex layout ({layout.value}) needs structure preservation"
                
        elif origin_type == OriginType.MIXED:
            # Mixed content needs layout-aware
            strategy = StrategyType.LAYOUT_AWARE
            reason = "Mixed content needs layout-aware extraction"
            
        else:
            # Default to layout-aware for safety
            strategy = StrategyType.LAYOUT_AWARE
            reason = "Default strategy for unknown document type"
        
        # Calculate costs
        cost = self.costs[strategy] * total_pages
        time = self.speeds[strategy] * total_pages
        
        return strategy, reason, cost, time