"""
SQLite storage for facts and query results.
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, date


class DateTimeEncoder(json.JSONEncoder):
    """
    Custom JSON encoder that handles datetime objects.
    Converts datetime to ISO format string for JSON serialization.
    """
    def default(self, obj: Any) -> Any:
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


class SQLiteStore:
    """
    SQLite database for storing facts and query history.
    """
    
    def __init__(self, db_path: str = ".refinery/refinery.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Query history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS query_history (
                query_id TEXT PRIMARY KEY,
                query TEXT,
                timestamp TIMESTAMP,
                response TEXT,
                confidence REAL,
                verification_status TEXT,
                source_count INTEGER,
                processing_time REAL
            )
        ''')
        
        # Document index table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                filename TEXT,
                file_path TEXT,
                total_pages INTEGER,
                processed_at TIMESTAMP,
                chunk_count INTEGER,
                fact_count INTEGER
            )
        ''')
        
        # Create indices
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_query_time ON query_history(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_doc_processed ON documents(processed_at)')
        
        conn.commit()
        conn.close()
    
    def save_query(self, query_id: str, query: str, response: Dict, 
                   processing_time: float):
        """
        Save query to history with proper datetime serialization.
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Convert response to JSON with custom encoder for datetime objects
        response_json = json.dumps(response, cls=DateTimeEncoder)
        
        cursor.execute('''
            INSERT OR REPLACE INTO query_history
            (query_id, query, timestamp, response, confidence, 
             verification_status, source_count, processing_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            query_id,
            query,
            datetime.now(),
            response_json,
            response.get('confidence', 0),
            response.get('verification_status', 'unknown'),
            len(response.get('sources', [])),
            processing_time
        ))
        
        conn.commit()
        conn.close()
    
    def get_query_history(self, limit: int = 10) -> List[Dict]:
        """
        Get recent query history.
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT query_id, query, timestamp, confidence, 
                   verification_status, source_count, processing_time
            FROM query_history
            ORDER BY timestamp DESC
            LIMIT ?
        ''', [limit])
        
        rows = cursor.fetchall()
        columns = ['query_id', 'query', 'timestamp', 'confidence',
                   'verification_status', 'source_count', 'processing_time']
        
        results = []
        for row in rows:
            result = dict(zip(columns, row))
            # Convert timestamp string back to datetime if needed
            if isinstance(result.get('timestamp'), str):
                try:
                    result['timestamp'] = datetime.fromisoformat(result['timestamp'])
                except (ValueError, TypeError):
                    pass
            results.append(result)
        
        conn.close()
        return results
    
    def register_document(self, doc_id: str, filename: str, file_path: str,
                         total_pages: int, chunk_count: int = 0, 
                         fact_count: int = 0):
        """
        Register a document in the index.
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO documents
            (doc_id, filename, file_path, total_pages, processed_at,
             chunk_count, fact_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            doc_id, filename, file_path, total_pages,
            datetime.now(), chunk_count, fact_count
        ))
        
        conn.commit()
        conn.close()
    
    def get_document(self, doc_id: str) -> Optional[Dict]:
        """
        Get document info by ID.
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT doc_id, filename, file_path, total_pages,
                   processed_at, chunk_count, fact_count
            FROM documents
            WHERE doc_id = ?
        ''', [doc_id])
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            columns = ['doc_id', 'filename', 'file_path', 'total_pages',
                      'processed_at', 'chunk_count', 'fact_count']
            result = dict(zip(columns, row))
            # Convert timestamp string back to datetime if needed
            if isinstance(result.get('processed_at'), str):
                try:
                    result['processed_at'] = datetime.fromisoformat(result['processed_at'])
                except (ValueError, TypeError):
                    pass
            return result
        
        return None