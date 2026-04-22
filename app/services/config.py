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
        )
