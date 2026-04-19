from app.integrations.email import EmailMockService
from app.integrations.sage import SageMockService
from app.repositories.memory import InMemoryConversationRepository, InMemoryJobRepository
from app.services.conversation import ConversationService
from app.services.jobs import JobService


conversation_repository = InMemoryConversationRepository()
job_repository = InMemoryJobRepository()
sage_service = SageMockService()
email_service = EmailMockService()
job_service = JobService(job_repository=job_repository, email_service=email_service)
conversation_service = ConversationService(
    conversation_repository=conversation_repository,
    sage_service=sage_service,
    job_service=job_service,
)

