"""
Endpoint 6: Visualization Data Provider
Provides processed graph data for frontend visualization.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from loguru import logger

router = APIRouter()

@router.get("/graph-data")
async def get_graph_data(
    max_nodes: int = 200,
    node_type: Optional[str] = None,
    document_id: Optional[str] = None
):
    """
    **Get graph data in format suitable for visualization**
    Returns nodes and edges in D3.js compatible format.
    """
    from src.api.v1.graph import graph_builder

    if not graph_builder:
        raise HTTPException(
            status_code=400,
            detail="Knowledge graph not built. Please call /graph/build first."
        )

    graph = graph_builder.graph
    nodes_data = []
    node_ids = []

    # Map node types to colors for standardized visualization
    color_map = {
        'Standard': '#FF6B6B',
        'Clause': '#4ECDC4',
        'Requirement': '#45B7D1',
        'ExternalStandard': '#FFA07A'
    }

    for node_id, data in graph.nodes(data=True):
        if node_type and data.get('node_type') != node_type: continue
        if document_id and data.get('document_id') != document_id: continue

        node_info = {
            'id': node_id,
            'label': data.get('title', node_id)[:50],
            'type': data.get('node_type', 'Unknown'),
            'document_id': data.get('document_id', ''),
            'size': 10 + (data.get('depth', 0) * 2),
            'color': color_map.get(data.get('node_type'), '#999999')
        }
        nodes_data.append(node_info)
        node_ids.append(node_id)
        if len(nodes_data) >= max_nodes: break

    edges_data = []
    node_id_set = set(node_ids)
    edge_color_map = {
        'PARENT_OF': '#2C3E50',
        'REFERENCES': '#E74C3C',
        'CONTAINS_REQUIREMENT': '#9B59B6',
        'CITES_STANDARD': '#F39C12',
        'SIBLING_OF': '#27AE60'
    }

    for u, v, data in graph.edges(data=True):
        if u in node_id_set and v in node_id_set:
            edges_data.append({
                'source': u,
                'target': v,
                'type': data.get('edge_type', 'unknown'),
                'color': edge_color_map.get(data.get('edge_type'), '#BDC3C7')
            })

    return {
        'nodes': nodes_data,
        'links': edges_data,
        'total_nodes': len(nodes_data),
        'total_links': len(edges_data)
    }
