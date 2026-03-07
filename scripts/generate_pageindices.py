#!/usr/bin/env python
"""
Generate PageIndex trees for at least 12 documents (minimum 3 per class)
"""

from pathlib import Path
from src.agents.indexer import PageIndexBuilder
from src.models.chunking import LDU
import json

def generate_pageindices():
    """Generate PageIndex for 12+ documents"""
    
    builder = PageIndexBuilder(use_llm=True)  # Use LLM for summaries
    
    # Get all chunk files (you'll need to have these from Phase 3)
    chunk_files = list(Path(".refinery/chunks").glob("*.json"))[:12]
    
    if not chunk_files:
        print("❌ No chunk files found in .refinery/chunks/")
        print("Please run chunking first or create sample chunks")
        return
    
    print(f"📊 Found {len(chunk_files)} chunk files")
    
    for i, chunk_file in enumerate(chunk_files, 1):
        print(f"\n[{i}/{len(chunk_files)}] Processing: {chunk_file.name}")
        
        # Load chunks (you'll need to deserialize properly)
        with open(chunk_file, 'r') as f:
            data = json.load(f)
        
        # Convert to LDU objects (simplified - adjust based on your format)
        chunks = [LDU(**chunk) for chunk in data.get('chunks', [])]
        
        if not chunks:
            print(f"  ⚠️ No chunks found in {chunk_file.name}")
            continue
        
        # Build and save PageIndex
        doc_id = chunk_file.stem
        filename = data.get('filename', f"{doc_id}.pdf")
        
        pageindex = builder.build(
            chunks=chunks,
            doc_id=doc_id,
            filename=filename,
            save=True,
            output_dir=".refinery/pageindex"
        )
        
        print(f"  ✅ Saved to .refinery/pageindex/{doc_id}.json")
        print(f"     Sections: {len(pageindex.root_sections)}")

if __name__ == "__main__":
    generate_pageindices()