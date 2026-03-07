"""
PageIndex Builder - Creates hierarchical navigation structure.
Enables LLM to traverse document without reading everything.
"""

import hashlib
import os
import time
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

from ..models.chunking import LDU, ChunkType
from ..models.document import PageIndex, PageIndexNode
from ..utils.vector_store import VectorStore

# Try to import OpenAI for LLM summaries
try:
    from openai import OpenAI
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    print("⚠️ OpenAI not installed. Using rule-based summaries.")


class PageIndexBuilder:
    """
    Builds hierarchical PageIndex from chunks.
    Creates a "smart table of contents" with LLM-generated summaries.
    """

    def __init__(self, llm_client=None, use_llm: bool = True):
        """
        Initialize PageIndexBuilder.

        Args:
            llm_client: Optional LLM client (will create if not provided)
            use_llm: Whether to use LLM for summaries (falls back to rule-based)
        """
        self.use_llm = use_llm and LLM_AVAILABLE
        self.sections = defaultdict(list)  # section_path -> chunks

        # Initialize LLM client if requested
        if self.use_llm:
            if llm_client:
                self.llm = llm_client
            else:
                try:
                    self.llm = OpenAI(
                        base_url="https://openrouter.ai/api/v1",
                        api_key=os.getenv("OPENROUTER_API_KEY"),
                        default_headers={
                            "HTTP-Referer": "https://github.com/TsegayIS122123/document-intelligence-refinery",
                            "X-Title": "Document Intelligence Refinery"
                        }
                    )
                except Exception as e:
                    print(f"⚠️ LLM initialization failed: {e}. Using rule-based summaries.")
                    self.use_llm = False
        else:
            self.llm = None

    def build(self, chunks: List[LDU], doc_id: str, filename: str, 
              save: bool = True, output_dir: str = ".refinery/pageindex") -> PageIndex:
        """
        Build PageIndex from chunks and optionally save to disk.

        Steps:
        1. Extract section hierarchy from chunks
        2. Group chunks by section
        3. Generate summaries for each section (LLM or rule-based)
        4. Extract key entities
        5. Build navigation tree
        6. Save to disk (optional)

        Args:
            chunks: List of LDUs
            doc_id: Document ID
            filename: Original filename
            save: Whether to save to disk
            output_dir: Directory to save (configurable)

        Returns:
            PageIndex object
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

        pageindex = PageIndex(
            doc_id=doc_id,
            filename=filename,
            root_sections=root_sections,
            total_pages=total_pages
        )
        
        # Save to disk if requested
        if save:
            self.save(pageindex, output_dir)
        
        return pageindex

    def _build_tree(self, section_path: str, all_chunks: List[LDU]) -> List[PageIndexNode]:
        """
        Recursively build section tree with all required attributes.
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

            # Extract key entities from this section
            key_entities = self._extract_entities_from_chunks(section_chunks)
            
            # Get data types present
            data_types = self._get_data_types(section_chunks)

            # Create node with all attributes populated
            node = PageIndexNode(
                id=f"section_{hashlib.md5(section_title.encode()).hexdigest()[:8]}",
                title=section_title,
                page_start=page_start,
                page_end=page_end,
                child_sections=child_nodes,
                key_entities=key_entities,  # Now populated
                summary=None,  # Will be filled later in _generate_summaries
                data_types_present=data_types  # Now populated
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
        Generate summaries for each section.
        Uses LLM if available, otherwise falls back to rule-based.
        """
        for node in nodes:
            # Get all chunks in this section
            section_chunks = [
                c for c in all_chunks
                if c.parent_section == node.title
            ]

            if section_chunks:
                # Generate summary (LLM or rule-based)
                if self.use_llm:
                    summary = self._generate_llm_summary(
                        node.title,
                        section_chunks
                    )
                else:
                    summary = self._create_rule_based_summary(
                        node.title,
                        section_chunks
                    )
                node.summary = summary

            # Recursively process children
            self._generate_summaries(node.child_sections, all_chunks)

    def _generate_llm_summary(self, title: str, chunks: List[LDU]) -> str:
        """
        Generate summary using cheap LLM (GPT-4o-mini).
        Falls back to rule-based if LLM fails.
        """
        if not self.use_llm or not self.llm:
            return self._create_rule_based_summary(title, chunks)

        try:
            # Collect sample content (first 500 chars of first few chunks)
            content_samples = []
            for chunk in chunks[:3]:  # Limit to first 3 chunks
                if chunk.chunk_type == ChunkType.TEXT:
                    content_samples.append(chunk.content[:200])
                elif chunk.chunk_type == ChunkType.TABLE:
                    headers = chunk.metadata.get('headers', ['Table'])
                    content_samples.append(f"[Table: {headers[0] if headers else 'Table'}]")
                elif chunk.chunk_type == ChunkType.FIGURE:
                    content_samples.append(f"[Figure: {chunk.metadata.get('caption', 'Figure')}]")

            sample_text = ' '.join(content_samples)

            # Count types for context
            type_counts = defaultdict(int)
            for chunk in chunks:
                type_counts[chunk.chunk_type.value] += 1

            type_summary = ', '.join(f"{count} {type}" for type, count in type_counts.items())

            # Call LLM (using cheap model)
            response = self.llm.chat.completions.create(
                model="openai/gpt-4o-mini",  # Cheap model ($0.15/1M tokens)
                messages=[
                    {
                        "role": "system",
                        "content": "You are a document summarizer. Create a concise 2-3 sentence summary of this document section. Focus on the main topic and key points."
                    },
                    {
                        "role": "user",
                        "content": f"Section title: {title}\n\nContent preview: {sample_text}\n\nContains: {type_summary}\n\nGenerate a brief summary (2-3 sentences):"
                    }
                ],
                max_tokens=100,
                temperature=0.3
            )

            summary = response.choices[0].message.content.strip()
            return summary

        except Exception as e:
            print(f"⚠️ LLM summary failed: {e}. Using rule-based fallback.")
            return self._create_rule_based_summary(title, chunks)

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

    def _extract_entities_from_chunks(self, chunks: List[LDU]) -> List[str]:
        """
        Extract key entities from section chunks.
        """
        entities = set()
        
        # Look for capitalized phrases (potential named entities)
        for chunk in chunks:
            if chunk.chunk_type in [ChunkType.TEXT, ChunkType.SECTION_HEADER]:
                words = chunk.content.split()
                for i in range(len(words) - 1):
                    # Two consecutive capitalized words
                    if len(words[i]) > 1 and words[i][0].isupper() and \
                       len(words[i+1]) > 1 and words[i+1][0].isupper():
                        entities.add(f"{words[i]} {words[i+1]}")
                    # Single capitalized word (longer than 3 chars)
                    elif words[i][0].isupper() and len(words[i]) > 3:
                        entities.add(words[i])
        
        return list(entities)[:10]  # Limit to 10 entities per section

    def _extract_entities(self, nodes: List[PageIndexNode], all_chunks: List[LDU]):
        """
        Extract key entities from section chunks.
        """
        for node in nodes:
            # Get chunks in this section
            section_chunks = [
                c for c in all_chunks
                if c.parent_section == node.title
            ]
            
            # Extract entities using the helper method
            node.key_entities = self._extract_entities_from_chunks(section_chunks)
            
            # Recursively process children
            self._extract_entities(node.child_sections, all_chunks)

    def save(self, pageindex: PageIndex, output_dir: str = ".refinery/pageindex") -> Path:
        """
        Serialize PageIndex to JSON at configurable output path.

        Args:
            pageindex: The PageIndex object to save
            output_dir: Directory to save the JSON file (configurable)

        Returns:
            Path to the saved JSON file
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Create filename based on doc_id
        file_path = output_path / f"{pageindex.doc_id}.json"

        # Convert to JSON and save
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(pageindex.model_dump_json(indent=2))

        print(f"✅ PageIndex saved to: {file_path}")
        return file_path

    def load(self, doc_id: str, input_dir: str = ".refinery/pageindex") -> Optional[PageIndex]:
        """
        Load PageIndex from JSON file.

        Args:
            doc_id: Document ID to load
            input_dir: Directory containing the JSON files

        Returns:
            PageIndex object or None if not found
        """
        file_path = Path(input_dir) / f"{doc_id}.json"

        if not file_path.exists():
            print(f"⚠️ PageIndex not found: {file_path}")
            return None

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return PageIndex(**data)


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

            # Summary match (LLM summaries make this more effective!)
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

            if not sections:
                # No relevant sections found, search everything
                return self.vector_store.search(query, top_k=top_k)

            # Get page ranges from all relevant sections
            page_ranges = []
            for section in sections:
                page_ranges.append((section.page_start, section.page_end))
            
            # Use the first section's page range for filtering
            # (In production, you'd want more sophisticated filtering)
            first_range = page_ranges[0] if page_ranges else None
            
            # Search only in those page ranges
            results = self.vector_store.search(
                query,
                filter={
                    'page_num': {
                        '$between': first_range
                    }
                } if first_range else None,
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
        import time

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
            relevant = sum(1 for c in chunks if topic.lower() in c.get('content', '').lower())
            return relevant / len(chunks) if chunks else 0

        precision_with = relevance_score(with_nav, topic)
        precision_without = relevance_score(without_nav, topic)

        return {
            'query': query,
            'topic': topic,
            'with_navigation': {
                'time': nav_time,
                'results_count': len(with_nav),
                'precision': precision_with
            },
            'without_navigation': {
                'time': no_nav_time,
                'results_count': len(without_nav),
                'precision': precision_without
            },
            'improvement': {
                'time_saved': no_nav_time - nav_time,
                'precision_gain': precision_with - precision_without
            }
        }