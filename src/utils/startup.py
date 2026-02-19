"""
Startup automation utility
Builds the Knowledge Graph and Semantic Index before the server starts accepting requests.
"""
from src.core.graph_builder import KnowledgeGraphBuilder
from src.core.semantic_search import SemanticSearchEngine
from src.config import settings
from loguru import logger
from pathlib import Path
import os

def run_startup_automation():
    """
    Builds the knowledge graph and semantic search index during startup.
    Returns the initialized builder and search engine.
    """
    logger.info("Configuration - Input JSON Dir: " + settings.input_json_dir)
    
    # Check if input data exists
    if not Path(settings.input_json_dir).exists():
        logger.warning(f"Input directory {settings.input_json_dir} not found. Skipping startup automation.")
        return None, None
        
    logger.info("=== STARTUP AUTOMATION: Building Knowledge Graph ===")
    
    try:
        # 1. Initialize Builder
        builder = KnowledgeGraphBuilder(seed=42)
        
        # 2. Build Graph from Input Directory (offline mode)
        # 2. Build Knowledge Graph (Incremental)
        from src.api.v1.graph import load_existing_graph
        
        # Try to find latest existing graph
        existing_graph = None
        graph_files = list(Path(settings.graph_storage_path).glob("*.pkl"))
        if graph_files:
            latest_graph_file = max(graph_files, key=os.path.getctime)
            import pickle
            try:
                with open(latest_graph_file, 'rb') as f:
                    existing_graph = pickle.load(f)
                logger.info(f"Loaded existing graph from {latest_graph_file.name} for incremental update.")
            except Exception as e:
                logger.warning(f"Failed to load existing graph: {e}. Starting fresh.")
        
        builder = KnowledgeGraphBuilder(existing_graph=existing_graph)
        stats = builder.build_from_directory(
            settings.input_json_dir, 
            enable_structural=True,
            enable_reference=True
        )
        
        logger.info(f"Graph update stats: {stats}")
        
        # 3. Initialize Semantic Search Engine (if enabled)
        engine = None
        if settings.enable_semantic_search:
            logger.info("=== STARTUP AUTOMATION: Updating Semantic Index ===")
            engine = SemanticSearchEngine(
                model_name=settings.embedding_model,
                vector_db_path=settings.vector_db_path,
                reranker_model=settings.reranker_model if settings.enable_reranking else None
            )
            
            # Check if we need full index or incremental
            new_files_count = stats.get('new_files_processed', 0)
            
            # Check if index is actually populated
            is_index_empty = False
            try:
                if engine.clause_collection.count() == 0:
                    is_index_empty = True
            except:
                is_index_empty = True

            if existing_graph is None or is_index_empty:
                # Fresh build or Re-index needed
                if is_index_empty:
                    logger.info("Semantic index is empty. Forcing full index build.")
                engine.index_graph(builder.graph)
            elif new_files_count > 0:
                # Incremental update
                engine.incremental_index(builder.graph, new_files_count)
            else:
                logger.info("No new files processed. Skipping index update.")
        
        # 5. Save Graph to Disk (for persistence)
        # Generate a consistent job_id for the startup build, e.g., "startup"
        job_id = "startup"
        graph_path = Path(settings.graph_storage_path) / f"{job_id}.pkl"
        builder.save_graph(str(graph_path))
        
        # Save JSON export too
        json_path = Path(settings.graph_storage_path) / f"{job_id}.json"
        builder.export_json(str(json_path))
        
        logger.info("=== STARTUP AUTOMATION COMPLETED ===")
        return builder, engine
        
    except Exception as e:
        logger.exception(f"Startup automation failed: {e}")
        return None, None
