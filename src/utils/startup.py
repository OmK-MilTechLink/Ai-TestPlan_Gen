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
        # 1. Find and load the latest existing graph using latest.txt pointer
        existing_graph = None
        graph_dir = Path(settings.graph_storage_path)
        latest_ptr = graph_dir / "latest.txt"
        
        if latest_ptr.exists():
            latest_name = latest_ptr.read_text().strip()
            latest_graph_file = graph_dir / latest_name
            if latest_graph_file.exists():
                import pickle
                try:
                    with open(latest_graph_file, 'rb') as f:
                        existing_graph = pickle.load(f)
                    version = existing_graph.graph.get('graph_version', 'unknown')
                    logger.info(f"Loaded existing graph v{version} from '{latest_name}'.")
                except Exception as e:
                    logger.warning(f"Failed to load '{latest_name}': {e}. Starting fresh.")
        else:
            # Fallback: pick the newest .pkl if no pointer exists (migration support)
            graph_files = list(graph_dir.glob("*.pkl"))
            if graph_files:
                fallback_file = max(graph_files, key=os.path.getctime)
                import pickle
                try:
                    with open(fallback_file, 'rb') as f:
                        existing_graph = pickle.load(f)
                    logger.info(f"Loaded fallback graph from '{fallback_file.name}'.")
                except Exception as e:
                    logger.warning(f"Failed to load fallback graph: {e}. Starting fresh.")

        # 2. Build / merge KG incrementally (skips already-processed files)
        builder = KnowledgeGraphBuilder(existing_graph=existing_graph)
        stats = builder.build_from_directory(
            settings.input_json_dir, 
            enable_structural=True,
            enable_reference=True
        )
        
        new_files_count = stats.get('new_files_processed', 0)
        logger.info(f"Graph update stats: nodes={stats.get('nodes')}, new_files={new_files_count}")

        # 3. Initialize Semantic Search Engine (if enabled)
        engine = None
        if settings.enable_semantic_search:
            logger.info("=== STARTUP AUTOMATION: Updating Semantic Index ===")
            engine = SemanticSearchEngine(
                model_name=settings.embedding_model,
                vector_db_path=settings.vector_db_path,
                reranker_model=settings.reranker_model if settings.enable_reranking else None
            )
            
            # Check if index is actually populated
            is_index_empty = False
            try:
                if engine.clause_collection.count() == 0:
                    is_index_empty = True
            except:
                is_index_empty = True

            # BUG FIX: elif/else are now correctly INSIDE the if enable_semantic_search block
            if existing_graph is None or is_index_empty:
                if is_index_empty:
                    logger.info("Semantic index is empty. Forcing full index build.")
                engine.index_graph(builder.graph)
            elif new_files_count > 0:
                logger.info(f"Incrementally indexing {new_files_count} new files.")
                engine.incremental_index(builder.graph, new_files_count)
            else:
                logger.info("No new files. Skipping semantic index update.")

        # 4. Save Graph only if new data was processed — versioned to preserve history
        if new_files_count > 0:
            current_version = builder.graph.graph.get('graph_version', 1)
            versioned_name = f"startup_v{current_version}.pkl"
            graph_path = graph_dir / versioned_name
            json_path = graph_dir / f"startup_v{current_version}.json"
            
            builder.save_graph(str(graph_path))
            builder.export_json(str(json_path))
            
            # Update pointer so next restart loads the correct version
            latest_ptr.write_text(versioned_name)
            logger.info(f"Saved new graph as '{versioned_name}'. latest.txt pointer updated.")
        else:
            logger.info("No new files processed. Skipping graph save (graph is already up to date).")
        
        logger.info("=== STARTUP AUTOMATION COMPLETED ===")
        return builder, engine
        
    except Exception as e:
        logger.exception(f"Startup automation failed: {e}")
        return None, None
