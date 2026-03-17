"""
Semantic Search Engine using Sentence Transformers and ChromaDB
"""
import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder
from typing import List, Dict, Any, Optional
from pathlib import Path
import torch
import numpy as np
from loguru import logger

class SemanticSearchEngine:
    """
    Semantic search using embeddings and vector similarity
    With optional Reranking
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2",
                 vector_db_path: str = "./chroma_db",
                 reranker_model: Optional[str] = None,
                 seed: int = 42):
        self.model_name = model_name
        self.seed = seed
        self._set_determinism()

        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)

        # Initialize Reranker if provided
        self.reranker = None
        if reranker_model:
            logger.info(f"Loading reranker model: {reranker_model}")
            try:
                self.reranker = CrossEncoder(reranker_model)
            except Exception as e:
                logger.warning(f"Failed to load reranker {reranker_model}: {e}")

        # Initialize ChromaDB
        Path(vector_db_path).mkdir(parents=True, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=vector_db_path)

        # Collections: try to load existing, handle 'not found' gracefully
        try:
            self.clause_collection = self.chroma_client.get_collection("clauses")
            self.requirement_collection = self.chroma_client.get_collection("requirements")
            logger.info(f"Loaded existing collections. Clauses: {self.clause_collection.count()}, Requirements: {self.requirement_collection.count()}")
        except Exception as e:
            # This is expected on first run when collections don't exist yet
            err_str = str(e).lower()
            if "does not exist" in err_str or "collection" in err_str:
                logger.info("No existing ChromaDB collections found. Will be created on first indexing.")
            else:
                logger.error(f"Unexpected error loading ChromaDB collections: {e}")
            self.clause_collection = None
            self.requirement_collection = None

    def _set_determinism(self):
        """Set random seeds for reproducibility"""
        torch.manual_seed(self.seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        np.random.seed(self.seed)

    def index_graph(self, graph):
        """
        Index all nodes from knowledge graph
        """
        logger.info("Indexing knowledge graph for semantic search...")

        # Create or get collections
        try:
            self.chroma_client.delete_collection("clauses")
            self.chroma_client.delete_collection("requirements")
        except:
            pass

        self.clause_collection = self.chroma_client.create_collection(
            name="clauses",
            metadata={"hnsw:space": "cosine"}
        )

        self.requirement_collection = self.chroma_client.create_collection(
            name="requirements",
            metadata={"hnsw:space": "cosine"}
        )

        # Index clauses
        clause_ids = []
        clause_texts = []
        clause_metadatas = []

        for node_id, data in graph.nodes(data=True):
            if data.get('node_type') == 'Clause':
                # Extract text content
                text = self._extract_clause_text(data)
                if text:
                    clause_ids.append(node_id)
                    clause_texts.append(text)
                    clause_metadatas.append({
                        'chunk_id': node_id,
                        'document_id': data.get('document_id', ''),
                        'clause_id': data.get('clause_id', ''),
                        'title': data.get('title', ''),
                        'depth': str(data.get('depth', 0))
                    })

        if clause_ids:
            # Generate embeddings in batches
            logger.info(f"Generating embeddings for {len(clause_ids)} clauses...")
            embeddings = self.model.encode(
                clause_texts,
                batch_size=32,
                show_progress_bar=True,
                normalize_embeddings=True
            )

            # Add to ChromaDB
            self.clause_collection.add(
                ids=clause_ids,
                embeddings=embeddings.tolist(),
                metadatas=clause_metadatas,
                documents=clause_texts
            )

        # Index requirements
        req_ids = []
        req_texts = []
        req_metadatas = []

        for node_id, data in graph.nodes(data=True):
            if data.get('node_type') == 'Requirement':
                text = data.get('text', '')
                if text:
                    req_ids.append(node_id)
                    req_texts.append(text)
                    req_metadatas.append({
                        'requirement_id': node_id,
                        'parent_clause': data.get('parent_clause', ''),
                        'requirement_type': data.get('requirement_type', ''),
                        'keyword': data.get('keyword', '')
                    })

        if req_ids:
            logger.info(f"Generating embeddings for {len(req_ids)} requirements...")
            embeddings = self.model.encode(
                req_texts,
                batch_size=32,
                show_progress_bar=True,
                normalize_embeddings=True
            )

            self.requirement_collection.add(
                ids=req_ids,
                embeddings=embeddings.tolist(),
                metadatas=req_metadatas,
                documents=req_texts
            )

        logger.info(f"Indexing complete: {len(clause_ids)} clauses, {len(req_ids)} requirements")
        
    def incremental_index(self, graph, new_file_count: int):
        """
        Index only new nodes that are not yet in ChromaDB.
        Used when graph is updated incrementally.
        """
        if new_file_count == 0:
            logger.info("No new files to index.")
            return

        logger.info("Performing incremental semantic indexing...")
        
        # Ensure collections exist
        if not self.clause_collection or not self.requirement_collection:
            self.index_graph(graph)
            return

        # Get existing IDs
        existing_clause_ids = set(self.clause_collection.get()['ids'])
        existing_req_ids = set(self.requirement_collection.get()['ids'])
        
        # Identify new nodes
        new_clause_ids = []
        new_clause_texts = []
        new_clause_metadatas = []
        
        new_req_ids = []
        new_req_texts = []
        new_req_metadatas = []
        
        for node_id, data in graph.nodes(data=True):
            node_type = data.get('node_type')
            
            if node_type == 'Clause' and node_id not in existing_clause_ids:
                text = self._extract_clause_text(data)
                if text:
                    new_clause_ids.append(node_id)
                    new_clause_texts.append(text)
                    new_clause_metadatas.append({
                        'chunk_id': node_id,
                        'document_id': data.get('document_id', ''),
                        'clause_id': data.get('clause_id', ''),
                        'title': data.get('title', ''),
                        'depth': str(data.get('depth', 0))
                    })
            
            elif node_type == 'Requirement' and node_id not in existing_req_ids:
                text = data.get('text', '')
                if text:
                    new_req_ids.append(node_id)
                    new_req_texts.append(text)
                    new_req_metadatas.append({
                        'requirement_id': node_id,
                        'parent_clause': data.get('parent_clause', ''),
                        'requirement_type': data.get('requirement_type', ''),
                        'keyword': data.get('keyword', '')
                    })

        # Index new clauses
        if new_clause_ids:
            logger.info(f"Indexing {len(new_clause_ids)} new clauses...")
            embeddings = self.model.encode(
                new_clause_texts,
                batch_size=32,
                show_progress_bar=True,
                normalize_embeddings=True
            )
            self.clause_collection.add(
                ids=new_clause_ids,
                embeddings=embeddings.tolist(),
                metadatas=new_clause_metadatas,
                documents=new_clause_texts
            )

        # Index new requirements
        if new_req_ids:
            logger.info(f"Indexing {len(new_req_ids)} new requirements...")
            embeddings = self.model.encode(
                new_req_texts,
                batch_size=32,
                show_progress_bar=True,
                normalize_embeddings=True
            )
            self.requirement_collection.add(
                ids=new_req_ids,
                embeddings=embeddings.tolist(),
                metadatas=new_req_metadatas,
                documents=new_req_texts
            )
            
        logger.info(f"Incremental indexing complete. Added {len(new_clause_ids)} clauses and {len(new_req_ids)} requirements.")

    def _extract_clause_text(self, clause_data: Dict[str, Any]) -> str:
        """
        Extract searchable text from clause
        """
        text_parts = []

        # Add title
        title = clause_data.get('title', '')
        if title:
            text_parts.append(title)

        # Add content
        content = clause_data.get('content', [])
        for item in content:
            if item.get('type') in ['paragraph', 'list_item']:
                text = item.get('text', '')
                if text:
                    text_parts.append(text)

        return ' '.join(text_parts)

    def search_clauses(self, query: str, n_results: int = 20,
                      document_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for relevant clauses
        """
        if not self.clause_collection:
            return []

        # Apply filters
        where_filter = None
        if document_filter:
            where_filter = {"document_id": document_filter}

        results = self.clause_collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where_filter
        )

        # Format results
        formatted_results = []
        if results['ids']:
            for idx, node_id in enumerate(results['ids'][0]):
                formatted_results.append({
                    'node_id': node_id,
                    'relevance_score': 1.0 - results['distances'][0][idx],  # Convert distance to similarity
                    'metadata': results['metadatas'][0][idx],
                    'text': results['documents'][0][idx]
                })

        return formatted_results

    def search_requirements(self, query: str, n_results: int = 20,
                           requirement_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for relevant requirements
        """
        if not self.requirement_collection:
            return []

        # Apply filters
        where_filter = None
        if requirement_type:
            where_filter = {"requirement_type": requirement_type}

        results = self.requirement_collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where_filter
        )

        # Format results
        formatted_results = []
        if results['ids']:
            for idx, node_id in enumerate(results['ids'][0]):
                score = 1.0 - results['distances'][0][idx]
                formatted_results.append({
                    'node_id': node_id,
                    'relevance_score': score,
                    'metadata': results['metadatas'][0][idx],
                    'text': results['documents'][0][idx]
                })

            # Log top 5 raw scores for debugging
            top_scores = [f"{r['node_id']}: {r['relevance_score']:.3f}" for r in formatted_results[:5]]
            logger.debug(f"Top 5 raw semantic scores: {top_scores}")

        return formatted_results

    def rerank(self, query: str, candidates: List[str], top_k: int = 15) -> List[int]:
        """
        Rerank a list of candidate texts based on query relevance using CrossEncoder.
        Returns the indices of the top_k candidates.
        """
        if not self.reranker or not candidates:
            return list(range(min(len(candidates), top_k)))
            
        # Prepare pairs for CrossEncoder
        pairs = [[query, doc] for doc in candidates]
        
        # Predict scores
        try:
            scores = self.reranker.predict(pairs)
            
            # Sort indices by score desc
            sorted_indices = np.argsort(scores)[::-1]
            
            # Log reranking effect
            logger.debug(f"Reranking top {top_k} candidates. Top scores before: {scores[:5] if len(scores) > 0 else 'None'}")
            
            return sorted_indices[:top_k].tolist()
        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            return list(range(min(len(candidates), top_k)))
