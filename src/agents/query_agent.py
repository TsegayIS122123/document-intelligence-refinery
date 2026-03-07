"""
Query Agent with three tools for document querying.
Implements LangGraph agent with pageindex_navigate, semantic_search, and structured_query.
"""

import hashlib
import time
from typing import List, Dict, Optional, Any
from datetime import datetime

from ..models.provenance import ProvenanceChain, SourceCitation, BBox
from ..models.document import PageIndex
from ..utils.vector_store import VectorStore
from ..utils.fact_extractor import FactExtractor
from ..utils.sqlite_store import SQLiteStore


class QueryAgent:
    """
    Agent that provides three query tools:
    1. pageindex_navigate - Navigate document hierarchy
    2. semantic_search - Vector search in chunks
    3. structured_query - SQL query over facts
    
    Every answer includes a ProvenanceChain with full citations.
    """
    
    def __init__(
        self,
        vector_store: VectorStore,
        fact_extractor: FactExtractor,
        pageindex: Optional[PageIndex] = None
    ):
        self.vector_store = vector_store
        self.fact_extractor = fact_extractor
        self.sqlite = SQLiteStore()
        self.pageindex = pageindex
        
    def query(self, query_text: str) -> ProvenanceChain:
        """
        Main query method - returns answer with provenance.
        """
        start_time = time.time()
        
        # Route query to appropriate tool
        sources = self._route_query(query_text)
        
        # Synthesize answer
        if sources:
            confidence = max(s.confidence for s in sources)
            if confidence >= 0.9:
                status = 'verified'
            elif confidence >= 0.5:
                status = 'partial'
            else:
                status = 'unverifiable'
            answer = self._synthesize_answer(query_text, sources)
        else:
            answer = f"No information found for: '{query_text}'"
            status = 'unverifiable'
            confidence = 0.0
        
        # Create provenance chain
        provenance = ProvenanceChain(
            claim=query_text,
            sources=sources,
            synthesized_answer=answer,
            confidence=confidence,
            verification_status=status
        )
        
        # Save to history
        self.sqlite.save_query(
            query_id=provenance.query_id,
            query=query_text,
            response=provenance.model_dump(),
            processing_time=time.time() - start_time
        )
        
        return provenance
    
    def _route_query(self, query_text: str) -> List[SourceCitation]:
        """
        Route query to appropriate tool based on content.
        """
        query_lower = query_text.lower()
        
        # Route based on query type
        if any(word in query_lower for word in ['navigate', 'section', 'table of contents', 'structure']):
            return self.tool_pageindex_navigate(query_text)
        elif any(word in query_lower for word in ['>', '<', '=', 'million', 'billion']) and \
             any(word in query_lower for word in ['revenue', 'profit', 'expense']):
            return self.tool_structured_query(query_text)
        else:
            return self.tool_semantic_search(query_text)
    
    def tool_semantic_search(self, query: str, top_k: int = 5) -> List[SourceCitation]:
        """
        Tool 1: Semantic search using vector store.
        """
        results = self.vector_store.search(query, top_k=top_k)
        sources = []

        for result in results:
            metadata = result.get('metadata', {})
            
            # Get bbox data safely
            bbox_data = metadata.get('bbox', [0, 0, 100, 100])
            if isinstance(bbox_data, (list, tuple)) and len(bbox_data) == 4:
                x0, y0, x1, y1 = bbox_data
            else:
                x0, y0, x1, y1 = 0, 0, 100, 100
            
            # Ensure x1 > x0 and y1 > y0
            if x1 <= x0:
                x1 = x0 + 100
            if y1 <= y0:
                y1 = y0 + 100
            
            # Create bbox with validated coordinates
            bbox = BBox(
                x0=float(x0),
                y0=float(y0),
                x1=float(x1),
                y1=float(y1),
                page_num=metadata.get('page_num', 1)
            )
            
            # Generate PROPER hex hash (only 0-9, a-f)
            import hashlib
            content = result.get('content', '')
            proper_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
            # This will produce something like: "a1b2c3d4e5f6a7b8" (only hex chars)
            
            source = SourceCitation(
                document_name=metadata.get('doc_id', 'unknown'),
                page_number=metadata.get('page_num', 1),
                bbox=bbox,
                content_hash=proper_hash,  # ✅ Now using proper hex hash
                extracted_text=content[:200],
                confidence=result.get('score', 0.5)
            )
            sources.append(source)
        
        return sources
    
    def tool_pageindex_navigate(self, query: str) -> List[SourceCitation]:
        """
        Tool 2: Navigate PageIndex to find relevant sections.
        """
        if not self.pageindex:
            return []
        
        from .indexer import PageIndexQuerier
        querier = PageIndexQuerier(self.pageindex, self.vector_store)
        sections = querier.navigate(query, top_k=3)
        
        sources = []
        for section in sections:
            source = SourceCitation(
                document_name=self.pageindex.filename,
                page_number=section.page_start,
                bbox=BBox(x0=0, y0=0, x1=0, y1=0, page_num=section.page_start),
                content_hash=hashlib.md5(section.title.encode()).hexdigest()[:16],
                extracted_text=f"Section: {section.title}\n{section.summary or ''}",
                confidence=0.8
            )
            sources.append(source)
        
        return sources
    
    def tool_structured_query(self, query: str) -> List[SourceCitation]:
        """
        Tool 3: Query facts using SQLite.
        """
        facts = self.fact_extractor.query_facts(query)
        sources = []
        
        for fact in facts[:5]:
            bbox = BBox(x0=0, y0=0, x1=0, y1=0, page_num=fact.get('page_number', 1))
            
            source = SourceCitation(
                document_name=fact.get('document_name', 'unknown'),
                page_number=fact.get('page_number', 1),
                bbox=bbox,
                content_hash=fact.get('content_hash', ''),
                extracted_text=f"{fact.get('key')}: {fact.get('value')}",
                confidence=fact.get('confidence', 0.8)
            )
            sources.append(source)
        
        return sources
    
    def _synthesize_answer(self, query: str, sources: List[SourceCitation]) -> str:
        """
        Synthesize answer from sources.
        """
        if not sources:
            return f"No information found for: '{query}'"
        
        if len(sources) == 1:
            src = sources[0]
            return f"✓ Found in {src.document_name} (page {src.page_number}): {src.extracted_text}"
        else:
            # Group by document
            by_doc = {}
            for src in sources:
                if src.document_name not in by_doc:
                    by_doc[src.document_name] = []
                by_doc[src.document_name].append(src)
            
            parts = []
            for doc, doc_sources in by_doc.items():
                pages = ', '.join(str(s.page_number) for s in doc_sources)
                parts.append(f"{doc} (pages {pages})")
            
            return f"✓ Found in: {', '.join(parts)}"