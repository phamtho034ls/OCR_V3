"""
Job Repository in-memory có thread-lock để quản lý tiến trình bền vững và an toàn.
"""
import threading
from typing import Dict, List, Optional
from datetime import datetime
from ...domain.models import Job, JobStatus
from ...application.ports import JobRepositoryPort


class InMemoryJobRepository(JobRepositoryPort):
    def __init__(self):
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, job: Job) -> Job:
        with self._lock:
            self._jobs[job.job_id] = job
            return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job: Job) -> Job:
        with self._lock:
            job.updated_at = datetime.utcnow()
            self._jobs[job.job_id] = job
            return job

    def list_all(self, limit: int = 50, offset: int = 0) -> List[Job]:
        with self._lock:
            all_jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            return all_jobs[offset: offset + limit]
