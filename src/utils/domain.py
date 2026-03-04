# src/utils/domain.py
from typing import Dict, List, Tuple
from ..models.enums import DomainHint
import re

class DomainClassifier:
    """
    Classifies document domain based on keyword matching.
    For scanned docs, uses filename as hint.
    """
    
    def __init__(self):
        # Keywords from your document analysis
        self.keywords = {
            DomainHint.FINANCIAL: [
                'revenue', 'expense', 'profit', 'loss', 'income',
                'balance sheet', 'financial', 'fiscal', 'tax',
                'expenditure', 'budget', 'asset', 'liability',
                'cbe', 'bank', 'interest', 'loan', 'deposit'
            ],
            DomainHint.LEGAL: [
                'audit', 'auditor', 'opinion', 'statement',
                'compliance', 'regulation', 'legal', 'law',
                'independent', 'report', 'findings', 'attest',
                'assurance', 'examination', 'review'
            ],
            DomainHint.TECHNICAL: [
                'assessment', 'performance', 'implementation',
                'analysis', 'evaluation', 'survey', 'report',
                'findings', 'recommendations', 'methodology'
            ],
            DomainHint.MEDICAL: [
                'patient', 'clinical', 'diagnosis', 'treatment',
                'health', 'medical', 'hospital', 'doctor'
            ]
        }
        
        # Filename-based hints for scanned docs
        self.filename_hints = {
            'audit': DomainHint.LEGAL,
            'auditor': DomainHint.LEGAL,
            'legal': DomainHint.LEGAL,
            'financial': DomainHint.FINANCIAL,
            'cbe': DomainHint.FINANCIAL,
            'tax': DomainHint.FINANCIAL,
            'fta': DomainHint.TECHNICAL,
            'technical': DomainHint.TECHNICAL,
        }
    
    def classify(self, text_sample: str, filename: str = "") -> Tuple[DomainHint, float, Dict]:
        """
        Classify domain based on keyword matches and filename.
        """
        text_lower = text_sample.lower()
        signals = {}
        scores = {}
        
        # Check text content first
        for domain, keywords in self.keywords.items():
            matches = sum(1 for kw in keywords if kw in text_lower)
            signals[domain.value] = matches
            scores[domain] = matches
        
        # If no text matches and we have filename, use filename hints
        if sum(scores.values()) == 0 and filename:
            filename_lower = filename.lower()
            for hint_word, hint_domain in self.filename_hints.items():
                if hint_word in filename_lower:
                    scores[hint_domain] = scores.get(hint_domain, 0) + 5
                    signals[f'filename_hint_{hint_word}'] = 5
        
        # Find best match
        if scores:
            best_domain = max(scores, key=scores.get)
            max_score = scores[best_domain]
            
            # Calculate confidence
            if max_score >= 10:
                confidence = 0.95
            elif max_score >= 5:
                confidence = 0.80
            elif max_score >= 1:
                confidence = 0.60
            else:
                confidence = 0.50
            
            if max_score == 0:
                return DomainHint.GENERAL, 0.5, signals
            
            return best_domain, confidence, signals
        
        return DomainHint.GENERAL, 0.5, signals