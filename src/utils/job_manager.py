"""
Unified Job Management Utility
Handles in-memory job status, progress tracking, and background tasks.
"""
from typing import Dict, Any, Optional
from datetime import datetime
import uuid
from enum import Enum
from pydantic import BaseModel, Field

class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class JobEntry(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.PENDING
    current_step: str = "Initializing"
    progress_percent: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class JobManager:
    """
    Manages in-memory job states for background tasks.
    In a production system, this should be backed by Redis or a Database.
    """
    def __init__(self):
        self._jobs: Dict[str, JobEntry] = {}

    def create_job(self) -> str:
        """Create a new job and return its ID"""
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = JobEntry(job_id=job_id)
        return job_id

    def update_job(self, job_id: str, 
                   status: Optional[JobStatus] = None, 
                   current_step: Optional[str] = None, 
                   progress: Optional[float] = None,
                   result: Optional[Dict[str, Any]] = None,
                   error: Optional[str] = None):
        """Update job status and progress"""
        if job_id not in self._jobs:
            return

        job = self._jobs[job_id]
        if status:
            job.status = status
            if status == JobStatus.COMPLETED:
                job.completed_at = datetime.utcnow()
                job.progress_percent = 100.0
        if current_step:
            job.current_step = current_step
        if progress is not None:
            job.progress_percent = progress
        if result:
            job.result = result
        if error:
            job.error = error

    def get_job(self, job_id: str) -> Optional[JobEntry]:
        """Retrieve job details"""
        return self._jobs.get(job_id)

    def list_jobs(self) -> Dict[str, Any]:
        """List all managed jobs"""
        return {
            "total_jobs": len(self._jobs),
            "jobs": [job.model_dump() for job in self._jobs.values()]
        }
