#!/usr/bin/env python
"""
Compare Docling extraction quality vs pdfplumber on the 4 target documents
"""

import pdfplumber
from docling.document_converter import DocumentConverter
import json
from pathlib import Path
import time
from datetime import datetime

class DoclingComparator:
    def __init__(self):
        self.data_dir = Path("data/raw")
        self.output_dir = Path("analysis/output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.target_docs = {
            "Class A - CBE Annual": self.data_dir / "CBE ANNUAL REPORT 2023-24.pdf",
            "Class B - DBE Audit": self.data_dir / "Audit Report - 2023.pdf",
            "Class C - FTA Report": self.data_dir / "fta_performance_survey_final_report_2022.pdf",
            "Class D - Tax Report": self.data_dir / "tax_expenditure_ethiopia_2021_22.pdf"
        }
        
        # Initialize Docling converter
        try:
            self.converter = DocumentConverter()
            self.docling_available = True
        except Exception as e:
            print(f"⚠️ Docling not available: {e}")
            self.docling_available = False
        
        self.results = {}
    
    def extract_with_pdfplumber(self, pdf_path):
        """Extract using pdfplumber"""
        start = time.time()
        result = {
            'method': 'pdfplumber',
            'success': False,
            'text_length': 0,
            'tables_found': 0,
            'pages_processed': 0,
            'time_seconds': 0,
            'sample_text': ''
        }
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                pages = min(3, len(pdf.pages))
                result['pages_processed'] = pages
                
                for i in range(pages):
                    page = pdf.pages[i]
                    text = page.extract_text() or ""
                    tables = page.find_tables()
                    
                    result['text_length'] += len(text)
                    result['tables_found'] += len(tables)
                    
                    if i == 0 and text:
                        result['sample_text'] = text[:200] + "..."
                
                result['success'] = True
                
        except Exception as e:
            result['error'] = str(e)
        
        result['time_seconds'] = round(time.time() - start, 2)
        return result
    
    def extract_with_docling(self, pdf_path):
        """Extract using Docling (limited to first 10 pages)"""
        if not self.docling_available:
            return {'method': 'docling', 'success': False, 'error': 'Docling not installed'}
        
        start = time.time()
        result = {
            'method': 'docling',
            'success': False,
            'text_length': 0,
            'tables_found': 0,
            'figures_found': 0,
            'time_seconds': 0,
            'pages_processed': 0
        }
        
        try:
            # Create converter with memory limits
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption
            
            # Set memory limits
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = True
            pipeline_options.do_table_structure = True
            pipeline_options.table_structure_options.do_cell_matching = True
            
            # Limit pages to first 10
            converter = DocumentConverter(
                format_options=PdfFormatOption(pipeline_options=pipeline_options)
            )
            
            # Convert only first 10 pages
            doc_result = converter.convert(pdf_path, max_num_pages=10)
            doc = doc_result.document
            result['pages_processed'] = min(10, len(doc.pages)) if hasattr(doc, 'pages') else 0
            
            # Count elements
            result['tables_found'] = len(doc.tables) if hasattr(doc, 'tables') else 0
            result['figures_found'] = len(doc.pictures) if hasattr(doc, 'pictures') else 0
            result['success'] = True
            
            # Get text sample
            if hasattr(doc, 'texts') and doc.texts:
                result['sample_text'] = str(doc.texts[0])[:200] + "..."
                result['text_length'] = sum(len(str(t)) for t in doc.texts[:10])
                
        except Exception as e:
            result['error'] = str(e)
            print(f"   ⚠️ Docling error (normal for large PDFs): {str(e)[:100]}")
        
        result['time_seconds'] = round(time.time() - start, 2)
        return result
    
    def run_comparison(self):
        """Compare both methods on all documents"""
        print("\n" + "="*80)
        print("📊 DOCLING vs PDFPLUMBER COMPARISON")
        print("="*80)
        
        for doc_name, pdf_path in self.target_docs.items():
            if not pdf_path.exists():
                print(f"\n⚠️ {doc_name}: File not found - {pdf_path.name}")
                continue
            
            print(f"\n📄 {doc_name}")
            
            pdf_result = self.extract_with_pdfplumber(pdf_path)
            doc_result = self.extract_with_docling(pdf_path)
            
            self.results[doc_name] = {
                'pdfplumber': pdf_result,
                'docling': doc_result
            }
            
            # Print comparison
            print(f"   pdfplumber: {pdf_result.get('text_length', 0)} chars, "
                  f"{pdf_result.get('tables_found', 0)} tables, {pdf_result.get('time_seconds', 0)}s")
            print(f"   Docling:    {doc_result.get('text_length', 0)} chars, "
                  f"{doc_result.get('tables_found', 0)} tables, {doc_result.get('time_seconds', 0)}s")
            
            # Winner determination
            if doc_result.get('tables_found', 0) > pdf_result.get('tables_found', 0):
                print(f"   ✅ Docling better for table extraction")
            elif pdf_result.get('success') and not doc_result.get('success'):
                print(f"   ✅ pdfplumber works when Docling fails")
            else:
                print(f"   ⚖️ Similar performance")
        
        # Save results
        with open(self.output_dir / "docling_comparison.json", 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        print(f"\n✅ Results saved to {self.output_dir / 'docling_comparison.json'}")

if __name__ == "__main__":
    comparator = DoclingComparator()
    comparator.run_comparison()