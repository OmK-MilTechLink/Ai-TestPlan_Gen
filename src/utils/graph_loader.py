"""
Shared graph loading utility.
Centralizes the logic for finding and loading the latest Knowledge Graph
from disk, used by startup.py, retrieval.py, and graph.py.
"""
import os
import pickle
from pathlib import Path
from typing import Optional, Tuple
import networkx as nx
from loguru import logger
from src.config import settings


def load_latest_graph() -> Tuple[Optional[nx.MultiDiGraph], Optional[str]]:
    """
    Loads the latest saved Knowledge Graph from disk.
    Uses latest.txt pointer if available, otherwise falls back to
    the newest .pkl file by creation time.

    Returns:
        Tuple of (graph, version_name) where version_name is the .pkl filename,
        or (None, None) if no graph is found.
    """
    graph_dir = Path(settings.graph_storage_path)
    
    if not graph_dir.exists():
        logger.warning(f"Graph storage directory not found: {graph_dir}")
        return None, None

    # 1. Try the latest.txt pointer first (preferred — set by startup versioning)
    latest_ptr = graph_dir / "latest.txt"
    if latest_ptr.exists():
        version_name = latest_ptr.read_text().strip()
        graph_file = graph_dir / version_name
        if graph_file.exists():
            try:
                with open(graph_file, 'rb') as f:
                    graph = pickle.load(f)
                version = graph.graph.get('graph_version', 'unknown')
                logger.info(f"Loaded graph v{version} from '{version_name}' (via latest.txt).")
                return graph, version_name
            except Exception as e:
                logger.warning(f"Failed to load '{version_name}' from latest.txt pointer: {e}")

    # 2. Fallback: pick the newest .pkl by creation time (migration support)
    pkl_files = list(graph_dir.glob("*.pkl"))
    if pkl_files:
        fallback_file = max(pkl_files, key=os.path.getctime)
        try:
            with open(fallback_file, 'rb') as f:
                graph = pickle.load(f)
            logger.info(f"Loaded fallback graph from '{fallback_file.name}' (by creation time).")
            return graph, fallback_file.name
        except Exception as e:
            logger.warning(f"Failed to load fallback graph '{fallback_file.name}': {e}")

    logger.info("No existing graph found on disk.")
    return None, None
