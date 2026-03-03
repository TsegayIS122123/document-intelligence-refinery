#!/usr/bin/env python
"""
Phase 0: Document Science Primer
Analyze the 4 target documents to understand their characteristics
"""

import pdfplumber
import json
from pathlib import Path
import pandas as pd
from tabulate import tabulate
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns

class Phase0Analyzer:
    def __init__(self):
        self.data_dir = Path("data/raw")
        self.output_dir = Path("analysis/output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Map the 4 target documents exactly as specified in challenge
        self.target_docs = {
            "Class A - CBE Annual (2023-24)": self.data_dir / "CBE ANNUAL REPORT 2023-24.pdf",
            "Class B - DBE Audit (2023)": self.data_dir / "Audit Report - 2023.pdf",
            "Class C - FTA Report (2022)": self.data_dir / "fta_performance_survey_final_report_2022.pdf",
            "Class D - Tax Expenditure (2021-22)": self.data_dir / "tax_expenditure_ethiopia_2021_22.pdf"
        }
        
        self.results = {}
        
    def verify_files_exist(self):
        """Check all required files are present"""
        print("\n🔍 Verifying target documents:")
        all_exist = True
        for name, path in self.target_docs.items():
            exists = path.exists()
            status = "✅" if exists else "❌"
            print(f"  {status} {name}: {path.name}")
            if not exists:
                all_exist = False
        return all_exist
    
    def analyze_document(self, doc_name, pdf_path):
        """Comprehensive document analysis"""
        print(f"\n📊 Analyzing {doc_name}...")
        
        stats = {
            'doc_name': doc_name,
            'filename': pdf_path.name,
            'size_mb': round(pdf_path.stat().st_size / (1024*1024), 2),
            'total_pages': 0,
            'has_text_layer': False,
            'avg_chars_per_page': 0,
            'avg_image_ratio': 0,
            'has_tables': False,
            'has_multi_column': False,
            'page_details': [],
            'extraction_strategy': None,
            'confidence': None
        }
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                stats['total_pages'] = len(pdf.pages)
                
                # Analyze first 5 pages (or all if less)
                pages_to_analyze = min(5, len(pdf.pages))
                text_pages = 0
                total_chars = 0
                total_image_ratio = 0
                
                for page_num in range(pages_to_analyze):
                    page = pdf.pages[page_num]
                    
                    # Extract text
                    text = page.extract_text() or ""
                    char_count = len(text)
                    if char_count > 50:
                        text_pages += 1
                    
                    # Calculate image area
                    images = page.images
                    page_area = page.width * page.height if page.width and page.height else 1
                    image_area = sum(img['height'] * img['width'] for img in images) if images else 0
                    image_ratio = image_area / page_area if page_area > 0 else 0
                    
                    # Detect tables
                    tables = page.find_tables()
                    if tables:
                        stats['has_tables'] = True
                    
                    # Multi-column heuristic
                    words = page.extract_words()
                    if len(words) > 10:
                        x_positions = [w['x0'] for w in words]
                        # If words cluster in different x-ranges, likely multi-column
                        x_clusters = len(set(round(x/50) for x in x_positions))
                        if x_clusters > 2:
                            stats['has_multi_column'] = True
                    
                    # Page details
                    page_detail = {
                        'page': page_num + 1,
                        'char_count': char_count,
                        'image_count': len(images),
                        'image_ratio': round(image_ratio, 3),
                        'has_text': char_count > 50,
                        'table_count': len(tables),
                        'word_count': len(words)
                    }
                    stats['page_details'].append(page_detail)
                    
                    total_chars += char_count
                    total_image_ratio += image_ratio
                
                # Calculate averages
                stats['pages_analyzed'] = pages_to_analyze
                stats['avg_chars_per_page'] = total_chars / pages_to_analyze
                stats['avg_image_ratio'] = total_image_ratio / pages_to_analyze
                stats['has_text_layer'] = text_pages > 0
                
                # Determine document type and strategy
                if stats['avg_chars_per_page'] > 100 and stats['avg_image_ratio'] < 0.3:
                    stats['document_type'] = 'NATIVE_DIGITAL'
                    stats['confidence'] = 'HIGH'
                    if stats['has_multi_column'] or stats['has_tables']:
                        stats['extraction_strategy'] = 'Strategy B: Layout-Aware'
                        stats['reason'] = 'Complex layout needs structure preservation'
                    else:
                        stats['extraction_strategy'] = 'Strategy A: Fast Text'
                        stats['reason'] = 'Simple digital document'
                        
                elif stats['avg_chars_per_page'] < 50 and stats['avg_image_ratio'] > 0.5:
                    stats['document_type'] = 'SCANNED_IMAGE'
                    stats['confidence'] = 'HIGH'
                    stats['extraction_strategy'] = 'Strategy C: Vision-Augmented'
                    stats['reason'] = 'Scanned document requires vision model'
                    
                else:
                    stats['document_type'] = 'MIXED'
                    stats['confidence'] = 'MEDIUM'
                    stats['extraction_strategy'] = 'Strategy B: Layout-Aware'
                    stats['reason'] = 'Mixed content needs layout-aware extraction'
                
        except Exception as e:
            stats['error'] = str(e)
            print(f"  ❌ Error: {e}")
        
        return stats
    
    def run_analysis(self):
        """Analyze all target documents"""
        if not self.verify_files_exist():
            print("\n❌ Missing required documents. Please ensure all 4 files are in data/raw/")
            return
        
        for doc_name, pdf_path in self.target_docs.items():
            self.results[doc_name] = self.analyze_document(doc_name, pdf_path)
        
        self.save_results()
        self.print_summary()
        self.create_visualizations()
    
    def save_results(self):
        """Save analysis results"""
        # Save as JSON
        with open(self.output_dir / "phase0_analysis.json", 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        # Create comparison table with ASCII-safe characters
        comparison = []
        for doc_name, stats in self.results.items():
            comparison.append({
                'Document': doc_name,
                'Type': stats.get('document_type', 'UNKNOWN'),
                'Pages': stats['total_pages'],
                'Avg Chars/Page': round(stats['avg_chars_per_page'], 1),
                'Image Ratio': round(stats['avg_image_ratio'], 3),
                'Has Tables': '[X]' if stats.get('has_tables') else '[ ]',  # Changed from ✅/❌
                'Multi-col': '[X]' if stats.get('has_multi_column') else '[ ]',  # Changed from ✅/❌
                'Strategy': stats.get('extraction_strategy', 'TBD'),
                'Confidence': stats.get('confidence', 'LOW')
            })
        
        df = pd.DataFrame(comparison)
        df.to_csv(self.output_dir / "comparison.csv", index=False, encoding='utf-8')
        
        # Save as markdown with UTF-8 encoding
        with open(self.output_dir / "comparison_table.md", 'w', encoding='utf-8') as f:
            f.write("# Phase 0: Document Analysis Results\n\n")
            f.write(f"*Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
            f.write(tabulate(comparison, headers="keys", tablefmt="github"))
    
    def print_summary(self):
        """Print human-readable summary"""
        print("\n" + "="*90)
        print("PHASE 0: DOCUMENT SCIENCE PRIMER - ANALYSIS RESULTS")
        print("="*90)
        
        for doc_name, stats in self.results.items():
            print(f"\n{doc_name}")
            print(f"   File: {stats.get('filename', 'N/A')} ({stats.get('size_mb', 0)} MB)")
            print(f"   Type: {stats.get('document_type', 'UNKNOWN')} ({stats.get('confidence', 'LOW')} confidence)")
            print(f"   Pages: {stats['total_pages']} (analyzed first {stats.get('pages_analyzed', 0)})")
            print(f"   Avg Characters/Page: {stats['avg_chars_per_page']:.1f}")
            print(f"   Avg Image Ratio: {stats['avg_image_ratio']:.3f}")
            print(f"   Tables Detected: {'[X]' if stats.get('has_tables') else '[ ]'}")
            print(f"   Multi-column Layout: {'[X]' if stats.get('has_multi_column') else '[ ]'}")
            print(f"   Recommended Strategy: {stats.get('extraction_strategy', 'TBD')}")
            print(f"   Reason: {stats.get('reason', 'N/A')}")
    
    def create_visualizations(self):
        """Create visualizations for DOMAIN_NOTES"""
        try:
            # Character density bar chart
            docs = list(self.results.keys())
            chars = [stats['avg_chars_per_page'] for stats in self.results.values()]
            
            plt.figure(figsize=(10, 6))
            colors = ['#2ecc71' if c > 100 else '#e74c3c' for c in chars]
            bars = plt.bar(range(len(docs)), chars, color=colors)
            plt.axhline(y=100, color='r', linestyle='--', label='Digital Threshold (100 chars)')
            plt.axhline(y=50, color='orange', linestyle='--', label='Scanned Threshold (50 chars)')
            plt.xlabel('Document')
            plt.ylabel('Average Characters per Page')
            plt.title('Character Density by Document Class')
            plt.xticks(range(len(docs)), [d.split(' - ')[0] for d in docs], rotation=45)
            plt.legend()
            plt.tight_layout()
            plt.savefig(self.output_dir / 'char_density.png', dpi=150)
            plt.close()
            
            print("\n✅ Visualizations saved to analysis/output/")
        except Exception as e:
            print(f"⚠️ Could not create visualizations: {e}")

if __name__ == "__main__":
    analyzer = Phase0Analyzer()
    analyzer.run_analysis()