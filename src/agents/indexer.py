"""
PageIndex Builder - Creates hierarchical navigation structure.
Enables LLM to traverse document without reading everything.
"""

import hashlib
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import json
from pathlib import Path

from ..models.chunking import LDU, ChunkType
from ..models.document import PageIndex, PageIndexNode
from ..utils.vector_store import VectorStore


class PageIndexBuilder:
    """
    Builds hierarchical PageIndex from chunks.
    Creates a "smart table of contents" with summaries.
    """
    
    def __init__(self, llm_client=None):
        self.llm = llm_client  # For generating summaries
        self.sections = defaultdict(list)  # section_path -> chunks
    
    def build(self, chunks: List[LDU], doc_id: str, filename: str) -> PageIndex:
        """
        Build PageIndex from chunks.
        
        Steps:
        1. Extract section hierarchy from chunks
        2. Group chunks by section
        3. Generate summaries for each section
        4. Extract key entities
        5. Build navigation tree
        """
        # Reset
        self.sections = defaultdict(list)
        
        # Group chunks by section
        for chunk in chunks:
            section = chunk.parent_section or "root"
            self.sections[section].append(chunk)
        
        # Build tree recursively
        root_sections = self._build_tree("root", chunks)
        
        # Generate summaries for each section
        self._generate_summaries(root_sections, chunks)
        
        # Extract key entities
        self._extract_entities(root_sections, chunks)
        
        # Get total pages
        total_pages = max(
            (c.primary_page for c in chunks),
            default=0
        )
        
        return PageIndex(
            doc_id=doc_id,
            filename=filename,
            root_sections=root_sections,
            total_pages=total_pages
        )
    
    def _build_tree(self, section_path: str, all_chunks: List[LDU]) -> List[PageIndexNode]:
        """
        Recursively build section tree.
        """
        nodes = []
        
        # Find direct children of this section
        child_sections = {}
        for chunk in all_chunks:
            if chunk.chunk_type == ChunkType.SECTION_HEADER:
                if chunk.parent_section == section_path or (
                    section_path == "root" and chunk.section_depth == 1
                ):
                    child_sections[chunk.content] = chunk
        
        # Build nodes for each child section
        for section_title, header_chunk in child_sections.items():
            # Find all chunks in this section
            section_chunks = [
                c for c in all_chunks
                if c.parent_section == section_title or (
                    hasattr(c, 'section_path') and section_title in c.section_path
                )
            ]
            
            # Get page range
            if section_chunks:
                page_start = min(c.primary_page for c in section_chunks)
                page_end = max(c.primary_page for c in section_chunks)
            else:
                page_start = header_chunk.primary_page
                page_end = header_chunk.primary_page
            
            # Build child sections recursively
            child_section_path = section_title
            child_nodes = self._build_tree(child_section_path, all_chunks)
            
            # Create node
            node = PageIndexNode(
                id=f"section_{hashlib.md5(section_title.encode()).hexdigest()[:8]}",
                title=section_title,
                page_start=page_start,
                page_end=page_end,
                child_sections=child_nodes,
                key_entities=[],  # Will be filled later
                summary=None,  # Will be filled later
                data_types_present=self._get_data_types(section_chunks)
            )
            nodes.append(node)
        
        return sorted(nodes, key=lambda n: n.page_start)
    
    def _get_data_types(self, chunks: List[LDU]) -> List[str]:
        """Get data types present in section"""
        types = set()
        for chunk in chunks:
            types.add(chunk.chunk_type.value)
        return list(types)
    
    def _generate_summaries(self, nodes: List[PageIndexNode], all_chunks: List[LDU]):
        """
        Generate LLM summaries for each section.
        Uses fast, cheap model (or rule-based fallback).
        """
        for node in nodes:
            # Get all chunks in this section
            section_chunks = [
                c for c in all_chunks
                if c.parent_section == node.title
            ]
            
            if section_chunks:
                # Create summary (rule-based for now)
                summary = self._create_rule_based_summary(
                    node.title,
                    section_chunks
                )
                node.summary = summary
            
            # Recursively process children
            self._generate_summaries(node.child_sections, all_chunks)
    
    def _create_rule_based_summary(self, title: str, chunks: List[LDU]) -> str:
        """
        Create summary without LLM (fallback).
        """
        # Count types
        type_counts = defaultdict(int)
        for chunk in chunks:
            type_counts[chunk.chunk_type.value] += 1
        
        # Get first few words of first text chunk
        first_text = next(
            (c.content[:100] for c in chunks if c.chunk_type == ChunkType.TEXT),
            ""
        )
        
        summary_parts = [
            f"Section: {title}",
            f"Contains: {', '.join(f'{v} {k}s' for k, v in type_counts.items())}",
        ]
        
        if first_text:
            summary_parts.append(f"Sample: {first_text}...")
        
        return " | ".join(summary_parts)
    
    def _extract_entities(self, nodes: List[PageIndexNode], all_chunks: List[LDU]):
        """
        Extract key entities from section chunks.
        Simple rule-based extraction (can be enhanced with NER).
        """
        for node in nodes:
            # Get chunks in this section
            section_chunks = [
                c for c in all_chunks
                if c.parent_section == node.title
            ]
            
            # Extract potential entities
            entities = set()
            
            # Look for capitalized phrases
            for chunk in section_chunks:
                words = chunk.content.split()
                for i in range(len(words) - 1):
                    if words[i][0].isupper() and words[i+1][0].isupper():
                        entities.add(f"{words[i]} {words[i+1]}")
                    elif words[i][0].isupper() and len(words[i]) > 3:
                        entities.add(words[i])
            
            node.key_entities = list(entities)[:10]  # Limit to 10
            
            # Recursively process children
            self._extract_entities(node.child_sections, all_chunks)


class PageIndexQuerier:
    """
    Query interface for PageIndex.
    Enables hierarchical navigation before vector search.
    """
    
    def __init__(self, pageindex: PageIndex, vector_store: VectorStore):
        self.pageindex = pageindex
        self.vector_store = vector_store
    
    def navigate(self, topic: str, top_k: int = 3) -> List[PageIndexNode]:
        """
        Navigate PageIndex to find most relevant sections.
        Uses section summaries and titles to match topic.
        
        Returns:
            Top-k most relevant sections
        """
        scored_sections = []
        
        def score_section(node: PageIndexNode, path: str = ""):
            """Score a section for relevance to topic"""
            score = 0
            
            # Title match
            if topic.lower() in node.title.lower():
                score += 10
            
            # Summary match
            if node.summary and topic.lower() in node.summary.lower():
                score += 5
            
            # Entity match
            for entity in node.key_entities:
                if topic.lower() in entity.lower():
                    score += 3
            
            # Boost if data types match
            if 'table' in topic.lower() and 'table' in node.data_types_present:
                score += 2
            if 'figure' in topic.lower() and 'figure' in node.data_types_present:
                score += 2
            
            scored_sections.append((score, node, path))
            
            # Score children
            for child in node.child_sections:
                score_section(child, f"{path} > {node.title}")
        
        # Score all sections
        for root in self.pageindex.root_sections:
            score_section(root)
        
        # Sort by score and return top-k
        scored_sections.sort(key=lambda x: x[0], reverse=True)
        return [node for score, node, path in scored_sections[:top_k]]
    
    def retrieve(
        self,
        query: str,
        topic: Optional[str] = None,
        top_k: int = 5
    ) -> List[Dict]:
        """
        Retrieve chunks with optional PageIndex navigation.
        
        If topic provided, first navigates to relevant sections,
        then searches only within those sections.
        """
        if topic:
            # Navigate to relevant sections
            sections = self.navigate(topic, top_k=3)
            
            # Get page ranges
            page_ranges = [(s.page_start, s.page_end) for s in sections]
            
            # Search only in those page ranges
            results = self.vector_store.search(
                query,
                filter={
                    'page_num': {
                        '$between': page_ranges[0] if page_ranges else None
                    }
                },
                top_k=top_k
            )
        else:
            # Search everything
            results = self.vector_store.search(query, top_k=top_k)
        
        return results
    
    def compare_retrieval(
        self,
        query: str,
        topic: str,
        top_k: int = 5
    ) -> Dict:
        """
        Compare retrieval with and without PageIndex navigation.
        Measures improvement from hierarchical navigation.
        """
        # With PageIndex
        start = time.time()
        with_nav = self.retrieve(query, topic=topic, top_k=top_k)
        nav_time = time.time() - start
        
        # Without PageIndex
        start = time.time()
        without_nav = self.retrieve(query, topic=None, top_k=top_k)
        no_nav_time = time.time() - start
        
        # Calculate precision improvement
        # (Assume we can judge relevance by presence of topic in content)
        def relevance_score(chunks, topic):
            if not chunks:
                return 0
            relevant = sum(1 for c in chunks if topic.lower() in c['content'].lower())
            return relevant / len(chunks)
        
        precision_with = relevance_score(with_nav, topic)
        precision_without = relevance_score(without_nav, topic)
        
        return {
            'query': query,
            'topic': topic,
            'with_navigation': {
                'time': nav_time,
                'results': with_nav,
                'precision': precision_with
            },
            'without_navigation': {
                'time': no_nav_time,
                'results': without_nav,
                'precision': precision_without
            },
            'improvement': {
                'time_saved': no_nav_time - nav_time,
                'precision_gain': precision_with - precision_without
            }
        }