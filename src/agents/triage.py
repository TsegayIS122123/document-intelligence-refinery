"""
Triage Agent - The brain of document classification.
This implements all your Phase 0 discoveries.
"""

import hashlib
from pathlib import Path
from typing import Optional

from ..models.document import DocumentProfile, PageAnalysis
from ..models.enums import (
    OriginType, LayoutComplexity, DomainHint,
    StrategyType, ConfidenceLevel
)
from ..utils.pdf_analyzer import PDFAnalyzer
from ..utils.layout import LayoutAnalyzer
from ..utils.domain import DomainClassifier
from ..utils.strategy import StrategyRecommender
from ..config.settings import settings


class TriageAgent:
    """
    Triage Agent: Analyzes documents and creates comprehensive profiles.
    Uses your Phase 0 discoveries to make intelligent decisions.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config = settings.load_rules(config_path)
        self.pdf_analyzer = PDFAnalyzer(sample_pages=self.config.get('sampling', {}).get('initial_analysis_pages', 5))
        self.layout_analyzer = LayoutAnalyzer()
        self.domain_classifier = DomainClassifier()
        self.strategy_recommender = StrategyRecommender()
        
    def generate_doc_id(self, filepath: Path) -> str:
        """Generate unique document ID"""
        # Use filename + size + modification time
        stats = filepath.stat()
        unique_str = f"{filepath.name}_{stats.st_size}_{stats.st_mtime}"
        return hashlib.sha256(unique_str.encode()).hexdigest()[:16]
    
    def analyze(self, pdf_path: str) -> DocumentProfile:
        """
        Main entry point: Analyze document and create profile.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"Document not found: {pdf_path}")
        
        # Generate ID
        doc_id = self.generate_doc_id(pdf_path)
        
        # Run analysis
        signals, page_details = self.pdf_analyzer.analyze(pdf_path)
        
        # Classify origin type (your 50/100 rule!)
        origin_type_str, origin_conf, origin_signals = self.pdf_analyzer.classify_origin(signals)
        origin_type = OriginType(origin_type_str)
        
        # Analyze layout
        layout_type, layout_conf, layout_signals = self.layout_analyzer.analyze(
            page_details, signals
        )
        
        # Extract text sample for domain classification
        text_sample = " ".join([
            f"Page {p.page_number}: {p.char_count} chars" 
            for p in page_details[:3]
        ])
        
        # Classify domain - pass filename for scanned docs!
        domain_type, domain_conf, domain_signals = self.domain_classifier.classify(
            text_sample, 
            filename=pdf_path.name  # ← Add this!
        )
        
        # Recommend strategy
        strategy, reason, cost, time = self.strategy_recommender.recommend(
            origin_type=origin_type,
            layout=layout_type,
            has_tables=signals.get('has_tables', False),
            total_pages=signals['total_pages']
        )
        
        # Determine overall confidence level
        avg_confidence = (origin_conf + layout_conf + domain_conf) / 3
        if avg_confidence >= 0.9:
            profile_confidence = ConfidenceLevel.HIGH
        elif avg_confidence >= 0.7:
            profile_confidence = ConfidenceLevel.MEDIUM
        else:
            profile_confidence = ConfidenceLevel.LOW
        
        # Create profile
        profile = DocumentProfile(
            doc_id=doc_id,
            filename=pdf_path.name,
            file_path=str(pdf_path),
            file_size_mb=pdf_path.stat().st_size / (1024 * 1024),
            total_pages=signals['total_pages'],
            analyzed_pages=signals['analyzed_pages'],
            
            origin_type=origin_type,
            origin_confidence=origin_conf,
            origin_signals=origin_signals,
            
            avg_chars_per_page=signals['avg_chars_per_page'],
            min_chars_per_page=signals['min_chars_per_page'],
            max_chars_per_page=signals['max_chars_per_page'],
            chars_std_dev=signals.get('chars_std_dev'),
            
            avg_image_ratio=signals['avg_image_ratio'],
            pages_with_images=signals['pages_with_images'],
            total_images=signals['total_images'],
            
            layout_complexity=layout_type,
            layout_confidence=layout_conf,
            has_tables=signals.get('has_tables', False),
            has_multi_column=signals.get('has_multi_column', False),
            has_figures=signals['total_images'] > 0,
            
            domain_hint=domain_type,
            domain_confidence=domain_conf,
            domain_keywords_found=domain_signals,
            
            language='en',
            language_confidence=0.9,
            
            recommended_strategy=strategy,
            recommendation_reason=reason,
            
            estimated_cost_usd=cost,
            processing_time_estimate_sec=int(time),
            
            profile_confidence=profile_confidence,
            
            page_details=page_details
        )
        
        return profile
    
    def save_profile(self, profile: DocumentProfile, output_dir: str = ".refinery/profiles"):
        """Save profile to JSON"""
        output_path = profile.save(Path(output_dir))
        return output_path
    
    def print_summary(self, profile: DocumentProfile):
        """Print human-readable summary"""
        print("\n" + "="*80)
        print(f"📋 DOCUMENT PROFILE: {profile.filename}")
        print("="*80)
        print(f"Document ID: {profile.doc_id}")
        print(f"Pages: {profile.total_pages} (analyzed {profile.analyzed_pages})")
        print(f"Size: {profile.file_size_mb:.2f} MB")
        print()
        
        print("🔍 ORIGIN CLASSIFICATION:")
        print(f"  Type: {profile.origin_type.value.upper()}")
        print(f"  Confidence: {profile.origin_confidence:.1%}")
        print(f"  Avg Characters/Page: {profile.avg_chars_per_page:.1f}")
        print(f"  Avg Image Ratio: {profile.avg_image_ratio:.3f}")
        print()
        
        print("📐 LAYOUT ANALYSIS:")
        print(f"  Complexity: {profile.layout_complexity.value}")
        print(f"  Confidence: {profile.layout_confidence:.1%}")
        print(f"  Has Tables: {'✅' if profile.has_tables else '❌'}")
        print(f"  Multi-column: {'✅' if profile.has_multi_column else '❌'}")
        print()
        
        print("🏷️ DOMAIN:")
        print(f"  Hint: {profile.domain_hint.value}")
        print(f"  Confidence: {profile.domain_confidence:.1%}")
        print()
        
        print("🎯 RECOMMENDATION:")
        print(f"  Strategy: {profile.recommended_strategy.value}")
        print(f"  Reason: {profile.recommendation_reason}")
        print(f"  Estimated Cost: ${profile.estimated_cost_usd:.4f}")
        print(f"  Est. Processing Time: {profile.processing_time_estimate_sec} seconds")
        print()
        
        print(f"Overall Confidence: {profile.profile_confidence.value.upper()}")
        print("="*80)