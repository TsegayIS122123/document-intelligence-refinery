"""
Audit Mode for verifying claims against source documents.
"""

import hashlib
import re
from typing import List, Dict, Optional, Tuple
from difflib import SequenceMatcher

from ..models.provenance import ProvenanceChain, SourceCitation, BBox
from ..utils.vector_store import VectorStore
from ..utils.sqlite_store import SQLiteStore
from ..utils.fact_extractor import FactExtractor


class AuditMode:
    """
    Claim verification system.
    Given a claim, either verifies with source or flags as unverifiable.
    """
    
    def __init__(self, vector_store: VectorStore, fact_extractor: FactExtractor):
        self.vector_store = vector_store
        self.fact_extractor = fact_extractor
        self.sqlite = SQLiteStore()
        
        # Thresholds for verification
        self.similarity_threshold = 0.5
        self.max_sources = 5
    
    def verify_claim(self, claim: str, doc_id: Optional[str] = None) -> ProvenanceChain:
        """
        Verify a claim against source documents.
        
        Steps:
        1. Search for relevant chunks
        2. Extract potential sources
        3. Compare claim with sources
        4. Calculate confidence
        5. Return ProvenanceChain
        """
        # Search for relevant chunks
        if doc_id:
            results = self.vector_store.search(
                claim,
                filter={'doc_id': doc_id},
                top_k=self.max_sources
            )
        else:
            results = self.vector_store.search(claim, top_k=self.max_sources)
        
        print(f"🔍 Search returned {len(results)} results")  # Debug output
        
        sources = []
        best_match_score = 0
        
        # Check each result for match
        for result in results:
            score, source = self._check_match(claim, result)
            print(f"  Match score: {score}")  # Debug output
            if score > self.similarity_threshold:
                sources.append(source)
                best_match_score = max(best_match_score, score)
        
        # Determine verification status
        if sources:
            if best_match_score >= 0.95:
                status = 'verified'
                confidence = best_match_score
            else:
                status = 'partial'
                confidence = best_match_score
            
            # Synthesize answer
            answer = self._synthesize_answer(claim, sources)
            
            return ProvenanceChain(
                claim=claim,
                sources=sources,
                synthesized_answer=answer,
                confidence=confidence,
                verification_status=status
            )
        else:
            # Try fact database
            facts = self.fact_extractor.query_facts(claim, doc_id)
            if facts:
                # Convert facts to sources
                for fact in facts[:self.max_sources]:
                    source = self._fact_to_source(fact)
                    sources.append(source)
                
                answer = self._synthesize_answer(claim, sources)
                return ProvenanceChain(
                    claim=claim,
                    sources=sources,
                    synthesized_answer=answer,
                    confidence=0.9,
                    verification_status='verified'
                )
            else:
                answer = f"Cannot verify claim: '{claim}' - no matching sources found."
                return ProvenanceChain(
                    claim=claim,
                    sources=[],  # Empty list for unverifiable
                    synthesized_answer=answer,
                    confidence=0.0,
                    verification_status='unverifiable'
                )
    
    def _check_match(self, claim: str, result: Dict) -> Tuple[float, Optional[SourceCitation]]:
        """
        Check if a search result matches the claim.
        Returns (similarity_score, SourceCitation if match)
        """
        content = result.get('content', '')
        metadata = result.get('metadata', {})
        
        print(f"  Checking match against: {content[:50]}...")  # Debug output
        
        # Calculate similarity
        similarity = SequenceMatcher(None, claim.lower(), content.lower()).ratio()
        print(f"  Similarity: {similarity}")  # Debug output
        
        if similarity >= self.similarity_threshold:
            # Create source citation
            bbox = None
            if 'bbox' in metadata:
                bbox_data = metadata['bbox']
                if isinstance(bbox_data, dict):
                    bbox = BBox(**bbox_data)
                elif isinstance(bbox_data, (list, tuple)) and len(bbox_data) == 4:
                    bbox = BBox(
                        x0=bbox_data[0], y0=bbox_data[1],
                        x1=bbox_data[2], y1=bbox_data[3],
                        page_num=metadata.get('page_num', 1)
                    )
            
            # Generate proper hex hash
            import hashlib
            proper_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
            
            source = SourceCitation(
                document_name=metadata.get('doc_id', 'unknown'),
                page_number=metadata.get('page_num', 1),
                bbox=bbox if bbox else BBox(x0=0, y0=0, x1=0, y1=0, page_num=1),
                content_hash=proper_hash,
                extracted_text=content[:200],
                confidence=similarity
            )
            return similarity, source
        
        return similarity, None
    
    def _fact_to_source(self, fact: Dict) -> SourceCitation:
        """
        Convert a fact dictionary to SourceCitation.
        """
        bbox_data = fact.get('bbox')
        bbox = None
        if bbox_data:
            if isinstance(bbox_data, str):
                import json
                bbox_data = json.loads(bbox_data)
            bbox = BBox(**bbox_data)
        else:
            bbox = BBox(x0=0, y0=0, x1=0, y1=0, page_num=fact.get('page_number', 1))
        
        return SourceCitation(
            document_name=fact.get('document_name', 'unknown'),
            page_number=fact.get('page_number', 1),
            bbox=bbox,
            content_hash=fact.get('content_hash', ''),
            extracted_text=f"{fact.get('key')}: {fact.get('value')}",
            confidence=fact.get('confidence', 0.8)
        )
    
    def _synthesize_answer(self, claim: str, sources: List[SourceCitation]) -> str:
        """
        Synthesize an answer from sources.
        """
        if len(sources) == 1:
            src = sources[0]
            return f"✓ Verified: '{claim}' found on page {src.page_number} of {src.document_name}"
        else:
            pages = ', '.join(str(s.page_number) for s in sources)
            docs = ', '.join(set(s.document_name for s in sources))
            return f"✓ Verified: '{claim}' found on pages {pages} in {docs}"
    
    def batch_verify(self, claims: List[str], doc_id: Optional[str] = None) -> List[ProvenanceChain]:
        """
        Verify multiple claims in batch.
        """
        results = []
        for claim in claims:
            results.append(self.verify_claim(claim, doc_id))
        return results
    
    def audit_report(self, doc_id: str) -> Dict:
        """
        Generate an audit report for a document.
        """
        # Get document info
        doc_info = self.sqlite.get_document(doc_id)
        
        # Get fact summary
        fact_summary = self.fact_extractor.get_fact_summary(doc_id)
        
        # Get recent queries about this doc
        history = self.sqlite.get_query_history(limit=20)
        doc_queries = [q for q in history if doc_id in str(q)]
        
        return {
            'document': doc_info,
            'facts': fact_summary,
            'recent_queries': doc_queries,
            'audit_date': datetime.now().isoformat()
        }