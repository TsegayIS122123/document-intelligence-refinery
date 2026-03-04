"""
Base extractor class that all strategies must implement.
This ensures consistent interface and enables the Router to swap strategies.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any
from ..models.extraction import ExtractedDocument
from ..models.document import DocumentProfile


class BaseExtractor(ABC):
    """
    Abstract base class for all extraction strategies.
    Any new extractor must implement these methods.
    """
    
    def __init__(self):
        self.name = self.__class__.__name__
        self.extraction_errors = []
    
    @abstractmethod
    def extract(self, pdf_path: Path, profile: Optional[DocumentProfile] = None) -> ExtractedDocument:
        """
        Extract content from PDF.
        
        Args:
            pdf_path: Path to PDF file
            profile: Optional DocumentProfile from Triage Agent
            
        Returns:
            ExtractedDocument with normalized schema
        """
        pass
    
    @abstractmethod
    def confidence_score(self, extracted: ExtractedDocument) -> float:
        """
        Calculate confidence in extraction quality.
        Each strategy implements its own confidence logic.
        
        Returns:
            Float between 0 and 1
        """
        pass
    
    @abstractmethod
    def estimate_cost(self, pdf_path: Path) -> float:
        """
        Estimate cost before extraction.
        Used by Router for budget decisions.
        
        Returns:
            Estimated cost in USD
        """
        pass
    
    def can_handle(self, profile: DocumentProfile) -> bool:
        """
        Check if this extractor can handle the document.
        Default implementation - can be overridden.
        """
        return True
    
    def get_metadata(self) -> Dict[str, Any]:
        """Return extractor metadata"""
        return {
            'name': self.name,
            'version': '1.0',
            'cost_per_page': self._get_cost_per_page()
        }
    
    def _get_cost_per_page(self) -> float:
        """To be overridden by subclasses"""
        return 0.001