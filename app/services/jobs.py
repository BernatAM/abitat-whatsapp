import logging

from app.domain.models import ScheduledJob, utcnow
from app.integrations.email import EmailMockService
from app.repositories.memory import InMemoryJobRepository


logger = logging.getLogger(__name__)


class JobService:
    def __init__(
        self,
        job_repository: InMemoryJobRepository,
        email_service: EmailMockService,
    ) -> None:
        self.job_repository = job_repository
        self.email_service = email_service

    def schedule_reminder_45_days(self, phone: str) -> ScheduledJob:
        job = ScheduledJob.reminder_45_days(phone=phone)
        self.job_repository.add(job)
        logger.info(
            "Created reminder job job_id=%s phone=%s run_at=%s",
            job.id,
            phone,
            job.run_at.isoformat(),
        )
        return job

    def run_jobs(self, mode: str = "due") -> list[ScheduledJob]:
        now = utcnow()
        executed: list[ScheduledJob] = []
        for job in self.job_repository.list_all():
            if job.executed:
                continue
            if mode == "due" and job.run_at > now:
                continue
            logger.info("Running job job_id=%s type=%s phone=%s", job.id, job.job_type, job.phone)
            if job.job_type == "toner_reminder_email":
                self.email_service.send_reminder(job.phone)
            job.mark_executed()
            executed.append(job)
        return executed

