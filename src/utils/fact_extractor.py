"""
FactTable extractor for financial/numerical documents.
Extracts key-value pairs into SQLite for precise querying.
"""

import re
import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import hashlib

from ..models.provenance import Fact, BBox
from ..models.chunking import LDU


class FactExtractor:
    """
    Extracts structured facts from financial documents.
    Uses pattern matching and NLP to identify key-value pairs.
    """
    
    def __init__(self, db_path: str = ".refinery/facts.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
        
        # Financial patterns
        self.patterns = {
            'revenue': [
                r'revenue(?: was|:)?\s*[\$€£]?\s*([\d,\.]+)\s*(?:million|billion|M|B)?',
                r'total\s+revenue:?\s*[\$€£]?\s*([\d,\.]+)\s*(million|billion|M|B)',
                r'gross\s+revenue:?\s*[\$€£]?\s*([\d,\.]+)\s*(million|billion|M|B)',
            ],
            'profit': [
                r'(?:net|gross)\s+profit:?\s*[\$€£]?\s*([\d,\.]+)\s*(million|billion|M|B)',
                r'profit(?:\s+was)?:?\s*[\$€£]?\s*([\d,\.]+)\s*(million|billion|M|B)',
                r'earnings:?\s*[\$€£]?\s*([\d,\.]+)\s*(million|billion|M|B)',
            ],
            'expenses': [
                r'(?:total|operating)\s+expenses?:?\s*[\$€£]?\s*([\d,\.]+)\s*(million|billion|M|B)',
                r'expenditure:?\s*[\$€£]?\s*([\d,\.]+)\s*(million|billion|M|B)',
                r'costs?:?\s*[\$€£]?\s*([\d,\.]+)\s*(million|billion|M|B)',
            ],
            'date': [
                r'(?:fiscal|financial)\s+year\s+(?:ended|ending)?\s*(\d{4})',
                r'(?:Q[1-4]|quarter)\s*(?:\d{4})',
                r'(?:as of|for the year ended)\s+(\w+\s+\d{1,2},?\s*\d{4})',
                r'(\d{4})\s+(?:annual|yearly)\s+report',
            ],
            'growth': [
                r'(?:growth|increase)(?:\s+rate)?:?\s*([\d\.]+)%',
                r'(?:increased|grew)(?:\s+by)?\s*([\d\.]+)%',
                r'year-over-year.*?([\d\.]+)%',
            ],
            'percentage': [
                r'margin:?\s*([\d\.]+)%',
                r'rate:?\s*([\d\.]+)%',
                r'([\d\.]+)%\s*(?:of|share)',
            ]
        }
        
        # Unit multipliers
        self.units = {
            'million': 1_000_000,
            'billion': 1_000_000_000,
            'trillion': 1_000_000_000_000,
            'M': 1_000_000,
            'B': 1_000_000_000,
            'T': 1_000_000_000_000,
        }
    
    def _init_database(self):
        """Initialize SQLite database for facts"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Create facts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS facts (
                fact_id TEXT PRIMARY KEY,
                document_name TEXT,
                doc_id TEXT,
                fact_type TEXT,
                key TEXT,
                value TEXT,
                numeric_value REAL,
                page_number INTEGER,
                bbox TEXT,
                content_hash TEXT,
                confidence REAL,
                context TEXT,
                extracted_at TIMESTAMP
            )
        ''')
        
        # Create indices for fast querying
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_doc ON facts(document_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_type ON facts(fact_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_key ON facts(key)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_value ON facts(numeric_value) WHERE numeric_value IS NOT NULL')
        
        conn.commit()
        conn.close()
    
    def extract_from_chunks(self, chunks: List[LDU], doc_id: str, doc_name: str) -> List[Fact]:
        """
        Extract facts from document chunks.
        """
        facts = []
        
        for chunk in chunks:
            # Skip non-text chunks
            if chunk.chunk_type not in ['text', 'table']:
                continue
            
            # Extract facts from this chunk
            chunk_facts = self._extract_from_text(
                text=chunk.content,
                page_num=chunk.primary_page,
                bbox=chunk.bbox,
                doc_name=doc_name,
                doc_id=doc_id,
                context=chunk.parent_section
            )
            facts.extend(chunk_facts)
        
        # Store in database
        self._store_facts(facts)
        
        return facts
    
    def _extract_from_text(
        self,
        text: str,
        page_num: int,
        bbox: Optional[Tuple],
        doc_name: str,
        doc_id: str,
        context: Optional[str] = None
    ) -> List[Fact]:
        """
        Extract facts from a single text block.
        """
        facts = []
        text_lower = text.lower()
        
        for fact_type, patterns in self.patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    # Create fact
                    value = match.group(0)
                    
                    # Generate fact ID
                    fact_id = hashlib.md5(
                        f"{doc_id}:{page_num}:{fact_type}:{value}".encode()
                    ).hexdigest()[:16]
                    
                    # Create BBox if available
                    fact_bbox = None
                    if bbox:
                        fact_bbox = BBox(
                            x0=bbox[0], y0=bbox[1],
                            x1=bbox[2], y1=bbox[3],
                            page_num=page_num
                        )
                    
                    # Generate content hash
                    content_hash = hashlib.sha256(
                        f"{value}:{page_num}:{bbox}".encode()
                    ).hexdigest()[:16]
                    
                    # Determine key from pattern
                    key = fact_type
                    
                    # Try to extract numeric value for calculations
                    numeric_value = self._extract_numeric(value)
                    
                    fact = Fact(
                        fact_id=fact_id,
                        document_name=doc_name,
                        doc_id=doc_id,
                        fact_type=fact_type,
                        key=key,
                        value=value,
                        page_number=page_num,
                        bbox=fact_bbox,
                        content_hash=content_hash,
                        confidence=0.8,  # Base confidence
                        context=context
                    )
                    facts.append(fact)
        
        return facts
    
    def _extract_numeric(self, text: str) -> Optional[float]:
        """
        Extract numeric value from text, handling units.
        """
        # Extract number
        num_match = re.search(r'[\d,\.]+', text)
        if not num_match:
            return None
        
        num_str = num_match.group().replace(',', '')
        try:
            value = float(num_str)
        except ValueError:
            return None
        
        # Check for units
        text_lower = text.lower()
        for unit, multiplier in self.units.items():
            if unit in text_lower:
                value *= multiplier
                break
        
        return value
    
    def _store_facts(self, facts: List[Fact]):
        """
        Store facts in SQLite database.
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        for fact in facts:
            # Convert bbox to JSON if present
            bbox_json = json.dumps(fact.bbox.model_dump()) if fact.bbox else None
            
            # Extract numeric value
            numeric_value = self._extract_numeric(fact.value)
            
            cursor.execute('''
                INSERT OR REPLACE INTO facts 
                (fact_id, document_name, doc_id, fact_type, key, value, numeric_value,
                 page_number, bbox, content_hash, confidence, context, extracted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                fact.fact_id, fact.document_name, fact.doc_id, fact.fact_type,
                fact.key, fact.value, numeric_value,
                fact.page_number, bbox_json, fact.content_hash,
                fact.confidence, fact.context, fact.extracted_at
            ))
        
        conn.commit()
        conn.close()
    
    def query_facts(self, query: str, doc_id: Optional[str] = None) -> List[Dict]:
        """
        Query facts using natural language or SQL.
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Parse query for numeric comparisons
        numeric_query = self._parse_numeric_query(query)
        
        if numeric_query:
            # Handle numeric queries (e.g., "revenue > 100M")
            fact_type, op, value = numeric_query
            sql = f'''
                SELECT * FROM facts 
                WHERE fact_type = ? AND numeric_value IS NOT NULL
                AND numeric_value {op} ?
            '''
            params = [fact_type, value]
        else:
            # Text search
            sql = '''
                SELECT * FROM facts 
                WHERE key LIKE ? OR value LIKE ? OR fact_type LIKE ?
            '''
            params = [f'%{query}%', f'%{query}%', f'%{query}%']
        
        if doc_id:
            sql += ' AND doc_id = ?'
            params.append(doc_id)
        
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        
        # Convert to dict
        columns = [description[0] for description in cursor.description]
        results = [dict(zip(columns, row)) for row in rows]
        
        conn.close()
        return results
    def _parse_comparison(self, groups):
        """Parse comparison groups from regex match"""
        if len(groups) >= 4:
            fact_type, op, num_str, unit = groups[0], groups[1], groups[2], groups[3]
        else:
            fact_type, op, num_str = groups[0], groups[1], groups[2]
            unit = None
        return (fact_type, op, num_str, unit)
    
    def _parse_numeric_query(self, query: str) -> Optional[Tuple[str, str, float]]:
        """
        Parse queries like "revenue > 100M" into structured form.
        """
        # Pattern: [fact_type] [operator] [number][unit]
        patterns = [
            (r'(\w+)\s*(>|>=|<|<=|=)\s*([\d\.]+)\s*(million|billion|M|B)?', self._parse_comparison),
            (r'(\w+)\s*(?:greater than|more than)\s*([\d\.]+)\s*(million|billion|M|B)?', lambda m: (m[0], '>', m[1], m[2])),
            (r'(\w+)\s*(?:less than|under)\s*([\d\.]+)\s*(million|billion|M|B)?', lambda m: (m[0], '<', m[1], m[2])),
        ]
        
        for pattern, parser in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                groups = match.groups()
                fact_type, op, num_str, unit = parser(groups)
                
                try:
                    value = float(num_str)
                    if unit:
                        unit_lower = unit.lower()
                        if unit_lower in ['billion', 'b']:
                            value *= 1_000_000_000
                        elif unit_lower in ['million', 'm']:
                            value *= 1_000_000
                    return (fact_type.lower(), op, value)
                except:
                    return None
        
        return None
    
    def get_fact_summary(self, doc_id: str) -> Dict:
        """
        Get summary of facts for a document.
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT fact_type, COUNT(*) as count, 
                   AVG(confidence) as avg_confidence
            FROM facts 
            WHERE doc_id = ?
            GROUP BY fact_type
        ''', [doc_id])
        
        rows = cursor.fetchall()
        summary = {
            'doc_id': doc_id,
            'total_facts': sum(r[1] for r in rows),
            'by_type': {r[0]: {'count': r[1], 'avg_confidence': r[2]} for r in rows}
        }
        
        conn.close()
        return summary