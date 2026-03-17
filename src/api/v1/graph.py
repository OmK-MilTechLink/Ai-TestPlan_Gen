"""
Endpoint 2: Knowledge Graph Construction
Builds multi-layer knowledge graph from ingested documents
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional
import uuid
from datetime import datetime
from pathlib import Path

from src.models.api_models import (
    GraphBuildResponse,
    JobStatus,
    JobStatusResponse
)
from src.config import settings
from src.core.graph_builder import KnowledgeGraphBuilder
from src.core.semantic_search import SemanticSearchEngine
from loguru import logger

router = APIRouter()

from src.utils.job_manager import JobManager, JobStatus as JMStatus

router = APIRouter()

# Unified job manager for graph tasks
job_manager = JobManager()

class GraphBuildRequest(BaseModel):
    """Request to build knowledge graph"""
    ingestion_job_id: str = Field(..., description="Job ID from ingestion")
    enable_structural_links: bool = Field(default=True)
    enable_semantic_links: bool = Field(default=True)
    enable_reference_links: bool = Field(default=True)
    semantic_threshold: float = Field(default=0.75, ge=0.0, le=1.0)

# Global graph builder and search engine
graph_builder = None
search_engine = None

async def process_graph_building(job_id: str, request: GraphBuildRequest):
    """Background task to build knowledge graph"""
    global graph_builder, search_engine
    try:
        job_manager.update_job(job_id, status=JMStatus.PROCESSING, current_step='Initializing builder', progress=10.0)
        graph_builder = KnowledgeGraphBuilder(seed=42)
        
        from src.api.v1.ingest import job_manager as ingest_jm
        ingest_job = ingest_jm.get_job(request.ingestion_job_id)
        data_path = ingest_job.result.get('temp_path', settings.data_dir) if ingest_job and ingest_job.result else settings.data_dir

        job_manager.update_job(job_id, current_step='Building structure', progress=20.0)
        result = graph_builder.build_from_directory(data_path=data_path, enable_structural=request.enable_structural_links, enable_reference=request.enable_reference_links)

        if request.enable_semantic_links:
            job_manager.update_job(job_id, current_step='Building semantic index', progress=70.0)
            search_engine = SemanticSearchEngine(model_name=settings.embedding_model, vector_db_path=settings.vector_db_path, seed=42)
            search_engine.index_graph(graph_builder.graph)

        job_manager.update_job(job_id, current_step='Saving graph', progress=90.0)
        g_path = Path(settings.graph_storage_path) / f"{job_id}.pkl"
        j_path = Path(settings.graph_storage_path) / f"{job_id}.json"
        graph_builder.save_graph(str(g_path)); graph_builder.export_json(str(j_path))

        res_payload = {**result, 'graph_path': str(g_path), 'json_path': str(j_path)}
        job_manager.update_job(job_id, status=JMStatus.COMPLETED, result=res_payload)
    except Exception as e:
        logger.exception(f"Graph build failed: {e}")
        job_manager.update_job(job_id, status=JMStatus.FAILED, error=str(e))

@router.post("/build", response_model=GraphBuildResponse)
async def build_knowledge_graph(request: GraphBuildRequest, background_tasks: BackgroundTasks):
    """**Endpoint 2: Build Knowledge Graph**"""
    job_id = job_manager.create_job()
    background_tasks.add_task(process_graph_building, job_id, request)
    return GraphBuildResponse(job_id=job_id, status=JobStatus.PENDING, message="Graph building started.", nodes_created=0, edges_created=0, graph_checksum="", timestamp=datetime.utcnow())

@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_graph_status(job_id: str):
    """**Check graph building status**"""
    job = job_manager.get_job(job_id)
    if not job: raise HTTPException(404, f"Job {job_id} not found")
    return JobStatusResponse(
        job_id=job.job_id, 
        status=job.status, 
        progress_percent=job.progress_percent, 
        current_step=job.current_step, 
        message=f"Graph building: {job.current_step}", 
        result=job.result, 
        error=job.error,
        timestamp=datetime.utcnow()
    )

@router.get("/statistics")
async def get_graph_statistics():
    """**Get graph statistics**"""
    if not graph_builder: raise HTTPException(404, "Graph not built")
    return {"statistics": graph_builder.get_statistics(), "graph_checksum": graph_builder._compute_checksum(), "timestamp": datetime.utcnow().isoformat()}

@router.get("/export/{job_id}")
async def export_graph(job_id: str):
    """**Export knowledge graph**"""
    job = job_manager.get_job(job_id)
    if not job or job.status != JMStatus.COMPLETED: raise HTTPException(400, "Job not completed")
    f_path = job.result.get('json_path', '')
    if not Path(f_path).exists(): raise HTTPException(404, "File not found")
    return FileResponse(path=f_path, filename=f"graph_{job_id}.json", media_type="application/json")

@router.get("/list")
async def list_graph_jobs():
    """**List all graph building jobs**"""
    return job_manager.list_jobs()

@router.post("/load/{job_id}")
async def load_existing_graph(job_id: str):
    """**Load a previously built graph**"""
    global graph_builder, search_engine
    g_path = Path(settings.graph_storage_path) / f"{job_id}.pkl"
    if not g_path.exists(): raise HTTPException(404, "Graph not found")
    try:
        graph_builder = KnowledgeGraphBuilder(); graph_builder.load_graph(str(g_path))
        search_engine = SemanticSearchEngine(model_name=settings.embedding_model, vector_db_path=settings.vector_db_path, seed=42)
        return {"message": "Graph loaded", "job_id": job_id, "statistics": graph_builder.get_statistics()}
    except Exception as e:
        logger.exception(f"Load failed: {e}")
        raise HTTPException(500, str(e))
