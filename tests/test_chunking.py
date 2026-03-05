"""
Unit tests for chunking engine and rules.
"""

import pytest
from pathlib import Path
from src.agents.chunker import ChunkingEngine, ChunkValidator
from src.models.extraction import ExtractedDocument, TextBlock, Table, Figure
from src.models.chunking import LDU, ChunkType


class TestChunkingRules:
    
    @pytest.fixture
    def engine(self):
        return ChunkingEngine(max_tokens=512)
    
    @pytest.fixture
    def sample_table(self):
        return Table(
            headers=['Year', 'Revenue', 'Growth'],
            rows=[['2023', '45.2M', '7.4%'], ['2022', '42.1M', '5.2%']],
            bbox=(10, 10, 500, 100),
            page_num=1,
            caption='Annual Revenue'
        )
    
    def test_rule_1_no_table_split(self, engine, sample_table):
        """Test that tables are never split"""
        extraction = ExtractedDocument(
            doc_id='test',
            filename='test.pdf',
            total_pages=1,
            tables=[sample_table],
            text_blocks=[],
            figures=[],
            extraction_strategy='layout_aware',
            confidence_score=0.9,
            processing_time_sec=1.0,
            cost_usd=0.01
        )
        
        result = engine.chunk(extraction)
        
        # Check table is single chunk
        table_chunks = [c for c in result.chunks if c.chunk_type == ChunkType.TABLE]
        assert len(table_chunks) == 1
        
        # Verify no rule violations
        assert 'RULE_001' not in str(result.rule_violations)
    
    def test_rule_2_figure_caption_linked(self, engine):
        """Test that figure captions are stored as metadata"""
        figure = Figure(
            caption='Test Figure',
            bbox=(10, 10, 500, 100),
            page_num=1
        )
        
        extraction = ExtractedDocument(
            doc_id='test',
            filename='test.pdf',
            total_pages=1,
            tables=[],
            text_blocks=[],
            figures=[figure],
            extraction_strategy='layout_aware',
            confidence_score=0.9,
            processing_time_sec=1.0,
            cost_usd=0.01
        )
        
        result = engine.chunk(extraction)
        
        # Check figure has caption in metadata
        figure_chunks = [c for c in result.chunks if c.chunk_type == ChunkType.FIGURE]
        assert len(figure_chunks) == 1
        assert 'caption' in figure_chunks[0].metadata
        assert figure_chunks[0].metadata['caption'] == 'Test Figure'
    
    def test_rule_3_list_preservation(self, engine):
        """Test that lists are kept together"""
        list_items = [
            TextBlock(text='1. First item', bbox=(10, 10, 500, 20), page_num=1),
            TextBlock(text='2. Second item', bbox=(10, 30, 500, 20), page_num=1),
            TextBlock(text='3. Third item', bbox=(10, 50, 500, 20), page_num=1),
        ]
        
        extraction = ExtractedDocument(
            doc_id='test',
            filename='test.pdf',
            total_pages=1,
            tables=[],
            text_blocks=list_items,
            figures=[],
            extraction_strategy='fast_text',
            confidence_score=0.9,
            processing_time_sec=1.0,
            cost_usd=0.001
        )
        
        result = engine.chunk(extraction)
        
        # Check list items were merged
        list_chunks = [c for c in result.chunks if c.chunk_type == ChunkType.LIST]
        assert len(list_chunks) >= 1
        
        # If merged, should have all items
        if list_chunks and list_chunks[0].metadata.get('merged'):
            content = list_chunks[0].content
            assert 'First item' in content
            assert 'Second item' in content
            assert 'Third item' in content
    
    def test_rule_4_section_hierarchy(self, engine):
        """Test that chunks have parent section metadata"""
        # Create hierarchy: Section 1 > Section 1.1
        blocks = [
            TextBlock(text='1. Introduction', bbox=(10, 10, 500, 20), page_num=1),
            TextBlock(text='Some intro text', bbox=(10, 30, 500, 50), page_num=1),
            TextBlock(text='1.1 Background', bbox=(10, 80, 500, 20), page_num=1),
            TextBlock(text='Background details', bbox=(10, 100, 500, 50), page_num=1),
        ]
        
        extraction = ExtractedDocument(
            doc_id='test',
            filename='test.pdf',
            total_pages=1,
            tables=[],
            text_blocks=blocks,
            figures=[],
            extraction_strategy='fast_text',
            confidence_score=0.9,
            processing_time_sec=1.0,
            cost_usd=0.001
        )
        
        result = engine.chunk(extraction)
        
        # Find text chunks
        text_chunks = [c for c in result.chunks if c.chunk_type == ChunkType.TEXT]
        
        # Check they have parent sections
        for chunk in text_chunks:
            assert chunk.parent_section is not None
            assert chunk.section_depth > 0
    
    def test_rule_5_cross_reference_resolved(self, engine):
        """Test that cross-references are resolved"""
        # Create a chunk with reference to table
        text_with_ref = "As shown in Table 1, revenue grew significantly."
        
        blocks = [
            TextBlock(text=text_with_ref, bbox=(10, 10, 500, 50), page_num=1),
        ]
        
        tables = [
            Table(
                headers=['Year', 'Revenue'],
                rows=[['2023', '45.2M']],
                bbox=(10, 100, 500, 50),
                page_num=2
            )
        ]
        
        extraction = ExtractedDocument(
            doc_id='test',
            filename='test.pdf',
            total_pages=2,
            tables=tables,
            text_blocks=blocks,
            figures=[],
            extraction_strategy='layout_aware',
            confidence_score=0.9,
            processing_time_sec=1.0,
            cost_usd=0.01
        )
        
        result = engine.chunk(extraction)
        
        # Find the text chunk
        text_chunk = next(c for c in result.chunks if c.chunk_type == ChunkType.TEXT)
        
        # Check cross-references were resolved
        assert len(text_chunk.cross_references) > 0
        
        # Check relations were created
        assert len(result.relations) > 0
        ref_relations = [r for r in result.relations 
                        if r.relationship_type.value == 'cross_reference']
        assert len(ref_relations) > 0
    
    def test_content_hash_validation(self, engine):
        """Test that content hashes are generated and validated"""
        block = TextBlock(text='Test content', bbox=(10, 10, 500, 20), page_num=1)
        
        extraction = ExtractedDocument(
            doc_id='test',
            filename='test.pdf',
            total_pages=1,
            tables=[],
            text_blocks=[block],
            figures=[],
            extraction_strategy='fast_text',
            confidence_score=0.9,
            processing_time_sec=1.0,
            cost_usd=0.001
        )
        
        result = engine.chunk(extraction)
        
        # Check hash exists
        chunk = result.chunks[0]
        assert chunk.content_hash is not None
        assert len(chunk.content_hash) == 16
        
        # Verify hash matches content
        from src.utils.hashing import SpatialHasher
        expected = SpatialHasher.generate_content_hash(
            text=chunk.content,
            page_num=chunk.primary_page,
            bbox=chunk.bbox,
            context=chunk.parent_section
        )
        assert chunk.content_hash == expected