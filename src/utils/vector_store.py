"""
Vector store integration for LDU chunks.
Supports ChromaDB and FAISS (local, free).
"""

import os
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from pathlib import Path

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    print("⚠️ ChromaDB not installed. Install with: pip install chromadb")

try:
    import faiss
    import pickle
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    print("⚠️ FAISS not installed. Install with: pip install faiss-cpu")


class VectorStore:
    """
    Unified interface for vector stores (ChromaDB or FAISS).
    """
    
    def __init__(self, store_type: str = "chroma", persist_dir: str = ".refinery/vectors"):
        self.store_type = store_type
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        
        if store_type == "chroma" and CHROMA_AVAILABLE:
            self._init_chromadb()
        elif store_type == "faiss" and FAISS_AVAILABLE:
            self._init_faiss()
        else:
            print(f"⚠️ {store_type} not available, using in-memory dict fallback")
            self._init_dict()
    
    def _init_chromadb(self):
        """Initialize ChromaDB client"""
        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Create or get collection
        try:
            self.collection = self.client.get_collection("ldu_chunks")
        except:
            self.collection = self.client.create_collection(
                name="ldu_chunks",
                metadata={"hnsw:space": "cosine"}
            )
        
        self.embedding_function = None  # Will use Chroma's default
    
    def _init_faiss(self):
        """Initialize FAISS index"""
        self.index_path = self.persist_dir / "faiss.index"
        self.metadata_path = self.persist_dir / "metadata.pkl"
        
        # Dimension of embeddings (using sentence-transformers default)
        self.dimension = 384
        
        if self.index_path.exists():
            self.index = faiss.read_index(str(self.index_path))
            with open(self.metadata_path, 'rb') as f:
                self.metadata = pickle.load(f)
        else:
            self.index = faiss.IndexFlatL2(self.dimension)
            self.metadata = []
    
    def _init_dict(self):
        """Fallback: in-memory dict"""
        self.vectors = []
        self.metadata = []
    
    def add_chunks(
        self,
        chunks: List[Dict],
        embeddings: Optional[List[List[float]]] = None
    ):
        """
        Add chunks to vector store.
        
        Args:
            chunks: List of chunk dictionaries (must have 'id', 'content')
            embeddings: Optional pre-computed embeddings
        """
        if self.store_type == "chroma" and CHROMA_AVAILABLE:
            self._add_chromadb(chunks, embeddings)
        elif self.store_type == "faiss" and FAISS_AVAILABLE:
            self._add_faiss(chunks, embeddings)
        else:
            self._add_dict(chunks, embeddings)
    
    def _add_chromadb(self, chunks: List[Dict], embeddings: Optional[List[List[float]]] = None):
        """Add to ChromaDB"""
        ids = [c['id'] for c in chunks]
        documents = [c['content'] for c in chunks]
        metadatas = [{
            'doc_id': c.get('doc_id', ''),
            'page_num': c.get('primary_page', 0),
            'chunk_type': c.get('chunk_type', 'text'),
            'section': c.get('parent_section', ''),
            'token_count': c.get('token_count', 0)
        } for c in chunks]
        
        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
    
    def _add_faiss(self, chunks: List[Dict], embeddings: Optional[List[List[float]]] = None):
        """Add to FAISS"""
        if embeddings is None:
            # Use random embeddings as placeholder
            # In production, use sentence-transformers
            embeddings = [np.random.randn(self.dimension).astype('float32') 
                         for _ in chunks]
        
        for emb, chunk in zip(embeddings, chunks):
            self.index.add(np.array([emb]))
            self.metadata.append({
                'id': chunk['id'],
                'content': chunk['content'],
                'doc_id': chunk.get('doc_id', ''),
                'page_num': chunk.get('primary_page', 0),
                'chunk_type': chunk.get('chunk_type', 'text'),
                'section': chunk.get('parent_section', '')
            })
        
        # Save
        faiss.write_index(self.index, str(self.index_path))
        with open(self.metadata_path, 'wb') as f:
            pickle.dump(self.metadata, f)
    
    def _add_dict(self, chunks: List[Dict], embeddings: Optional[List[List[float]]] = None):
        """Add to in-memory dict"""
        if embeddings is None:
            embeddings = [np.random.randn(384).astype('float32') for _ in chunks]
        
        for emb, chunk in zip(embeddings, chunks):
            self.vectors.append(emb)
            self.metadata.append(chunk)
    
    def search(
        self,
        query: str,
        embedding: Optional[List[float]] = None,
        filter: Optional[Dict] = None,
        top_k: int = 5
    ) -> List[Dict]:
        """
        Search for similar chunks.
        
        Args:
            query: Text query
            embedding: Optional pre-computed query embedding
            filter: Metadata filter (ChromaDB format)
            top_k: Number of results
            
        Returns:
            List of chunks with similarity scores
        """
        if self.store_type == "chroma" and CHROMA_AVAILABLE:
            return self._search_chromadb(query, embedding, filter, top_k)
        elif self.store_type == "faiss" and FAISS_AVAILABLE:
            return self._search_faiss(embedding, filter, top_k)
        else:
            return self._search_dict(embedding, filter, top_k)
    
    def _search_chromadb(self, query: str, embedding: Optional[List[float]], 
                         filter: Optional[Dict], top_k: int) -> List[Dict]:
        """Search ChromaDB"""
        if embedding:
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=top_k,
                where=filter
            )
        else:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=filter
            )
        
        # Format results
        formatted = []
        if results['ids']:
            for i in range(len(results['ids'][0])):
                formatted.append({
                    'id': results['ids'][0][i],
                    'content': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                    'score': 1 - results['distances'][0][i] if results['distances'] else 1.0
                })
        
        return formatted
    
    def _search_faiss(self, embedding: Optional[List[float]], 
                      filter: Optional[Dict], top_k: int) -> List[Dict]:
        """Search FAISS"""
        if embedding is None:
            return []
        
        query_vec = np.array([embedding]).astype('float32')
        distances, indices = self.index.search(query_vec, min(top_k, len(self.metadata)))
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx < len(self.metadata):
                metadata = self.metadata[idx]
                
                # Apply filter if needed
                if filter:
                    # Simple filter implementation
                    for key, value in filter.items():
                        if key == 'page_num' and value.get('$between'):
                            low, high = value['$between']
                            if not (low <= metadata['page_num'] <= high):
                                continue
                
                results.append({
                    'id': metadata['id'],
                    'content': metadata['content'],
                    'metadata': metadata,
                    'score': float(1 / (1 + distances[0][i]))
                })
        
        return results
    
    def _search_dict(self, embedding: Optional[List[float]], 
                     filter: Optional[Dict], top_k: int) -> List[Dict]:
        """Search in-memory dict (linear scan)"""
        if embedding is None or not self.vectors:
            return []
        
        # Simple cosine similarity
        query_vec = np.array(embedding)
        scores = []
        
        for i, vec in enumerate(self.vectors):
            # Apply filter
            if filter:
                metadata = self.metadata[i]
                if filter.get('page_num') and metadata['primary_page'] != filter['page_num']:
                    continue
            
            # Cosine similarity
            sim = np.dot(query_vec, vec) / (np.linalg.norm(query_vec) * np.linalg.norm(vec))
            scores.append((i, sim))
        
        # Sort and return top_k
        scores.sort(key=lambda x: x[1], reverse=True)
        
        results = []
        for i, score in scores[:top_k]:
            results.append({
                'id': self.metadata[i]['ldu_id'],
                'content': self.metadata[i]['content'],
                'metadata': self.metadata[i],
                'score': float(score)
            })
        
        return results
    
    def delete_document(self, doc_id: str):
        """Delete all chunks for a document"""
        if self.store_type == "chroma" and CHROMA_AVAILABLE:
            self.collection.delete(where={'doc_id': doc_id})
        # FAISS and dict would need reindexing - simplified for now
    
    def count(self) -> int:
        """Get number of chunks"""
        if self.store_type == "chroma" and CHROMA_AVAILABLE:
            return self.collection.count()
        elif self.store_type == "faiss" and FAISS_AVAILABLE:
            return len(self.metadata)
        else:
            return len(self.metadata)