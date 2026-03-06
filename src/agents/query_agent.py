"""
LangGraph Query Agent with three tools:
1. pageindex_navigate - Navigate document hierarchy
2. semantic_search - Vector search in chunks
3. structured_query - SQL query over facts
"""

import json
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
import hashlib

try:
    from langgraph.graph import StateGraph, END
    from langgraph.prebuilt import ToolExecutor
    from langchain_core.messages import HumanMessage, AIMessage
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    

from ..models.provenance import ProvenanceChain, SourceCitation, BBox
from ..models.document import PageIndex
from ..utils.vector_store import VectorStore
from ..utils.fact_extractor import FactExtractor
from ..utils.sqlite_store import SQLiteStore


class QueryAgent:
    """
    LangGraph agent with three tools for querying documents.
    Every answer includes ProvenanceChain.
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
        
        # Tool registry
        self.tools = {
            'pageindex_navigate': self.tool_pageindex_navigate,
            'semantic_search': self.tool_semantic_search,
            'structured_query': self.tool_structured_query,
        }
        
        # Initialize LangGraph if available
        if LANGGRAPH_AVAILABLE:
            self._init_langgraph()
    
    def _init_langgraph(self):
        """Initialize LangGraph workflow"""
        # Define graph state
        class AgentState(dict):
            messages: List
            query: str
            context: Dict
            sources: List
            answer: Optional[str]
            provenance: Optional[ProvenanceChain]
        
        # Create graph
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("classify_query", self._classify_query)
        workflow.add_node("pageindex_navigate", self._run_tool)
        workflow.add_node("semantic_search", self._run_tool)
        workflow.add_node("structured_query", self._run_tool)
        workflow.add_node("synthesize", self._synthesize)
        
        # Add edges
        workflow.set_entry_point("classify_query")
        workflow.add_conditional_edges(
            "classify_query",
            self._route_query,
            {
                "navigate": "pageindex_navigate",
                "search": "semantic_search",
                "query": "structured_query",
                "synthesize": "synthesize"
            }
        )
        workflow.add_edge("pageindex_navigate", "synthesize")
        workflow.add_edge("semantic_search", "synthesize")
        workflow.add_edge("structured_query", "synthesize")
        workflow.add_edge("synthesize", END)
        
        self.graph = workflow.compile()
    
    def query(self, query_text: str) -> ProvenanceChain:
        """
        Main query method - returns answer with provenance.
        """
        start_time = time.time()
        
        if LANGGRAPH_AVAILABLE and self.graph:
            # Use LangGraph
            result = self.graph.invoke({
                "messages": [HumanMessage(content=query_text)],
                "query": query_text,
                "context": {},
                "sources": [],
                "answer": None,
                "provenance": None
            })
            provenance = result.get("provenance")
        else:
            # Fallback to simple routing
            provenance = self._simple_query(query_text)
        
        # Save to history
        self.sqlite.save_query(
            query_id=provenance.query_id if provenance else hashlib.md5(query_text.encode()).hexdigest()[:8],
            query=query_text,
            response=provenance.model_dump() if provenance else {},
            processing_time=time.time() - start_time
        )
        
        return provenance
    
    def _simple_query(self, query_text: str) -> ProvenanceChain:
        """
        Simple query routing without LangGraph.
        """
        query_lower = query_text.lower()

        # Better routing logic
        if any(word in query_lower for word in ['navigate', 'section', 'table of contents', 'structure']):
            # Use pageindex navigation
            sources = self.tool_pageindex_navigate(query_text)
        elif any(word in query_lower for word in ['>', '<', '=', 'million', 'billion']) and any(word in query_lower for word in ['revenue', 'profit', 'expense']):
            # Use structured query ONLY for explicit numerical comparisons
            sources = self.tool_structured_query(query_text)
        else:
            # Default to semantic search for most queries
            sources = self.tool_semantic_search(query_text)

        # Synthesize answer with proper status logic
        if sources:
            # Calculate confidence
            confidence = max(s.confidence for s in sources) if sources else 0

            # Set status based on confidence threshold
            if confidence >= 0.9:
                status = 'verified'
            elif confidence >= 0.5:
                status = 'partial'
            else:
                status = 'partial'  # ← CHANGED: Don't use 'unverifiable' when sources exist!

            answer = self._synthesize_answer(query_text, sources)
            return ProvenanceChain(
                claim=query_text,
                sources=sources,
                synthesized_answer=answer,
                confidence=confidence,
                verification_status=status
            )
        else:
            answer = f"No information found for: '{query_text}'"
            return ProvenanceChain(
                claim=query_text,
                sources=[],  # Empty sources for unverifiable
                synthesized_answer=answer,
                confidence=0.0,
                verification_status='unverifiable'
            )
    
    # === Tool 1: PageIndex Navigation ===
    
    def tool_pageindex_navigate(self, query: str) -> List[SourceCitation]:
        """
        Navigate document hierarchy to find relevant sections.
        """
        if not self.pageindex:
            return []
        
        query_lower = query.lower()
        relevant_sections = []
        
        def search_sections(node):
            score = 0
            if query_lower in node.title.lower():
                score += 10
            if node.summary and query_lower in node.summary.lower():
                score += 5
            for entity in node.key_entities:
                if query_lower in entity.lower():
                    score += 3
            
            if score > 0:
                relevant_sections.append((score, node))
            
            for child in node.child_sections:
                search_sections(child)
        
        # Search all sections
        for root in self.pageindex.root_sections:
            search_sections(root)
        
        # Sort by relevance
        relevant_sections.sort(key=lambda x: x[0], reverse=True)
        
        # Convert to sources
        sources = []
        for score, section in relevant_sections[:3]:
            source = SourceCitation(
                document_name=self.pageindex.filename,
                page_number=section.page_start,
                bbox=BBox(x0=0, y0=0, x1=0, y1=0, page_num=section.page_start),
                content_hash=hashlib.md5(section.title.encode()).hexdigest()[:16],
                extracted_text=f"Section: {section.title}\n{section.summary or ''}",
                confidence=min(1.0, score / 10)
            )
            sources.append(source)
        
        return sources
    
    # === Tool 2: Semantic Search ===
    
    def tool_semantic_search(self, query: str, top_k: int = 5) -> List[SourceCitation]:
        """
        Search chunks using vector similarity.
        """
        # Generate embedding for query (simplified for testing)
        import numpy as np
        seed = hash(query) % 10000
        np.random.seed(seed)
        query_embedding = np.random.randn(384).astype('float32').tolist()
        
        results = self.vector_store.search(query, embedding=query_embedding, top_k=top_k)
        print(f"📊 Search returned {len(results)} results")
        
  # In tool_semantic_search method, after getting results
        sources = []
        for result in results:
            metadata = result.get('metadata', {})
            
            # Create bbox from metadata
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
            else:
                bbox = BBox(x0=0, y0=0, x1=0, y1=0, page_num=metadata.get('page_num', 1))
            
            # Fix 1: Generate proper hex hash
            import hashlib
            content = result.get('content', '')
            proper_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
            
            # Fix 2: Normalize confidence score
            raw_score = result.get('score', 0.8)
            confidence = (raw_score + 1) / 2  # Maps [-1,1] to [0,1]
            confidence = max(0, min(1, confidence))  # Clamp to [0,1]
            
            source = SourceCitation(
                document_name=metadata.get('doc_id', 'unknown'),
                page_number=metadata.get('page_num', 1),
                bbox=bbox,
                content_hash=proper_hash,  # ← Fixed
                extracted_text=content[:200],
                confidence=confidence  # ← Fixed
            )
            sources.append(source)
                
        return sources
    
    # === Tool 3: Structured Query ===
    
    def tool_structured_query(self, query: str) -> List[SourceCitation]:
        """
        Query facts using SQLite.
        """
        facts = self.fact_extractor.query_facts(query)
        
        sources = []
        for fact in facts[:5]:
            # Parse bbox from JSON string if needed
            bbox_data = fact.get('bbox')
            bbox = None
            if bbox_data:
                if isinstance(bbox_data, str):
                    import json
                    bbox_data = json.loads(bbox_data)
                bbox = BBox(**bbox_data)
            else:
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
    
    # === LangGraph Node Functions ===
    
    def _classify_query(self, state):
        """Classify query type for routing"""
        query = state["query"].lower()
        
        if any(word in query for word in ['navigate', 'section', 'toc', 'structure', 'table of contents']):
            state["context"]["tool"] = "navigate"
        elif any(word in query for word in ['revenue', 'profit', 'financial', 'number', 'value', 'amount', 'total']):
            state["context"]["tool"] = "query"
        else:
            state["context"]["tool"] = "search"
        
        return state
    
    def _route_query(self, state):
        """Route to appropriate tool"""
        tool = state["context"].get("tool", "search")
        return tool
    
    def _run_tool(self, state):
        """Execute selected tool"""
        tool_name = state["context"]["tool"]
        query = state["query"]
        
        if tool_name == "navigate":
            sources = self.tool_pageindex_navigate(query)
        elif tool_name == "search":
            sources = self.tool_semantic_search(query)
        elif tool_name == "query":
            sources = self.tool_structured_query(query)
        else:
            sources = []
        
        state["sources"] = sources
        return state
    
    def _synthesize(self, state):
        """Synthesize answer from sources"""
        query = state["query"]
        sources = state["sources"]
        
        if sources:
            answer = self._synthesize_answer(query, sources)
            status = 'verified' if len(sources) > 0 else 'partial'
            confidence = max(s.confidence for s in sources) if sources else 0
        else:
            answer = f"No information found for: '{query}'"
            status = 'unverifiable'
            confidence = 0
        
        # Create provenance
        provenance = ProvenanceChain(
            claim=query,
            sources=sources,
            synthesized_answer=answer,
            confidence=confidence,
            verification_status=status
        )
        
        state["provenance"] = provenance
        state["answer"] = answer
        
        return state
    
    def _synthesize_answer(self, query: str, sources: List[SourceCitation]) -> str:
        """Synthesize answer from sources"""
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