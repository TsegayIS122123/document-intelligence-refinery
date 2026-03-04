# src/utils/domain.py
"""
Domain classification using keywords from config.
Now fully externalized - no hardcoded keywords!
"""

from typing import Dict, List, Tuple, Optional
from pathlib import Path
import fnmatch
import yaml

from ..models.enums import DomainHint
from ..config.settings import settings


class DomainClassifier:
    """
    Classifies document domain based on keywords from config.
    All keywords are externalized - edit YAML, not code!
    For scanned docs, uses filename hints from config.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self.config = settings.load_rules(config_path)
        self.keywords = self._load_keywords_from_config()
        self.filename_hints = self._load_filename_hints()
        self.weights = self._load_weights()

    def _load_keywords_from_config(self) -> Dict[DomainHint, List[str]]:
        """Load domain keywords from config file"""
        domain_config = self.config.get('domain_classification', {})
        keywords = {}
        
        for domain_name, domain_data in domain_config.items():
            # Skip non-domain sections (like 'filename_hints')
            if domain_name == 'filename_hints':
                continue
                
            try:
                domain_enum = DomainHint(domain_name)
                keywords[domain_enum] = domain_data.get('keywords', [])
            except ValueError:
                # Skip if not a valid enum
                print(f"⚠️ Warning: Unknown domain '{domain_name}' in config")
                continue
        
        return keywords
    
    def _load_filename_hints(self) -> List[Dict]:
        """Load filename hints from config"""
        return self.config.get('filename_hints', [])
    
    def _load_weights(self) -> Dict[DomainHint, float]:
        """Load domain weights from config"""
        domain_config = self.config.get('domain_classification', {})
        weights = {}
        
        for domain_name, domain_data in domain_config.items():
            if domain_name == 'filename_hints':
                continue
                
            try:
                domain_enum = DomainHint(domain_name)
                weights[domain_enum] = domain_data.get('weight', 1.0)
            except ValueError:
                continue
        
        return weights

    def classify(self, text_sample: str, filename: str = "") -> Tuple[DomainHint, float, Dict]:
        """
        Classify domain based on config keywords and filename hints.
        
        Args:
            text_sample: Sample text from document (may be empty for scanned docs)
            filename: Filename for fallback hints
            
        Returns:
            domain: DomainHint enum
            confidence: float 0-1
            signals: dict with match counts and reasoning
        """
        text_lower = text_sample.lower()
        signals = {}
        scores = {}

        # Check text content using keywords from config
        for domain, keywords in self.keywords.items():
            matches = sum(1 for kw in keywords if kw in text_lower)
            weight = self.weights.get(domain, 1.0)
            weighted_score = matches * weight
            signals[domain.value] = weighted_score
            scores[domain] = weighted_score

        # If no text matches and we have filename, use filename hints from config
        total_text_score = sum(scores.values())
        if total_text_score == 0 and filename and self.filename_hints:
            filename_lower = filename.lower()
            for hint in self.filename_hints:
                pattern = hint.get('pattern', '')
                if pattern and fnmatch.fnmatch(filename_lower, pattern.lower()):
                    domain_name = hint.get('domain')
                    hint_confidence = hint.get('confidence', 0.7)
                    try:
                        domain = DomainHint(domain_name)
                        scores[domain] = scores.get(domain, 0) + 10  # High weight for filename match
                        signals[f'filename_hint_{pattern}'] = hint_confidence
                    except ValueError:
                        print(f"⚠️ Warning: Unknown domain '{domain_name}' in filename hint")
                        continue

        # Find best match
        if scores:
            best_domain = max(scores, key=scores.get)
            max_score = scores[best_domain]

            # Calculate confidence based on match strength
            if max_score >= 10:
                confidence = 0.95  # Filename match or many keywords
            elif max_score >= 5:
                confidence = 0.80  # Strong keyword match
            elif max_score >= 1:
                confidence = 0.60  # Weak keyword match
            else:
                confidence = 0.50  # No matches

            if max_score == 0:
                return DomainHint.GENERAL, 0.5, signals

            return best_domain, confidence, signals

        return DomainHint.GENERAL, 0.5, signals

    def get_supported_domains(self) -> List[DomainHint]:
        """Return list of domains supported in config"""
        return list(self.keywords.keys())