"""
Layout complexity detection using heuristics.
This identifies multi-column, tables, figures from your analysis.
"""

from typing import List, Dict, Any, Tuple
from ..models.enums import LayoutComplexity


class LayoutAnalyzer:
    """
    Analyzes document layout complexity.
    Uses heuristics from your Phase 0 observations.
    """
    
    def __init__(self):
        self.thresholds = {
            'multi_column_min_clusters': 2,  # From your analysis
            'table_min_vertical_lines': 2,
            'table_min_horizontal_lines': 2,
            'figure_min_size': 0.1,  # 10% of page
        }
    
    def analyze(self, page_details: List, signals: Dict) -> Tuple[LayoutComplexity, float, Dict]:
        """
        Determine layout complexity from page analysis.
        
        Returns:
            complexity: LayoutComplexity enum
            confidence: float 0-1
            signals: dict with reasoning
        """
        has_tables = signals.get('has_tables', False)
        has_multi_column = signals.get('has_multi_column', False)
        
        # Count figures from page details
        figure_count = sum(p.image_count for p in page_details)
        has_figures = figure_count > 0
        
        layout_signals = {
            'has_tables': has_tables,
            'has_multi_column': has_multi_column,
            'has_figures': has_figures,
            'figure_count': figure_count,
            'tables_found': signals.get('total_tables', 0)
        }
        
        # Decision logic based on your observations
        if has_tables and has_multi_column:
            # Class C: Both tables and multi-column → MIXED
            return LayoutComplexity.MIXED, 0.85, layout_signals
        
        elif has_tables:
            # Table-heavy document
            return LayoutComplexity.TABLE_HEAVY, 0.80, layout_signals
        
        elif has_multi_column:
            # Multi-column document
            return LayoutComplexity.MULTI_COLUMN, 0.75, layout_signals
        
        elif has_figures:
            # Figure-heavy document
            return LayoutComplexity.FIGURE_HEAVY, 0.70, layout_signals
        
        else:
            # Simple single column
            return LayoutComplexity.SINGLE_COLUMN, 0.60, layout_signals