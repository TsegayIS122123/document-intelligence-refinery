"""
ExtractionRouter: The strategy pattern implementation that:
1. Reads DocumentProfile from Triage Agent
2. Delegates to correct strategy
3. Implements escalation guard on low confidence
4. Logs everything to extraction_ledger.jsonl
"""

import json
import time
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from ..models.document import DocumentProfile
from ..models.extraction import ExtractedDocument
from ..models.enums import StrategyType
from ..strategies.fast_text import FastTextExtractor
# from ..strategies.layout import LayoutExtractor  # TEMPORARILY DISABLED - Windows DLL issue with Docling/PyTorch
from ..strategies.vision import VisionExtractor


class ExtractionRouter:
    """
    Routes documents to appropriate extraction strategy.
    Implements the escalation guard pattern:
    Start with cheapest, escalate if confidence too low.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self.config = self._load_config(config_path)
        self.ledger_path = Path(".refinery/extraction_ledger.jsonl")
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize strategies - LayoutExtractor temporarily disabled on Windows
        self.strategies = {
            StrategyType.FAST_TEXT: FastTextExtractor(),
            StrategyType.LAYOUT_AWARE: None,  # Temporarily disabled due to Windows DLL issue
            StrategyType.VISION_AUGMENTED: VisionExtractor(
                max_cost_per_doc=self.config.get('budget', {}).get('max_cost_per_document', 20.00)  # Increased for testing
            )
        }

        # Confidence thresholds from config
        self.confidence_thresholds = self.config.get('confidence', {
            'fast_text': {'min_confidence': 0.7, 'escalate_to': 'layout_aware'},
            'layout_aware': {'min_confidence': 0.8, 'escalate_to': 'vision_augmented'},
            'vision_augmented': {'min_confidence': 0.9}
        })

    def _load_config(self, config_path: Optional[Path]) -> Dict:
        """Load configuration from extraction_rules.yaml"""
        default_config = {
            'confidence': {
                'fast_text': {'min_confidence': 0.7, 'escalate_to': 'layout_aware'},
                'layout_aware': {'min_confidence': 0.8, 'escalate_to': 'vision_augmented'},
                'vision_augmented': {'min_confidence': 0.9}
            },
            'budget': {
                'max_cost_per_document': 20.00,  # Increased from 1.00 for testing
                'warn_at_cost': 10.00
            }
        }

        if config_path and config_path.exists():
            import yaml
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)

        return default_config

    def _log_extraction(self, doc_id: str, strategy: str, confidence: float,
                        cost: float, time_sec: float, error: Optional[str] = None,
                        escalated_from: Optional[str] = None):
        """Log extraction to ledger.jsonl"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'doc_id': doc_id,
            'strategy_used': strategy,
            'confidence_score': confidence,
            'cost_estimate': cost,
            'processing_time_sec': time_sec,
            'escalated_from': escalated_from,
            'error': error
        }

        with open(self.ledger_path, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')

    def extract(self, pdf_path: Path, profile: DocumentProfile) -> ExtractedDocument:
        """
        Main extraction method with escalation guard.
        """
        # Handle disabled LayoutExtractor (Windows DLL issue)
        if profile.recommended_strategy == StrategyType.LAYOUT_AWARE:
            # print("⚠️ [Windows Compatibility] LayoutExtractor temporarily disabled (PyTorch DLL issue). Using FastTextExtractor as fallback.")
            current_strategy = StrategyType.FAST_TEXT
        else:
            current_strategy = profile.recommended_strategy

        escalated_from = None
        result = None

        # Try strategies in order, escalating as needed
        while True:
            extractor = self.strategies[current_strategy]
            
            # Skip if strategy is disabled
            if extractor is None:
                print(f"⚠️ Strategy {current_strategy.value} is disabled, trying next...")
                # Try to escalate
                escalate_to = self.confidence_thresholds[current_strategy.value].get('escalate_to')
                if escalate_to and escalate_to != current_strategy.value:
                    escalated_from = current_strategy.value
                    current_strategy = StrategyType(escalate_to)
                    continue
                else:
                    # No further options, create fallback
                    from ..models.extraction import ExtractedDocument
                    result = ExtractedDocument(
                        doc_id=profile.doc_id,
                        filename=pdf_path.name,
                        total_pages=profile.total_pages,
                        extraction_strategy=current_strategy,
                        confidence_score=0.0,
                        processing_time_sec=0,
                        cost_usd=0,
                        extraction_errors=[f"Strategy {current_strategy.value} is disabled"]
                    )
                    break

            # Check budget for vision
            if current_strategy == StrategyType.VISION_AUGMENTED:
                estimated_cost = extractor.estimate_cost(pdf_path)
                if estimated_cost > self.config.get('budget', {}).get('max_cost_per_document', 20.00):
                    error_msg = f"Budget exceeded: ${estimated_cost:.2f} > max"
                    self._log_extraction(
                        doc_id=profile.doc_id,
                        strategy=current_strategy.value,
                        confidence=0.0,
                        cost=0,
                        time_sec=0,
                        error=error_msg,
                        escalated_from=escalated_from
                    )
                    # Create a fallback document
                    from ..models.extraction import ExtractedDocument
                    result = ExtractedDocument(
                        doc_id=profile.doc_id,
                        filename=pdf_path.name,
                        total_pages=profile.total_pages,
                        extraction_strategy=current_strategy,
                        confidence_score=0.0,
                        processing_time_sec=0,
                        cost_usd=0,
                        extraction_errors=[error_msg]
                    )
                    break

            # Perform extraction
            start_time = time.time()
            try:
                result = extractor.extract(pdf_path, profile)
                if result is None:
                    # If extractor returns None, create a fallback
                    from ..models.extraction import ExtractedDocument
                    result = ExtractedDocument(
                        doc_id=profile.doc_id,
                        filename=pdf_path.name,
                        total_pages=profile.total_pages,
                        extraction_strategy=current_strategy,
                        confidence_score=0.0,
                        processing_time_sec=time.time() - start_time,
                        cost_usd=0,
                        extraction_errors=[f"{current_strategy.value} returned None"]
                    )
            except Exception as e:
                # If extractor throws exception, create a fallback
                from ..models.extraction import ExtractedDocument
                result = ExtractedDocument(
                    doc_id=profile.doc_id,
                    filename=pdf_path.name,
                    total_pages=profile.total_pages,
                    extraction_strategy=current_strategy,
                    confidence_score=0.0,
                    processing_time_sec=time.time() - start_time,
                    cost_usd=0,
                    extraction_errors=[f"Exception: {str(e)}"]
                )

            processing_time = time.time() - start_time

            # Get confidence
            confidence = result.confidence_score if result else 0.0

            # Log this attempt
            self._log_extraction(
                doc_id=profile.doc_id,
                strategy=current_strategy.value,
                confidence=confidence,
                cost=result.cost_usd if result else 0,
                time_sec=processing_time,
                escalated_from=escalated_from
            )

            # Check if we need to escalate
            threshold = self.confidence_thresholds[current_strategy.value]['min_confidence']

            if confidence >= threshold:
                # Good enough - accept
                break
            else:
                # Need to escalate
                escalate_to = self.confidence_thresholds[current_strategy.value].get('escalate_to')
                if escalate_to and escalate_to != current_strategy.value:
                    print(f"⚠️ Escalating from {current_strategy.value} to {escalate_to} (confidence {confidence:.1%} < {threshold:.0%})")
                    escalated_from = current_strategy.value
                    current_strategy = StrategyType(escalate_to)
                else:
                    # No further escalation possible
                    break

        return result

    def batch_extract(self, pdf_paths: list[Path], profiles: list[DocumentProfile]) -> list[ExtractedDocument]:
        """Extract multiple documents"""
        results = []
        for pdf_path, profile in zip(pdf_paths, profiles):
            result = self.extract(pdf_path, profile)
            results.append(result)
        return results

    def get_ledger_summary(self) -> Dict:
        """Get summary of extraction ledger"""
        if not self.ledger_path.exists():
            return {'total_extractions': 0}

        entries = []
        with open(self.ledger_path, 'r') as f:
            for line in f:
                entries.append(json.loads(line))

        summary = {
            'total_extractions': len(entries),
            'by_strategy': {},
            'avg_confidence': 0,
            'total_cost': 0
        }

        for entry in entries:
            strategy = entry['strategy_used']
            summary['by_strategy'][strategy] = summary['by_strategy'].get(strategy, 0) + 1
            summary['total_cost'] += entry['cost_estimate']

        if entries:
            summary['avg_confidence'] = sum(e['confidence_score'] for e in entries) / len(entries)

        return summary