#!/usr/bin/env python
"""
Generate 3 example Q&A pairs per document class (12 total)
Each with full ProvenanceChain citations
"""

import json
from pathlib import Path
from src.agents.query_agent import QueryAgent
from src.utils.vector_store import VectorStore
from src.utils.fact_extractor import FactExtractor

# Define document classes and sample documents
DOC_CLASSES = {
    "Class A - Financial Reports": [
        "CBE ANNUAL REPORT 2023-24.pdf",
        "Annual_Report_JUNE-2023.pdf",
        "Annual_Report_JUNE-2022.pdf"
    ],
    "Class B - Audit Reports": [
        "Audit Report - 2023.pdf",
        "2018_Audited_Financial_Statement_Report.pdf",
        "2019_Audited_Financial_Statement_Report.pdf"
    ],
    "Class C - Technical Reports": [
        "fta_performance_survey_final_report_2022.pdf",
        "20191010_Pharmaceutical-Manufacturing-Opportunites-in-Ethiopia_VF.pdf",
        "Security_Vulnerability_Disclosure_Standard_Procedure_1.pdf"
    ],
    "Class D - Tax Reports": [
        "tax_expenditure_ethiopia_2021_22.pdf",
        "Consumer Price Index August 2025.pdf",
        "Consumer Price Index July 2025.pdf"
    ]
}

# Sample questions per class
QUESTIONS = {
    "Class A - Financial Reports": [
        "What was the total revenue in 2023?",
        "What is the net profit margin?",
        "How much did assets grow compared to last year?"
    ],
    "Class B - Audit Reports": [
        "What was the audit opinion?",
        "Were there any material weaknesses found?",
        "What is the auditor's name and firm?"
    ],
    "Class C - Technical Reports": [
        "What are the key findings of the assessment?",
        "What recommendations were made?",
        "What methodology was used in the study?"
    ],
    "Class D - Tax Reports": [
        "What was the total tax expenditure for 2021?",
        "How did import taxes change from 2019 to 2020?",
        "What categories have the highest tax expenditure?"
    ]
}

def generate_qa_examples():
    """Generate 3 Q&A examples per document class"""
    
    # Initialize components
    vector_store = VectorStore()
    fact_extractor = FactExtractor()
    agent = QueryAgent(vector_store, fact_extractor)
    
    output_dir = Path("qa_examples")
    output_dir.mkdir(exist_ok=True)
    
    all_examples = []
    
    for class_name, docs in DOC_CLASSES.items():
        print(f"\n📁 Processing {class_name}")
        class_questions = QUESTIONS[class_name]
        
        for doc_idx, doc_name in enumerate(docs[:3]):  # Take first 3 docs
            doc_path = Path("data/raw") / doc_name
            
            if not doc_path.exists():
                print(f"  ⚠️ Document not found: {doc_name}")
                continue
            
            print(f"  📄 {doc_name}")
            
            for q_idx, question in enumerate(class_questions):
                print(f"    ❓ Q{q_idx+1}: {question[:50]}...")
                
                # Query the document
                result = agent.query(question)
                
                # Create example with full provenance
                example = {
                    "class": class_name,
                    "document": doc_name,
                    "question": question,
                    "answer": result.synthesized_answer,
                    "confidence": result.confidence,
                    "verification_status": result.verification_status,
                    "sources": [
                        {
                            "document_name": s.document_name,
                            "page_number": s.page_number,
                            "bbox": {
                                "x0": s.bbox.x0,
                                "y0": s.bbox.y0,
                                "x1": s.bbox.x1,
                                "y1": s.bbox.y1,
                                "page_num": s.bbox.page_num
                            },
                            "content_hash": s.content_hash,
                            "extracted_text": s.extracted_text[:200] + "..." if len(s.extracted_text) > 200 else s.extracted_text
                        }
                        for s in result.sources
                    ],
                    "query_id": result.query_id,
                    "timestamp": result.query_time.isoformat()
                }
                
                all_examples.append(example)
                
                # Save individual example
                example_file = output_dir / f"{class_name.replace(' ', '_')}_{doc_idx+1}_q{q_idx+1}.json"
                with open(example_file, 'w') as f:
                    json.dump(example, f, indent=2, default=str)
    
    # Save all examples
    with open(output_dir / "all_qa_examples.json", 'w') as f:
        json.dump(all_examples, f, indent=2, default=str)
    
    print(f"\n✅ Generated {len(all_examples)} Q&A examples")
    print(f"   Saved to {output_dir}/")

if __name__ == "__main__":
    generate_qa_examples()