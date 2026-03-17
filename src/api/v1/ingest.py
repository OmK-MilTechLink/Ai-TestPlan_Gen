"""
Endpoint 1: Data Ingestion from External Sources
Fetches standards documents from external API or local files
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from typing import List, Optional
import httpx
import json
import os
from pathlib import Path
import uuid
from datetime import datetime

from src.models.api_models import (
    ExternalDataSourceRequest,
    IngestionResponse,
    JobStatus,
    JobStatusResponse
)
from src.config import settings
from loguru import logger
from src.utils.job_manager import JobManager, JobStatus as JMStatus

router = APIRouter()

# Unified job manager for ingestion tasks
job_manager = JobManager()

# ==================== HELPER FUNCTIONS ====================

async def fetch_from_external_api(source_url: str, api_key: Optional[str], filters: dict) -> List[dict]:
    """Fetch standards documents from external API"""
    headers = {}
    if api_key: headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.get(str(source_url), headers=headers, params=filters)
            response.raise_for_status()
            data = response.json()
            return data['documents'] if isinstance(data, dict) and 'documents' in data else (data if isinstance(data, list) else [data])
        except httpx.HTTPError as e:
            logger.error(f"HTTP error: {e}")
            raise HTTPException(status_code=502, detail=f"External API error: {str(e)}")

def load_from_local_directory(data_dir: str) -> List[dict]:
    """Load JSON files from local data directory"""
    documents = []
    data_path = Path(data_dir)
    if not data_path.exists(): raise HTTPException(status_code=404, detail=f"Data directory not found: {data_dir}")
    json_files = list(data_path.rglob("*.json"))
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f); data['_source_file'] = str(json_file); documents.append(data)
        except Exception: continue
    return documents

async def process_ingestion_job(job_id: str, source_url: Optional[str], api_key: Optional[str], filters: dict, use_local: bool):
    """Background task to process ingestion"""
    try:
        job_manager.update_job(job_id, status=JMStatus.PROCESSING, current_step='Fetching documents')
        if use_local:
            source_dir = settings.input_json_dir if Path(settings.input_json_dir).exists() else settings.data_dir
            documents = load_from_local_directory(source_dir)
        else:
            documents = await fetch_from_external_api(source_url, api_key, filters)

        temp_dir = Path(settings.temp_dir) / job_id; temp_dir.mkdir(parents=True, exist_ok=True)
        for idx, doc in enumerate(documents):
            doc_id = doc.get('chunk_id', f'doc_{idx}')
            file_path = temp_dir / f"{doc_id.replace('/', '_').replace('::', '_')}.json"
            with open(file_path, 'w', encoding='utf-8') as f: json.dump(doc, f, indent=2)

        result = {'files_fetched': len(documents), 'temp_path': str(temp_dir)}
        job_manager.update_job(job_id, status=JMStatus.COMPLETED, result=result)
    except Exception as e:
        logger.exception(f"Ingestion job failed: {e}")
        job_manager.update_job(job_id, status=JMStatus.FAILED, error=str(e))

# ==================== ENDPOINTS ====================

@router.post("/fetch", response_model=IngestionResponse)
async def fetch_external_data(request: ExternalDataSourceRequest, background_tasks: BackgroundTasks):
    """**Fetch standards documents from external API**"""
    job_id = job_manager.create_job()
    background_tasks.add_task(process_ingestion_job, job_id, request.source_url, request.api_key, request.filters, use_local=False)
    return IngestionResponse(job_id=job_id, status=JobStatus.PENDING, message="Ingestion job started.", files_fetched=0, estimated_time_seconds=30)

@router.post("/local", response_model=IngestionResponse)
async def ingest_local_data(background_tasks: BackgroundTasks):
    """**Ingest standards documents from local data directory**"""
    job_id = job_manager.create_job()
    background_tasks.add_task(process_ingestion_job, job_id, None, None, {}, use_local=True)
    return IngestionResponse(job_id=job_id, status=JobStatus.PENDING, message="Local ingestion started.", files_fetched=0, estimated_time_seconds=10)

@router.post("/upload", response_model=IngestionResponse)
async def upload_documents(files: List[UploadFile] = File(...)):
    """**Upload standards documents directly (JSON files only)**"""
    job_id = job_manager.create_job()
    temp_dir = Path(settings.temp_dir) / job_id; temp_dir.mkdir(parents=True, exist_ok=True)
    uploaded_count = 0
    rejected_count = 0
    for file in files:
        if not file.filename.endswith('.json'):
            logger.warning(f"Rejected unsupported file type: {file.filename}")
            rejected_count += 1
            continue
        try:
            content = await file.read()
            with open(temp_dir / file.filename, 'wb') as f: f.write(content)
            uploaded_count += 1
        except Exception: continue
    
    result = {'files_fetched': uploaded_count, 'rejected': rejected_count, 'temp_path': str(temp_dir)}
    job_manager.update_job(job_id, status=JMStatus.COMPLETED, result=result, progress=100.0)
    message = f"Uploaded {uploaded_count} files"
    if rejected_count > 0:
        message += f" ({rejected_count} rejected — only .json files are supported)"
    return IngestionResponse(job_id=job_id, status=JobStatus.COMPLETED, message=message, files_fetched=uploaded_count)

@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_ingestion_status(job_id: str):
    """**Check status of an ingestion job**"""
    job = job_manager.get_job(job_id)
    if not job: raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        progress_percent=job.progress_percent,
        current_step=job.current_step,
        message=f"Ingestion job: {job.current_step}",
        result=job.result,
        error=job.error,
        timestamp=datetime.utcnow()
    )

@router.get("/list")
async def list_ingestion_jobs():
    """**List all ingestion jobs**"""
    return job_manager.list_jobs()
