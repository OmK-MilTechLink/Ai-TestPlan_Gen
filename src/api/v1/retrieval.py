"""
Endpoint 3: Context Retrieval
Hybrid search combining semantic + graph traversal
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import uuid
from datetime import datetime
from pathlib import Path
from src.config import settings
import json
import os

from src.models.api_models import (
    RetrievalQueryRequest,
    RetrievalResponse
)
from src.config import settings
from loguru import logger

router = APIRouter()

@router.post("/query", response_model=RetrievalResponse)
async def query_knowledge_graph(request: RetrievalQueryRequest):
    """
    **Endpoint 3: Query Knowledge Graph for Relevant Context**

    Retrieves relevant requirements using hybrid search (Semantic + Keyword).

    **Search Methods:**
    1. **Semantic**: Vector similarity using Sentence Transformers (ChromaDB)
    2. **Keyword**: Text-based matching in requirement text
    
    The results are combined and reranked.
    """
    from src.api.v1.graph import graph_builder, search_engine, load_existing_graph

    if not graph_builder:
        # Try to auto-load if not loaded (basic recovery)
        try:
            # Find latest graph
            graph_dir = Path("graph_data")
            if graph_dir.exists():
                pkl_files = list(graph_dir.glob("*.pkl"))
                if pkl_files:
                    latest_graph = max(pkl_files, key=os.path.getctime)
                    job_id = latest_graph.stem
                    logger.info(f"Auto-loading graph {job_id} for retrieval...")
                    
                    # Await the load function
                    await load_existing_graph(job_id)
                    
                    # Refresh references
                    from src.api.v1.graph import graph_builder, search_engine
        except Exception as e:
            logger.warning(f"Could not auto-load graph: {e}")

    if not graph_builder:
        raise HTTPException(
            status_code=400,
            detail="Knowledge graph not built. Please call /graph/build first."
        )

    query_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    try:
        # Build search keywords from component profile
        component = request.component_profile
        
        # 1. Semantic Search Query Construction
        # Create a natural language query representing what we are looking for
        query_text = f"Test requirements for {component.type} used in {component.application} application. "
        query_text += f"Test level: {component.test_level}. "
        query_text += f"Categories: {', '.join(component.test_categories)}. "
        if component.specifications:
            query_text += f"Specs: {', '.join([f'{k}={v}' for k,v in component.specifications.items()])}"
            
        logger.info(f"Semantic Query: {query_text} (Max Results: {request.max_results})")

        # Execute Semantic Search
        semantic_results = {}
        if search_engine:
            try:
                # We search for more results than requested to allow for filtering
                sem_hits = search_engine.search_requirements(query_text, n_results=max(100, request.max_results * 2))
                for hit in sem_hits:
                    semantic_results[hit['node_id']] = hit
                logger.info(f"Semantic search returned {len(sem_hits)} hits")
            except Exception as e:
                logger.error(f"Semantic search failed: {e}")
        else:
            logger.error("Search engine is NONE. Semantic search skipped. Check if index is built.")

        # 2. Keyword Search Construction
        search_terms = []
        search_terms.extend(component.type.lower().split())
        search_terms.extend(component.application.lower().split())
        search_terms.extend([cat.lower() for cat in component.test_categories])

        # Add common test-related keywords
        keyword_map = {
            'thermal': ['temperature', 'heat', 'thermal', 'cold', 'hot', 'celsius', '°c', 'climate', 'shock'],
            'mechanical': ['vibration', 'shock', 'mechanical', 'force', 'stress', 'impact', 'drop'],
            'environmental': ['humidity', 'water', 'dust', 'environment', 'climate', 'moisture', 'salt', 'corrosion', 'ingress'],
            'electrical': ['voltage', 'current', 'electrical', 'power', 'resistance', 'insulation', 'dielectric', 'short'],
            'emc': ['emc', 'electromagnetic', 'interference', 'emission', 'immunity', 'electrostatic', 'esd', 'conducted', 'radiated'],
            'durability': ['durability', 'life', 'cycle', 'endurance', 'aging', 'wear']
        }

        for cat in component.test_categories:
            if cat.lower() in keyword_map:
                search_terms.extend(keyword_map[cat.lower()])
        
        # Clean unique terms
        search_terms = list(set([t.lower() for t in search_terms if len(t) > 2]))
        logger.info(f"Keyword Search terms: {search_terms}")

        # 3. Hybrid Merge and Scoring
        combined_results = {}
        
        # Helper to get existing entry or create new
        def get_or_create_result(node_id, node_data):
            if node_id not in combined_results:
                # Fetch parent context
                parent_id = node_data.get('parent_clause')
                parent_title = ""
                if parent_id and graph_builder.graph.has_node(parent_id):
                    parent_node = graph_builder.graph.nodes[parent_id]
                    parent_title = parent_node.get('title', str(parent_id))
                
                # Construct context-rich text
                context_text = f"{parent_title}: {node_data.get('text', '')}" if parent_title else node_data.get('text', '')

                combined_results[node_id] = {
                    'node_id': node_id,
                    'node_type': 'Requirement',
                    'requirement_id': node_id,
                    'requirement_type': node_data.get('requirement_type', 'mandatory'),
                    'text': node_data.get('text', ''),
                    'context_text': context_text, # For reranking
                    'keyword': node_data.get('keyword', 'shall'),
                    'parent_clause': node_data.get('parent_clause', ''),
                    'semantic_score': 0.0,
                    'keyword_score': 0.0,
                    'matched_terms': [],
                    'retrieval_method': 'hybrid',
                    'figures': []
                }
                
                # Attach figures from parent clause
                if parent_id and graph_builder.graph.has_node(parent_id):
                    parent_node = graph_builder.graph.nodes[parent_id]
                    figs = parent_node.get('figures', [])
                    
                    # IF figures missing in memory graph but chunk file might have them, load it
                    if not figs:
                        source_file = parent_node.get('source_file', '')
                        if source_file:
                            
                            # Resolve actual path
                            json_path = settings.abs_data_dir / source_file if source_file.startswith('output_json_chunk') else Path(settings.input_json_dir) / os.path.basename(source_file)
                            
                            if json_path.exists():
                                try:
                                    with open(json_path, 'r', encoding='utf-8') as f:
                                        chunk_data = json.load(f)
                                        figs = chunk_data.get('figures', [])
                                except Exception:
                                    pass
                                    
                    combined_results[node_id]['figures'] = figs
                    
            return combined_results[node_id]

        # Process Semantic Results
        start_time = datetime.utcnow()
        for node_id, hit in semantic_results.items():
            if graph_builder.graph.has_node(node_id):
                node_data = graph_builder.graph.nodes[node_id]
                res = get_or_create_result(node_id, node_data)
                res['semantic_score'] = hit['relevance_score']

        # Process Keyword Search (Scan all nodes - naive but effective for small graphs < 10k nodes)
        # For larger graphs, we would rely more on semantic search or inverted index
        for node_id, node_data in graph_builder.graph.nodes(data=True):
            if node_data.get('node_type') != 'Requirement':
                continue

            # Get requirement text
            req_text = node_data.get('text', '').lower()
            if not req_text:
                continue

            # Calculate relevance score based on keyword matches
            matches = 0
            curr_matched_terms = []
            for term in search_terms:
                if term in req_text:
                    matches += 1
                    curr_matched_terms.append(term)
            
            if matches > 0:
                # Get or create result (might exist from semantic)
                res = get_or_create_result(node_id, node_data)
                
                # Normalize keyword score. 
                # Assuming 5 matches is "very good" (1.0).
                # New formula: Score = matches / 6.0, cap at 1.0
                k_score = min(1.0, matches / 6.0)
                
                # Boost if mandatory
                if node_data.get('requirement_type') == 'mandatory':
                    k_score = min(1.0, k_score * 1.2)
                
                res['keyword_score'] = k_score
                res['matched_terms'] = curr_matched_terms
                logger.debug(f"Keyword match for {node_id}: {curr_matched_terms} (Score: {k_score:.2f})")

        # 4. Final Scoring and Ranking
        final_list = []
        for res in combined_results.values():
            s_score = res['semantic_score']
            k_score = res['keyword_score']
            
            final_score = 0.0
            
            # IMPROVED HYBRID FORMULA
            # Allow strong semantic matches to pass even without keywords
            if s_score > 0 and k_score > 0:
                final_score = (0.7 * s_score) + (0.3 * k_score)
            elif s_score > 0:
                final_score = s_score  # Don't penalize pure semantic matches
            elif k_score > 0:
                final_score = k_score * 0.5 # Penalize pure keyword matches (often noisy)
            
            final_score = min(1.0, final_score)
            res['relevance_score'] = round(final_score, 3)
            
            if final_score >= request.min_confidence:
                final_list.append(res)

        # Log combined scores for top results
        top_candidates = sorted(combined_results.values(), key=lambda x: x['relevance_score'], reverse=True)[:5]
        for c in top_candidates:
            logger.debug(f"Candidate {c['node_id']}: Final={c['relevance_score']:.3f} (Sem={c['semantic_score']:.3f}, Key={c['keyword_score']:.3f})")

        # Initial Sort by hybrid score
        final_list.sort(key=lambda x: x['relevance_score'], reverse=True)        
        reranked = False
        
        if settings.enable_reranking and search_engine and search_engine.reranker:
            # Take ALL candidates for reranking (User requested all > threshold)
            # Threshold filtering already happened via 'request.min_confidence' check
            candidates_to_rerank = final_list
            
            if candidates_to_rerank:
                logger.info(f"Reranking {len(candidates_to_rerank)} candidates (All above threshold {request.min_confidence})...")
                # Use CONTEXT text for reranking
                candidate_texts = [c.get('context_text', c['text']) for c in candidates_to_rerank]
                
                # Get indices of best documents
                ranked_indices = search_engine.rerank(query_text, candidate_texts, top_k=len(candidates_to_rerank))
                
                # Reorder the list based on reranker
                reranked_list = [candidates_to_rerank[i] for i in ranked_indices]
                
                final_list = reranked_list
                reranked = True

        # Limit results (User requested top 15 implies defaults or explicit max_results)
        final_results = final_list[:request.max_results]
        
        logger.info(f"Retrieval complete. Found {len(final_results)} items (Candidates: {len(combined_results)}, Reranked: {reranked})")

        return RetrievalResponse(
            job_id=job_id,
            query_id=query_id,
            status="completed",
            results=final_results,
            total_results=len(final_results),
            retrieval_metadata={
                'search_terms': search_terms,
                'total_requirements_searched': sum(1 for _, d in graph_builder.graph.nodes(data=True) if d.get('node_type') == 'Requirement'),
                'candidates_found': len(combined_results),
                'filtered_by_confidence': request.min_confidence,
                'semantic_hits': len(semantic_results),
                'retrieval_method': 'hybrid_reranked' if reranked else 'hybrid',
                'reranking_enabled': settings.enable_reranking
            },
            timestamp=datetime.utcnow()
        )

    except Exception as e:
        logger.exception(f"Retrieval query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {str(e)}")

@router.get("/explain/{query_id}")
async def explain_retrieval(query_id: str):
    """
    **Explain how results were retrieved**

    Provides detailed explanation of the retrieval process:
    - Search methods used
    - Scoring breakdown
    - Graph traversal path
    - Confidence factors

    **Parameters:**
    - query_id: Query ID from /query endpoint
    """
    # For now, return placeholder
    return {
        "query_id": query_id,
        "message": "Retrieval explanation",
        "explanation": {
            "semantic_search": "Used sentence-transformers embedding similarity",
            "graph_traversal": "Followed parent-child relationships",
            "scoring": "Combined semantic score + graph proximity",
            "confidence_threshold": "Filtered results below threshold"
        }
    }
