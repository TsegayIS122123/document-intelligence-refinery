"""
Spatial hashing for provenance verification.
Same pattern as Week 1's content_hash - enables verification even when content shifts.
"""

import hashlib
import json
from typing import Tuple, Optional, Union
from pathlib import Path


class SpatialHasher:
    """
    Generates content hashes that include spatial information.
    This enables provenance verification even if document pages shift.
    """
    
    @staticmethod
    def generate_content_hash(
        text: str,
        page_num: int,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        context: Optional[str] = None
    ) -> str:
        """
        Generate a hash that combines content with spatial location.
        
        Args:
            text: The text content
            page_num: Page number
            bbox: Bounding box (x0, y0, x1, y1)
            context: Optional context (section title, etc.)
            
        Returns:
            16-character hash (first 16 of SHA-256)
        """
        # Normalize text (remove extra whitespace)
        normalized_text = ' '.join(text.split())
        
        # Create spatial signature
        spatial_parts = [str(page_num)]
        if bbox:
            # Round to 2 decimal places to handle minor variations
            rounded_bbox = [round(coord, 2) for coord in bbox]
            spatial_parts.extend([str(c) for c in rounded_bbox])
        
        spatial_signature = '|'.join(spatial_parts)
        
        # Combine with content and context
        hash_input = f"{normalized_text}|{spatial_signature}"
        if context:
            hash_input += f"|{context}"
        
        # Generate SHA-256 and take first 16 chars
        full_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        return full_hash[:16]
    
    @staticmethod
    def generate_chunk_hash(ldu_data: dict) -> str:
        """
        Generate hash for an LDU dictionary.
        Useful for batch operations.
        """
        # Sort keys for consistent hashing
        content = json.dumps(ldu_data, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    @staticmethod
    def verify_chunk(ldu: 'LDU', original_text: str, page_num: int, bbox: Tuple) -> bool:
        """
        Verify that an LDU's content matches its hash.
        """
        expected_hash = SpatialHasher.generate_content_hash(
            text=original_text,
            page_num=page_num,
            bbox=bbox,
            context=ldu.parent_section
        )
        return ldu.content_hash == expected_hash


class SpatialIndex:
    """
    Maintains a spatial index of chunks for fast lookup by location.
    """
    
    def __init__(self):
        self.by_page = {}  # page_num -> list of chunks
        self.by_region = {}  # region_id -> chunk
    
    def add_chunk(self, ldu: 'LDU'):
        """Add chunk to spatial index"""
        page = ldu.page_refs[0]  # Primary page
        if page not in self.by_page:
            self.by_page[page] = []
        self.by_page[page].append(ldu)
        
        # Index by region if bbox exists
        if ldu.bbox:
            region_id = f"p{page}_r{ldu.bbox[0]}_{ldu.bbox[1]}"
            self.by_region[region_id] = ldu
    
    def get_chunks_on_page(self, page_num: int) -> list:
        """Get all chunks on a specific page"""
        return self.by_page.get(page_num, [])
    
    def get_chunk_at_bbox(self, page_num: int, bbox: Tuple) -> Optional['LDU']:
        """Find chunk at specific location"""
        region_id = f"p{page_num}_r{bbox[0]}_{bbox[1]}"
        return self.by_region.get(region_id)