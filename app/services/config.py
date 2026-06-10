from dataclasses import dataclass
import os


@dataclass
class Settings:
    database_url: str | None
    supabase_url: str | None
    supabase_key: str | None
    whatsapp_verify_token: str | None
    whatsapp_access_token: str | None
    whatsapp_phone_number_id: str | None
    whatsapp_graph_version: str
    whatsapp_send_enabled: bool
    customer_service_phone: str
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_from_email: str | None
    smtp_to_email: str | None
    smtp_use_tls: bool
    smtp_use_ssl: bool

    @classmethod
    def from_env(cls) -> "Settings":
        access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
        phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        return cls(
            database_url=os.getenv("DATABASE_URL"),
            supabase_url=os.getenv("SUPABASE_URL"),
            supabase_key=os.getenv("SUPABASE_KEY"),
            whatsapp_verify_token=os.getenv("WHATSAPP_VERIFY_TOKEN"),
            whatsapp_access_token=access_token,
            whatsapp_phone_number_id=phone_number_id,
            whatsapp_graph_version=os.getenv("WHATSAPP_GRAPH_VERSION", "v23.0"),
            whatsapp_send_enabled=bool(access_token and phone_number_id),
            customer_service_phone=os.getenv("CUSTOMER_SERVICE_PHONE", "900 000 000"),
            smtp_host=os.getenv("SMTP_HOST"),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_username=os.getenv("SMTP_USERNAME"),
            smtp_password=os.getenv("SMTP_PASSWORD"),
            smtp_from_email=os.getenv("SMTP_FROM_EMAIL"),
            smtp_to_email=os.getenv("SMTP_TO_EMAIL"),
            smtp_use_tls=os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes", "si"},
            smtp_use_ssl=os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes", "si"},
        )
