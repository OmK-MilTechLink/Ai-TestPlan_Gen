"""
Knowledge Graph Builder
Constructs multi-layer knowledge graph from JSON documents with full traceability
"""
import json
import hashlib
import networkx as nx
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import re
from loguru import logger

class KnowledgeGraphBuilder:
    """
    Builds a traceable knowledge graph from standards documents
    """

    def __init__(self, existing_graph: Optional[nx.MultiDiGraph] = None, seed: int = 42):
        self.graph = existing_graph if existing_graph is not None else nx.MultiDiGraph()
        self.seed = seed
        self.node_count = self.graph.number_of_nodes()
        self.edge_count = self.graph.number_of_edges()
        
        # Provenance tracking: store as map of filename -> {size, mtime}
        self.processed_files = self.graph.graph.get('processed_files', {})
        if isinstance(self.processed_files, list):
            # Migration from old list-based format to new map-based manifest
            self.processed_files = {f: {"size": 0, "mtime": 0} for f in self.processed_files}
        
    def build_from_directory(self, data_path: str,
                            enable_structural: bool = True,
                            enable_reference: bool = True) -> Dict[str, Any]:
        """
        Build knowledge graph from JSON files in directory
        """
        logger.info(f"Building knowledge graph from: {data_path}")

        data_dir = Path(data_path)
        if not data_dir.exists():
            raise FileNotFoundError(f"Directory not found: {data_path}")

        # Load all JSON files (sorted for determinism)
        json_files = sorted(list(data_dir.rglob("*.json")))
        total_files = len(json_files)
        
        # Filter out already processed files using richer manifest (name, size, mtime)
        new_files = []
        for f in json_files:
            try:
                stat = f.stat()
                file_size = stat.st_size
                file_mtime = stat.st_mtime
                # Use relative path as the unique key (avoids filename collisions across subdirectories)
                rel_path = str(f.relative_to(data_dir)).replace('\\', '/')
                
                is_new = True
                if rel_path in self.processed_files:
                    manifest = self.processed_files[rel_path]
                    if manifest.get("size") == file_size and manifest.get("mtime") == file_mtime:
                        is_new = False
                
                if is_new:
                    new_files.append((f, rel_path, file_size, file_mtime))
            except Exception as e:
                logger.warning(f"Failed to stat {f}: {e}")
                continue
        
        logger.info(f"Found {total_files} files. New files to process: {len(new_files)}")
        
        if not new_files:
            logger.info("No new files to process. Graph is up to date.")
            stats = self._compute_statistics()
            stats['new_files_processed'] = 0
            return stats

        documents = []
        for idx, (json_file, rel_path, file_size, file_mtime) in enumerate(new_files):
            if idx % 100 == 0:
                logger.info(f"Processing file {idx}/{len(new_files)}: {json_file.name}")
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    data['_source_file'] = rel_path
                    documents.append(data)
                    # Update manifest using relative path as unique key
                    self.processed_files[rel_path] = {
                        "size": file_size,
                        "mtime": file_mtime,
                    }
            except Exception as e:
                logger.warning(f"Failed to load {json_file}: {e}")
                continue

        logger.info(f"Loaded {len(documents)} new documents successfully")

        # Phase 1: Create nodes
        logger.info("Phase 1: Creating nodes...")
        self._create_nodes(documents)

        # Phase 2: Create structural links
        if enable_structural:
            logger.info("Phase 2: Creating structural links...")
            self._create_structural_links()

        # Phase 3: Create reference links
        if enable_reference:
            logger.info("Phase 3: Creating reference links...")
            self._create_reference_links()
            
        # Update metadata
        self.graph.graph['processed_files'] = self.processed_files
        self.graph.graph['last_updated'] = datetime.utcnow().isoformat()
        # Increment version number each time new data is merged
        self.graph.graph['graph_version'] = self.graph.graph.get('graph_version', 0) + 1

        # Compute graph statistics
        stats = self._compute_statistics()
        stats['new_files_processed'] = len(new_files)

        logger.info(f"Graph updated: {stats['nodes']} nodes, {stats['edges']} edges")
        logger.debug(f"Edge types broken down: {self._get_edge_type_counts()}")

        return {
            'nodes_created': stats['nodes'],
            'edges_created': stats['edges'],
            'standards': stats['standards'],
            'clauses': stats['clauses'],
            'requirements': stats['requirements'],
            'graph_checksum': self._compute_checksum(),
            'new_files_processed': len(new_files)
        }

    def _create_nodes(self, documents: List[Dict[str, Any]]):
        """
        Create nodes for all entities in documents
        """
        # Track standards
        standards = {}

        for doc in documents:
            chunk_id = doc.get('chunk_id', '')
            document_id = doc.get('document_id', '')

            if not chunk_id or not document_id:
                continue

            # Create standard node if not exists
            if document_id not in standards:
                standards[document_id] = {
                    'node_type': 'Standard',
                    'document_id': document_id,
                    'title': document_id,
                    'created_at': datetime.utcnow().isoformat()
                }
                self.graph.add_node(document_id, **standards[document_id])
                self.node_count += 1

            # Create clause node
            clause_node = {
                'node_type': 'Clause',
                'chunk_id': chunk_id,
                'document_id': document_id,
                'clause_id': doc.get('clause_id', ''),
                'title': doc.get('title', ''),
                'parent_id': doc.get('parent_id'),
                'children_ids': doc.get('children_ids', []),
                'content': doc.get('content', []),
                'tables': doc.get('tables', []),
                'figures': [],
                'references': doc.get('references', {}),
                'source_file': doc.get('_source_file', ''),
                'created_at': datetime.utcnow().isoformat()
            }

            # Process figures to normalize paths
            raw_figures = doc.get('figures', [])
            processed_figures = []
            for fig in raw_figures:
                if 'path' in fig:
                    # Replace backslashes with forward slashes
                    fig['path'] = fig['path'].replace('\\', '/')
                    # Ensure it starts with output_images if not already (it usually does based on analysis)
                    # And ensure it's relative to the static mount point if we want to serve it
                processed_figures.append(fig)
            clause_node['figures'] = processed_figures

            # Calculate depth from clause_id
            clause_id = doc.get('clause_id', '')
            if clause_id and clause_id != 'misc':
                parts = clause_id.replace('Annex ', '').split('.')
                clause_node['depth'] = len(parts)
            else:
                clause_node['depth'] = 0

            self.graph.add_node(chunk_id, **clause_node)
            self.node_count += 1

            # Add edge: Standard -> Clause
            if not self.graph.has_edge(document_id, chunk_id):
                self.graph.add_edge(
                    document_id,
                    chunk_id,
                    edge_type='CONTAINS_CLAUSE',
                    linking_method='structural',
                    confidence=1.0,
                    created_at=datetime.utcnow().isoformat()
                )
                self.edge_count += 1

            # Create requirement nodes
            requirements = doc.get('requirements', [])
            for idx, req in enumerate(requirements):
                req_id = f"{chunk_id}::req_{idx}"

                req_node = {
                    'node_type': 'Requirement',
                    'requirement_id': req_id,
                    'parent_clause': chunk_id,
                    'requirement_type': req.get('type', 'unknown'),
                    'keyword': req.get('keyword', ''),
                    'text': req.get('text', ''),
                    'created_at': datetime.utcnow().isoformat()
                }

                self.graph.add_node(req_id, **req_node)
                self.node_count += 1

                # Add edge: Clause -> Requirement
                self.graph.add_edge(
                    chunk_id,
                    req_id,
                    edge_type='CONTAINS_REQUIREMENT',
                    linking_method='structural',
                    confidence=1.0,
                    created_at=datetime.utcnow().isoformat()
                )
                self.edge_count += 1

    def _create_structural_links(self):
        """
        Create parent-child hierarchical links
        """
        # Build lookup by clause_id
        clause_lookup = {}
        for node_id, data in self.graph.nodes(data=True):
            if data.get('node_type') == 'Clause':
                clause_id = data.get('clause_id')
                if clause_id:
                    clause_lookup[clause_id] = node_id

        # Create parent-child edges
        for node_id, data in self.graph.nodes(data=True):
            if data.get('node_type') != 'Clause':
                continue

            parent_id = data.get('parent_id')
            if parent_id and parent_id in clause_lookup:
                parent_node_id = clause_lookup[parent_id]

                # Add parent-child edges
                if not self.graph.has_edge(parent_node_id, node_id):
                    self.graph.add_edge(
                        parent_node_id,
                        node_id,
                        edge_type='PARENT_OF',
                        linking_method='structural',
                        confidence=1.0,
                        created_at=datetime.utcnow().isoformat()
                    )
                    self.edge_count += 1

            # Add sibling relationships
            if parent_id and parent_id in clause_lookup:
                parent_node_id = clause_lookup[parent_id]
                parent_data = self.graph.nodes[parent_node_id]
                children = parent_data.get('children_ids', [])

                clause_id = data.get('clause_id')
                if clause_id in children:
                    for sibling_id in children:
                        if sibling_id != clause_id and sibling_id in clause_lookup:
                            sibling_node_id = clause_lookup[sibling_id]

                            # Check if edge already exists
                            if not self.graph.has_edge(node_id, sibling_node_id, key=0):
                                self.graph.add_edge(
                                    node_id,
                                    sibling_node_id,
                                    edge_type='SIBLING_OF',
                                    linking_method='structural',
                                    confidence=1.0,
                                    created_at=datetime.utcnow().isoformat()
                                )
                                self.edge_count += 1

    def _create_reference_links(self):
        """
        Create reference-based links from internal_resolved and standards
        """
        # Build lookup by clause_id
        clause_lookup = {}
        for node_id, data in self.graph.nodes(data=True):
            if data.get('node_type') == 'Clause':
                clause_id = data.get('clause_id')
                if clause_id:
                    clause_lookup[clause_id] = node_id

        # Create reference edges
        # First, collect all nodes to avoid dictionary changed size during iteration
        nodes_list = list(self.graph.nodes(data=True))

        for node_id, data in nodes_list:
            if data.get('node_type') != 'Clause':
                continue

            references = data.get('references', {})

            # Internal references
            internal_refs = references.get('internal_resolved', [])
            for ref_clause_id in internal_refs:
                if ref_clause_id in clause_lookup:
                    ref_node_id = clause_lookup[ref_clause_id]

                    if not self.graph.has_edge(node_id, ref_node_id):
                        self.graph.add_edge(
                            node_id,
                            ref_node_id,
                            edge_type='REFERENCES',
                            linking_method='reference',
                            confidence=1.0,
                            created_at=datetime.utcnow().isoformat()
                        )
                        self.edge_count += 1

            # Cross-standard references
            std_refs = references.get('standards', [])
            for std_ref in std_refs:
                # Create external standard node if needed
                std_node_id = f"EXT::{std_ref}"
                if not self.graph.has_node(std_node_id):
                    self.graph.add_node(
                        std_node_id,
                        node_type='ExternalStandard',
                        standard_name=std_ref,
                        created_at=datetime.utcnow().isoformat()
                    )
                    self.node_count += 1

                if not self.graph.has_edge(node_id, std_node_id):
                    self.graph.add_edge(
                        node_id,
                        std_node_id,
                        edge_type='CITES_STANDARD',
                        linking_method='reference',
                        confidence=1.0,
                        created_at=datetime.utcnow().isoformat()
                    )
                    self.edge_count += 1

    def _compute_statistics(self) -> Dict[str, Any]:
        """
        Compute graph statistics
        """
        stats = {
            'nodes': self.graph.number_of_nodes(),
            'edges': self.graph.number_of_edges(),
            'standards': 0,
            'clauses': 0,
            'requirements': 0,
            'external_standards': 0
        }

        for node_id, data in self.graph.nodes(data=True):
            node_type = data.get('node_type', '')
            if node_type == 'Standard':
                stats['standards'] += 1
            elif node_type == 'Clause':
                stats['clauses'] += 1
            elif node_type == 'Requirement':
                stats['requirements'] += 1
            elif node_type == 'ExternalStandard':
                stats['external_standards'] += 1

        return stats

    def _compute_checksum(self) -> str:
        """
        Compute deterministic checksum of graph
        """
        nodes = sorted(self.graph.nodes(data=True), key=lambda x: x[0])
        edges = sorted(self.graph.edges(data=True, keys=True),
                      key=lambda x: (x[0], x[1], x[2]))

        graph_repr = {
            'nodes': len(nodes),
            'edges': len(edges),
            'node_ids': [n[0] for n in nodes[:10]]  # Sample
        }

        canonical = json.dumps(graph_repr, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def save_graph(self, output_path: str):
        """
        Save graph to file
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Save as pickle for fast loading
        import pickle
        with open(output_path, 'wb') as f:
            pickle.dump(self.graph, f)

        logger.info(f"Graph saved to: {output_path}")

    def load_graph(self, input_path: str):
        """
        Load graph from file
        """
        import pickle
        with open(input_path, 'rb') as f:
            self.graph = pickle.load(f)

        self.node_count = self.graph.number_of_nodes()
        self.edge_count = self.graph.number_of_edges()
        
        # Restore manifest
        self.processed_files = self.graph.graph.get('processed_files', {})
        if isinstance(self.processed_files, list):
            # Migration
            self.processed_files = {f: {"size": 0, "mtime": 0} for f in self.processed_files}

        logger.info(f"Graph loaded: {self.node_count} nodes, {self.edge_count} edges. Processed files: {len(self.processed_files)}")

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive graph statistics
        """
        return self._compute_statistics()

    def export_json(self, output_path: str):
        """
        Export graph as JSON for external analysis
        """
        graph_data = {
            'nodes': [
                {'id': n, **self.graph.nodes[n]}
                for n in self.graph.nodes()
            ],
            'edges': [
                {'source': u, 'target': v, 'key': k, **data}
                for u, v, k, data in self.graph.edges(data=True, keys=True)
            ],
            'metadata': {
                'created_at': datetime.utcnow().isoformat(),
                'statistics': self._compute_statistics(),
                'checksum': self._compute_checksum()
            }
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(graph_data, f, indent=2)

        logger.info(f"Graph exported to JSON: {output_path}")

    def _get_edge_type_counts(self) -> Dict[str, int]:
        """
        Helper to get counts of edges by type
        """
        counts = {}
        for _, _, data in self.graph.edges(data=True):
            edge_type = data.get('edge_type', 'unknown')
            counts[edge_type] = counts.get(edge_type, 0) + 1
        return counts
