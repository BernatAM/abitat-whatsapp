from app.integrations.email import EmailMockService, SmtpEmailService
from app.integrations.whatsapp import WhatsAppCloudClient
from app.repositories.memory import (
    InMemoryConversationRepository,
    InMemoryJobRepository,
    NoopProcessedEventRepository,
)
from app.services.config import Settings
from app.services.conversation import ConversationService
from app.services.jobs import JobService


settings = Settings.from_env()
if settings.supabase_url and settings.supabase_key:
    from app.repositories.supabase_rest import (
        SupabaseConversationRepository,
        SupabaseJobRepository,
        SupabaseProcessedEventRepository,
        SupabaseRestClient,
    )

    db_pool = None
    supabase_client = SupabaseRestClient(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_key,
    )
    conversation_repository = SupabaseConversationRepository(supabase_client)
    job_repository = SupabaseJobRepository(supabase_client)
    processed_event_repository = SupabaseProcessedEventRepository(supabase_client)
elif settings.database_url:
    from app.repositories.postgres import (
        PostgresConversationRepository,
        PostgresJobRepository,
        PostgresProcessedEventRepository,
        build_pool,
    )

    db_pool = build_pool(settings.database_url)
    conversation_repository = PostgresConversationRepository(db_pool)
    job_repository = PostgresJobRepository(db_pool)
    processed_event_repository = PostgresProcessedEventRepository(db_pool)
else:
    db_pool = None
    supabase_client = None
    conversation_repository = InMemoryConversationRepository()
    job_repository = InMemoryJobRepository()
    processed_event_repository = NoopProcessedEventRepository()

if settings.smtp_host and settings.smtp_from_email and settings.smtp_to_email:
    email_service = SmtpEmailService(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        from_email=settings.smtp_from_email,
        to_email=settings.smtp_to_email,
        use_tls=settings.smtp_use_tls,
        use_ssl=settings.smtp_use_ssl,
    )
else:
    email_service = EmailMockService()
whatsapp_client = WhatsAppCloudClient(settings=settings)
job_service = JobService(job_repository=job_repository, email_service=email_service)
conversation_service = ConversationService(
    conversation_repository=conversation_repository,
    job_service=job_service,
    customer_service_phone=settings.customer_service_phone,
)
