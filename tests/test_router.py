# tests/test_router.py
from pathlib import Path
from src.agents.triage import TriageAgent
from src.agents.extractor import ExtractionRouter

# Initialize
agent = TriageAgent()
router = ExtractionRouter()

# Test on all 4 documents
docs = [
    "data/raw/Audit Report - 2023.pdf",
    "data/raw/fta_performance_survey_final_report_2022.pdf",
    "data/raw/tax_expenditure_ethiopia_2021_22.pdf",
    "data/raw/CBE ANNUAL REPORT 2023-24.pdf"
]

for doc_path in docs:
    print(f"\n{'='*60}")
    print(f"Processing: {doc_path}")
    
    try:
        # Get profile
        profile = agent.analyze(doc_path)
        print(f"Triage says: {profile.recommended_strategy.value} (confidence: {profile.profile_confidence.value})")
        
        # Extract with router
        result = router.extract(Path(doc_path), profile)
        
        if result:
            print(f"✅ Final strategy used: {result.extraction_strategy}")
            print(f"   Confidence: {result.confidence_score:.1%}")
            print(f"   Cost: ${result.cost_usd:.4f}")
            print(f"   Tables found: {len(result.tables)}")
        else:
            print(f"❌ Extraction failed - result is None")
            
    except Exception as e:
        print(f"❌ Error: {e}")