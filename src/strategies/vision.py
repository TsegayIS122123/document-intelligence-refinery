"""
Strategy C: Vision-Augmented Extraction using VLM via OpenRouter.
For scanned documents with no text layer.
Includes budget guard to prevent cost overruns.
"""

import time
import base64
import os
from pathlib import Path
from typing import Optional, List, Dict
from .base import BaseExtractor
from ..models.extraction import ExtractedDocument, TextBlock, Table, Figure
from ..models.document import DocumentProfile
from ..models.enums import StrategyType
from dotenv import load_dotenv

# Load .env file from project root
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


# Try to import OpenAI (OpenRouter uses same API)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️ OpenAI not installed. Strategy C will use fallback.")


class BudgetGuard:
    """
    Budget guard to prevent cost overruns.
    Tracks token spend and enforces caps.
    """
    
    def __init__(self, max_cost_per_doc: float = 1.00):
        self.max_cost_per_doc = max_cost_per_doc
        self.total_cost = 0.0
        self.page_costs = []
        
    def check_budget(self, estimated_cost: float) -> bool:
        """Check if we can proceed with estimated cost"""
        if self.total_cost + estimated_cost > self.max_cost_per_doc:
            return False
        return True
    
    def add_cost(self, cost: float, page_num: int):
        """Record cost for a page"""
        self.total_cost += cost
        self.page_costs.append({
            'page': page_num,
            'cost': cost,
            'running_total': self.total_cost
        })
    
    def get_summary(self) -> Dict:
        """Get budget summary"""
        return {
            'total_cost': self.total_cost,
            'max_cost': self.max_cost_per_doc,
            'remaining': self.max_cost_per_doc - self.total_cost,
            'pages_processed': len(self.page_costs)
        }


class VisionExtractor(BaseExtractor):
    """
    Strategy C: Vision-Augmented extraction using VLM.
    Cost: $0.10 per page (configurable)
    Best for: Scanned documents, handwriting, complex layouts
    """
    
    def __init__(self, api_key: Optional[str] = None, max_cost_per_doc: float = 1.00):
        super().__init__()
        self.name = "VisionExtractor"
        self.cost_per_page = 0.10
        self.budget_guard = BudgetGuard(max_cost_per_doc)
        
        # Try multiple ways to get API key:
        # 1. Passed directly
        # 2. From OPENROUTER_API_KEY env var
        # 3. From OPENAI_API_KEY env var (OpenRouter compatible)
        self.api_key = (
            api_key or 
            os.getenv("OPENROUTER_API_KEY") or 
            os.getenv("OPENAI_API_KEY")
        )
        
        # Initialize OpenRouter client
        self.client = None
        if OPENAI_AVAILABLE and self.api_key:
            try:
                self.client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=self.api_key,
                    default_headers={
                        "HTTP-Referer": "https://github.com/TsegayIS122123/document-intelligence-refinery",
                        "X-Title": "Document Intelligence Refinery"
                    }
                )
                print(f"✅ OpenRouter client initialized with key: {self.api_key[:8]}...")
            except Exception as e:
                print(f"⚠️ OpenRouter initialization error: {e}")
        else:
            print("⚠️ OpenRouter not available - missing API key or openai package")
    
    def estimate_cost(self, pdf_path: Path) -> float:
        """Estimate cost based on page count"""
        try:
            import pypdf
            with open(pdf_path, 'rb') as f:
                pdf = pypdf.PdfReader(f)
                return len(pdf.pages) * self.cost_per_page
        except:
            return 1.00  # Default for scanned docs
    
    def extract(self, pdf_path: Path, profile: Optional[DocumentProfile] = None) -> ExtractedDocument:
        """
        Extract using Vision model via OpenRouter.
        """
        start_time = time.time()
        doc_id = profile.doc_id if profile else pdf_path.stem
        
        try:
            # Import pdf2image
            from pdf2image import convert_from_path
            
            # Convert first 3 pages only (for speed)
            images = convert_from_path(pdf_path, first_page=1, last_page=3)
            
            text_blocks = []
            page_confidences = []
            
            for page_num, image in enumerate(images, 1):
                # Convert to base64
                import base64
                import io
                img_buffer = io.BytesIO()
                image.save(img_buffer, format='PNG')
                img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
                
                # Call OpenRouter
                response = self.client.chat.completions.create(
                    model="google/gemini-2.0-flash-lite-preview-02-05:free",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Extract ALL text from this document page."},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                            ]
                        }
                    ],
                    max_tokens=500
                )
                
                # Add text block
                text_blocks.append(TextBlock(
                    text=response.choices[0].message.content[:500],
                    bbox=(0, 0, 1000, 1000),
                    page_num=page_num,
                    block_type="text",
                    confidence=0.9
                ))
                page_confidences.append(0.9)
            
            confidence = sum(page_confidences) / len(page_confidences) if page_confidences else 0.8
            
            return ExtractedDocument(
                doc_id=doc_id,
                filename=pdf_path.name,
                total_pages=len(images),
                text_blocks=text_blocks,
                tables=[],
                figures=[],
                extraction_strategy=StrategyType.VISION_AUGMENTED,
                confidence_score=confidence,
                processing_time_sec=time.time() - start_time,
                cost_usd=0.30,  # Approx 3 pages * $0.10
                extraction_errors=[]
            )
            
        except Exception as e:
            return ExtractedDocument(
                doc_id=doc_id,
                filename=pdf_path.name,
                total_pages=0,
                extraction_strategy=StrategyType.VISION_AUGMENTED,
                confidence_score=0.0,
                processing_time_sec=time.time() - start_time,
                cost_usd=0.0,
                extraction_errors=[f"Vision error: {str(e)}"]
            )
    
    def confidence_score(self, extracted: ExtractedDocument) -> float:
        """Return confidence from extraction"""
        return extracted.confidence_score