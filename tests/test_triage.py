"""
Unit tests for Triage Agent.
Uses your Phase 0 analysis as ground truth!
"""

import pytest
from pathlib import Path
from src.agents.triage import TriageAgent
from src.models.enums import OriginType, LayoutComplexity, DomainHint, StrategyType


class TestTriageAgent:
    """Test the Triage Agent against your Phase 0 findings"""
    
    @pytest.fixture
    def agent(self):
        return TriageAgent()
    
    @pytest.fixture
    def test_docs(self):
        """Map of documents and expected results from Phase 0"""
        base_path = Path("data/raw")
        return [
            {
                'path': base_path / "Audit Report - 2023.pdf",
                'expected': {
                    'origin': OriginType.SCANNED_IMAGE,
                    'origin_conf': 0.95,
                    'chars_per_page': 24.2,
                    'image_ratio': 0.803,
                    'strategy': StrategyType.VISION_AUGMENTED
                }
            },
            {
                'path': base_path / "fta_performance_survey_final_report_2022.pdf",
                'expected': {
                    'origin': OriginType.NATIVE_DIGITAL,
                    'origin_conf': 0.90,
                    'chars_per_page': 3646.4,
                    'image_ratio': 0.001,
                    'has_tables': True,
                    'strategy': StrategyType.LAYOUT_AWARE
                }
            },
            {
                'path': base_path / "tax_expenditure_ethiopia_2021_22.pdf",
                'expected': {
                    'origin': OriginType.NATIVE_DIGITAL,
                    'origin_conf': 0.90,
                    'chars_per_page': 1596.4,
                    'image_ratio': 0.009,
                    'strategy': StrategyType.LAYOUT_AWARE
                }
            },
            {
                'path': base_path / "CBE ANNUAL REPORT 2023-24.pdf",
                'expected': {
                    'origin': OriginType.MIXED,
                    'origin_conf': 0.60,
                    'chars_per_page': 947.2,
                    'image_ratio': 0.400,
                    'has_multi_column': True,
                    'strategy': StrategyType.LAYOUT_AWARE
                }
            }
        ]
    
    def test_origin_classification(self, agent, test_docs):
        """Test that origin classification matches Phase 0 findings"""
        for doc in test_docs:
            if not doc['path'].exists():
                pytest.skip(f"Document not found: {doc['path']}")
            
            profile = agent.analyze(str(doc['path']))
            
            # Check origin type
            assert profile.origin_type == doc['expected']['origin'], \
                f"{doc['path'].name}: Expected {doc['expected']['origin']}, got {profile.origin_type}"
            
            # Check character density (within 10% tolerance)
            expected_chars = doc['expected']['chars_per_page']
            actual_chars = profile.avg_chars_per_page
            tolerance = expected_chars * 0.1
            assert abs(actual_chars - expected_chars) < tolerance, \
                f"{doc['path'].name}: Expected ~{expected_chars} chars, got {actual_chars}"
    
    def test_strategy_recommendation(self, agent, test_docs):
        """Test that strategy recommendations match Phase 0"""
        for doc in test_docs:
            if not doc['path'].exists():
                pytest.skip(f"Document not found: {doc['path']}")
            
            profile = agent.analyze(str(doc['path']))
            
            # Check strategy recommendation
            assert profile.recommended_strategy == doc['expected']['strategy'], \
                f"{doc['path'].name}: Expected {doc['expected']['strategy']}, got {profile.recommended_strategy}"
    
    def test_image_ratio_detection(self, agent, test_docs):
        """Test image ratio detection accuracy"""
        for doc in test_docs:
            if 'image_ratio' not in doc['expected']:
                continue

            profile = agent.analyze(str(doc['path']))

            expected = doc['expected']['image_ratio']
            actual = profile.avg_image_ratio
            
            # Better tolerance: use both relative AND absolute tolerance
            if expected < 0.01:  # For very small numbers (like 0.001)
                # Use absolute tolerance
                tolerance = 0.001  # Allow up to 0.001 difference
            else:
                # Use relative tolerance for larger numbers
                tolerance = expected * 0.2
            
            assert abs(actual - expected) < tolerance, \
                f"{doc['path'].name}: Expected {expected} image ratio, got {actual}"
    
    def test_multi_column_detection(self, agent):
        """Test multi-column detection on Class A (which has multi-column)"""
        doc_path = Path("data/raw/CBE ANNUAL REPORT 2023-24.pdf")
        if not doc_path.exists():
            pytest.skip("CBE document not found")
        
        profile = agent.analyze(str(doc_path))
        assert profile.has_multi_column, "CBE report should be detected as multi-column"
    
    def test_table_detection(self, agent):
        """Test table detection on Class C (which has tables)"""
        doc_path = Path("data/raw/fta_performance_survey_final_report_2022.pdf")
        if not doc_path.exists():
            pytest.skip("FTA document not found")
        
        profile = agent.analyze(str(doc_path))
        assert profile.has_tables, "FTA report should have tables detected"
    
    def test_domain_classification(self, agent):
        """Test domain classification matches document type"""
        test_cases = [
            ("Audit Report - 2023.pdf", DomainHint.LEGAL),
            ("CBE ANNUAL REPORT 2023-24.pdf", DomainHint.FINANCIAL),
            ("tax_expenditure_ethiopia_2021_22.pdf", DomainHint.FINANCIAL),
            ("fta_performance_survey_final_report_2022.pdf", DomainHint.TECHNICAL)
        ]
        
        for filename, expected_domain in test_cases:
            doc_path = Path("data/raw") / filename
            if not doc_path.exists():
                continue
            
            profile = agent.analyze(str(doc_path))
            assert profile.domain_hint == expected_domain, \
                f"{filename}: Expected {expected_domain}, got {profile.domain_hint}"
    
    def test_profile_saving(self, agent, tmp_path):
        """Test that profiles save correctly"""
        doc_path = Path("data/raw/Audit Report - 2023.pdf")
        if not doc_path.exists():
            pytest.skip("Audit document not found")
        
        profile = agent.analyze(str(doc_path))
        saved_path = agent.save_profile(profile, str(tmp_path))
        
        assert saved_path.exists()
        assert saved_path.suffix == '.json'
        
        # Verify we can load it back
        import json
        with open(saved_path, 'r') as f:
            data = json.load(f)
            assert data['doc_id'] == profile.doc_id
            assert data['origin_type'] == profile.origin_type.value
    
    def test_edge_cases(self, agent):
        """Test edge cases"""
        # Non-existent file
        with pytest.raises(FileNotFoundError):
            agent.analyze("nonexistent.pdf")
        
        # Empty PDF? (if you have one)
        # TODO: Add test for empty/corrupted PDF