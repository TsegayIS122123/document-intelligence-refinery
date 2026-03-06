"""
Unit tests for Audit Mode.
"""

import pytest
from src.queries.audit_mode import AuditMode
from src.utils.vector_store import VectorStore
from src.utils.fact_extractor import FactExtractor


class TestAuditMode:
    
    @pytest.fixture
    def vector_store(self):
        """Create a vector store with proper embeddings"""
        store = VectorStore(store_type="dict")
        
        # Add test chunks directly to vectors and metadata
        import numpy as np
        
        # Create a test chunk
        test_chunk = {
            'id': 'chunk1',
            'content': 'Revenue for 2023 was $45.2 million, a 7.4% increase from last year.',
            'doc_id': 'test_doc',
            'page_num': 42,
            'bbox': (10, 50, 600, 100),
            'content_hash': 'a1b2c3d4e5f6g7h8',
        }
        
        # Add to store
        store.metadata.append(test_chunk)
        
        # Create a deterministic embedding
        np.random.seed(42)
        embedding = np.random.randn(384).astype('float32')
        store.vectors.append(embedding)
        
        print(f"✅ Test vector store initialized with {len(store.vectors)} vectors")
        return store
    
    @pytest.fixture
    def fact_extractor(self, tmp_path):
        db_path = tmp_path / "test_facts.db"
        return FactExtractor(str(db_path))
    
    @pytest.fixture
    def audit_mode(self, vector_store, fact_extractor):
        """Create audit mode with properly configured vector store"""
        return AuditMode(vector_store, fact_extractor)
    
    def test_claim_verification(self, audit_mode):
        """Test claim verification"""
        claim = "Revenue was $45.2 million"
        
        # Mock the search to return results
        def mock_search(query, filter=None, top_k=5):
            return [{
                'content': 'Revenue for 2023 was $45.2 million, a 7.4% increase from last year.',
                'metadata': {
                    'doc_id': 'test_doc',
                    'page_num': 42,
                    'bbox': (10, 50, 600, 100),
                    'content_hash': 'a1b2c3d4e5f6g7h8'
                },
                'score': 0.95
            }]
        
        # Replace search method
        audit_mode.vector_store.search = mock_search
        
        result = audit_mode.verify_claim(claim, doc_id='test_doc')
        
        assert result.claim == claim
        assert len(result.sources) > 0
        assert result.verification_status in ['verified', 'partial']
        assert result.confidence > 0
    
    def test_unverifiable_claim(self, audit_mode):
        """Test unverifiable claim"""
        claim = "This claim does not exist anywhere"
        
        # Mock search to return empty results
        def mock_search(query, filter=None, top_k=5):
            return []
        
        audit_mode.vector_store.search = mock_search
        
        result = audit_mode.verify_claim(claim)
        
        assert result.verification_status == 'unverifiable'
        assert len(result.sources) == 0
        assert result.confidence == 0.0
    
    def test_batch_verification(self, audit_mode):
        """Test batch verification"""
        claims = [
            "Revenue was $45.2 million",
            "Nonexistent claim",
            "Operating expenses"
        ]
        
        # Mock search to return results for first claim only
        call_count = 0
        def mock_search(query, filter=None, top_k=5):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # First claim
                return [{
                    'content': 'Revenue for 2023 was $45.2 million',
                    'metadata': {
                        'doc_id': 'test_doc',
                        'page_num': 42,
                        'bbox': (10, 50, 600, 100),
                        'content_hash': 'a1b2c3d4e5f6g7h8'
                    },
                    'score': 0.95
                }]
            return []  # Other claims
        
        audit_mode.vector_store.search = mock_search
        
        results = audit_mode.batch_verify(claims, doc_id='test_doc')
        
        assert len(results) == 3
        assert results[0].verification_status in ['verified', 'partial']
        assert results[1].verification_status == 'unverifiable'
        assert results[2].verification_status == 'unverifiable'