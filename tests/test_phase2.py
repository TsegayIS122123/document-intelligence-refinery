# test_phase2.py
from pathlib import Path
from src.agents.triage import TriageAgent
from src.strategies.fast_text import FastTextExtractor
from src.strategies.vision import VisionExtractor

# Test Strategy A on a digital doc
print("🔍 Testing FastTextExtractor on Class C...")
agent = TriageAgent()
profile = agent.analyze("data/raw/fta_performance_survey_final_report_2022.pdf")

extractor = FastTextExtractor()
result = extractor.extract(Path("data/raw/fta_performance_survey_final_report_2022.pdf"), profile)

print(f"Strategy: {result.extraction_strategy}")
print(f"Confidence: {result.confidence_score}")
print(f"Cost: ${result.cost_usd}")
print(f"Text blocks: {len(result.text_blocks)}")
print(f"Tables: {len(result.tables)}")
print("-" * 50)