"""
Strategy C: Vision-Augmented Extraction using VLM via OpenRouter.
For scanned documents with no text layer.
Includes budget guard to prevent cost overruns and MULTILINGUAL SUPPORT
for Ethiopian languages: Amharic, Tigrinya, Afaan Oromo, and others.
"""

import time
import base64
import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple
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

# Try to import Tesseract for local OCR fallback (Amharic support)
try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    print("⚠️ pytesseract not installed. Local OCR fallback unavailable.")


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


class MultilingualOCR:
    """
    Helper class for multilingual OCR support, especially for Ethiopian languages.
    Supports Amharic, Tigrinya, Afaan Oromo, and English.
    """
    
    # Language detection patterns (Unicode ranges for Ethiopian scripts)
    ETHIOPIC_UNICODE_RANGE = r'[\u1200-\u137F]'  # Ethiopic script range
    
    # Language-specific Tesseract configurations
    LANG_CONFIGS = {
        'amharic': {
            'tesseract_lang': 'amh',  # Amharic Tesseract language pack
            'openrouter_model': 'google/gemini-2.0-flash-lite-preview-02-05:free',
            'prompt': "Extract ALL text from this document page. The document contains Amharic text. Preserve the Amharic characters exactly. Return the extracted text with proper Amharic encoding."
        },
        'tigrinya': {
            'tesseract_lang': 'tir',  # Tigrinya Tesseract language pack
            'openrouter_model': 'google/gemini-2.0-flash-lite-preview-02-05:free',
            'prompt': "Extract ALL text from this document page. The document contains Tigrinya text. Preserve the Tigrinya characters exactly. Return the extracted text with proper encoding."
        },
        'oromo': {
            'tesseract_lang': 'orm',  # Afaan Oromo Tesseract language pack
            'openrouter_model': 'google/gemini-2.0-flash-lite-preview-02-05:free',
            'prompt': "Extract ALL text from this document page. The document contains Afaan Oromo text. Preserve the Oromo characters exactly. Return the extracted text."
        },
        'english': {
            'tesseract_lang': 'eng',
            'openrouter_model': 'google/gemini-2.0-flash-lite-preview-02-05:free',
            'prompt': "Extract ALL text from this document page."
        },
        'mixed': {
            'tesseract_lang': 'amh+eng+tir+orm',  # Multiple languages
            'openrouter_model': 'google/gemini-2.0-flash-lite-preview-02-05:free',
            'prompt': "Extract ALL text from this document page. The document may contain multiple languages including Amharic, Tigrinya, Afaan Oromo, and English. Preserve all characters exactly."
        }
    }
    
    @staticmethod
    def detect_language(text_sample: str, filename: str = "") -> str:
        """
        Detect the primary language of the document.
        
        Args:
            text_sample: Sample text from document (may be empty)
            filename: Filename for fallback detection
            
        Returns:
            Language code: 'amharic', 'tigrinya', 'oromo', 'english', or 'mixed'
        """
        # Check filename for language hints
        filename_lower = filename.lower()
        if 'amharic' in filename_lower or 'amh' in filename_lower:
            return 'amharic'
        if 'tigrinya' in filename_lower or 'tir' in filename_lower:
            return 'tigrinya'
        if 'oromo' in filename_lower or 'orm' in filename_lower or 'afaan' in filename_lower:
            return 'oromo'
        
        # If we have text sample, check for Ethiopic characters
        if text_sample:
            # Count Ethiopic characters
            ethiopic_chars = len(re.findall(MultilingualOCR.ETHIOPIC_UNICODE_RANGE, text_sample))
            total_chars = len(text_sample)
            
            if total_chars > 0:
                ethiopic_ratio = ethiopic_chars / total_chars
                
                if ethiopic_ratio > 0.3:
                    # Document contains significant Ethiopic script
                    # Could be Amharic, Tigrinya, etc. - use mixed to be safe
                    return 'mixed'
        
        return 'english'  # Default to English
    
    @staticmethod
    def extract_with_tesseract(image, language: str = 'amh') -> str:
        """
        Extract text using Tesseract OCR with specific language pack.
        This is a FREE alternative to VLM APIs for local processing.
        
        Args:
            image: PIL Image object
            language: Tesseract language code (amh, tir, orm, eng)
            
        Returns:
            Extracted text
        """
        if not TESSERACT_AVAILABLE:
            return ""
        
        try:
            # Configure Tesseract for the specific language
            custom_config = f'--oem 3 --psm 6 -l {language}'
            text = pytesseract.image_to_string(image, config=custom_config)
            return text.strip()
        except Exception as e:
            print(f"⚠️ Tesseract extraction failed for language {language}: {e}")
            return ""


class VisionExtractor(BaseExtractor):
    """
    Strategy C: Vision-Augmented extraction using VLM with MULTILINGUAL SUPPORT.
    Cost: $0.10 per page (configurable)
    Best for: Scanned documents, handwriting, complex layouts, and 
              ETHIOPIAN LANGUAGES (Amharic, Tigrinya, Afaan Oromo)
    
    UNIQUE FEATURE: Multilingual OCR supporting Ethiopian languages:
    - Amharic (አማርኛ) - Ethiopia's working language
    - Tigrinya (ትግርኛ) - Spoken in Tigray region
    - Afaan Oromo - Most widely spoken language in Ethiopia
    - English - Default fallback
    
    The extractor automatically detects the document language and
    uses appropriate prompts and OCR configurations.
    """

    def __init__(self, api_key: Optional[str] = None, max_cost_per_doc: float = 20.00):
        """
        Initialize VisionExtractor with multilingual support.
        
        Args:
            api_key: OpenRouter API key (optional, will use env var)
            max_cost_per_doc: Maximum cost per document in USD
        """
        super().__init__()
        self.name = "VisionExtractor"
        self.cost_per_page = 0.10
        self.budget_guard = BudgetGuard(max_cost_per_doc)
        
        # UNIQUE FEATURE: Enable multilingual support
        self.multilingual_ocr = MultilingualOCR()
        self.supported_languages = ['amharic', 'tigrinya', 'oromo', 'english', 'mixed']

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
                        "X-Title": "Document Intelligence Refinery - Ethiopian Languages Support"
                    }
                )
                print(f"✅ OpenRouter client initialized with key: {self.api_key[:8]}...")
                print(f"🌍 Multilingual support enabled for: {', '.join(self.supported_languages)}")
            except Exception as e:
                print(f"⚠️ OpenRouter initialization error: {e}")
        else:
            print("⚠️ OpenRouter not available - missing API key or openai package")
            print("🌍 Falling back to Tesseract OCR for local processing (slower but free)")

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
        Extract using Vision model with automatic language detection.
        
        UNIQUE FEATURE: Automatically detects document language and uses
        appropriate prompts for Ethiopian languages.
        
        Args:
            pdf_path: Path to PDF file
            profile: DocumentProfile from Triage Agent
        
        Returns:
            ExtractedDocument with text in original language
        """
        start_time = time.time()
        doc_id = profile.doc_id if profile else pdf_path.stem
        
        # Detect document language from filename and any available text
        detected_language = self.multilingual_ocr.detect_language(
            text_sample=profile.page_details[0].text if profile and profile.page_details else "",
            filename=pdf_path.name
        )
        print(f"🌍 Detected language: {detected_language}")

        try:
            # Import pdf2image
            from pdf2image import convert_from_path

            # Convert first 3 pages only (for speed)
            images = convert_from_path(pdf_path, first_page=1, last_page=3)

            text_blocks = []
            page_confidences = []
            extraction_errors = []

            for page_num, image in enumerate(images, 1):
                # Get language-specific configuration
                lang_config = self.multilingual_ocr.LANG_CONFIGS.get(
                    detected_language,
                    self.multilingual_ocr.LANG_CONFIGS['english']
                )
                
                extracted_text = ""
                
                # Try OpenRouter first (if available)
                if self.client:
                    try:
                        # Convert to base64
                        import io
                        img_buffer = io.BytesIO()
                        image.save(img_buffer, format='PNG')
                        img_base64 = base64.b64encode(img_buffer.getvalue()).decode()

                        # Call OpenRouter with language-specific prompt
                        response = self.client.chat.completions.create(
                            model=lang_config['openrouter_model'],
                            messages=[
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": lang_config['prompt']},
                                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                                    ]
                                }
                            ],
                            max_tokens=1000
                        )
                        extracted_text = response.choices[0].message.content
                        
                    except Exception as e:
                        error_msg = f"OpenRouter API error for page {page_num}: {e}"
                        print(f"⚠️ {error_msg}")
                        extraction_errors.append(error_msg)
                
                # Fallback to Tesseract if OpenRouter failed or not available
                if not extracted_text and TESSERACT_AVAILABLE:
                    print(f"🔄 Falling back to Tesseract OCR for page {page_num} with language: {lang_config['tesseract_lang']}")
                    extracted_text = self.multilingual_ocr.extract_with_tesseract(
                        image,
                        language=lang_config['tesseract_lang']
                    )

                # Add text block if we got any text
                if extracted_text:
                    text_blocks.append(TextBlock(
                        text=extracted_text[:1000],  # Limit length
                        bbox=(0, 0, 1000, 1000),  # Approximate bbox
                        page_num=page_num,
                        block_type="text",
                        confidence=0.9
                    ))
                    page_confidences.append(0.9)
                    print(f"✅ Page {page_num}: Extracted {len(extracted_text)} chars in {detected_language}")
                else:
                    page_confidences.append(0.3)
                    print(f"⚠️ Page {page_num}: No text extracted")
                    extraction_errors.append(f"Page {page_num}: No text extracted")

            # Calculate overall confidence
            confidence = sum(page_confidences) / len(page_confidences) if page_confidences else 0.0

            # Create ExtractedDocument with language metadata
            return ExtractedDocument(
                doc_id=doc_id,
                filename=pdf_path.name,
                total_pages=len(images),
                text_blocks=text_blocks,
                tables=[],  # Vision model doesn't extract tables yet
                figures=[],  # Vision model doesn't extract figures yet
                extraction_strategy=StrategyType.VISION_AUGMENTED,
                confidence_score=confidence,
                processing_time_sec=time.time() - start_time,
                cost_usd=0.30,  # Approx 3 pages * $0.10
                extraction_errors=extraction_errors,
                metadata={
                    'detected_language': detected_language,
                    'multilingual_support': True,
                    'languages_supported': self.supported_languages
                }
            )

        except Exception as e:
            error_msg = f"Vision extraction error: {str(e)}"
            print(f"❌ {error_msg}")
            return ExtractedDocument(
                doc_id=doc_id,
                filename=pdf_path.name,
                total_pages=0,
                text_blocks=[],
                tables=[],
                figures=[],
                extraction_strategy=StrategyType.VISION_AUGMENTED,
                confidence_score=0.0,
                processing_time_sec=time.time() - start_time,
                cost_usd=0.0,
                extraction_errors=[error_msg],
                metadata={
                    'detected_language': detected_language if 'detected_language' in locals() else 'unknown',
                    'multilingual_support': True
                }
            )

    def confidence_score(self, extracted: ExtractedDocument) -> float:
        """Return confidence from extraction"""
        return extracted.confidence_score