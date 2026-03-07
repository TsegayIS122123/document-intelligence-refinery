"""
Demo script showing Amharic OCR capability
"""

from pathlib import Path
from src.strategies.vision import VisionExtractor

# Initialize with multilingual support
extractor = VisionExtractor(max_cost_per_doc=20.00)

# Process an Amharic document (example)
result = extractor.extract(Path("data/raw/amharic_report.pdf"))

print(f"🌍 Detected language: {result.metadata.get('detected_language')}")
print(f"📝 Extracted text sample: {result.text_blocks[0].text[:200] if result.text_blocks else 'No text'}")