from fastapi import APIRouter

from app.domain.schemas import WebhookResponse, WhatsAppWebhookRequest
from app.services.container import conversation_service


router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("/whatsapp", response_model=WebhookResponse)
def whatsapp_webhook(payload: WhatsAppWebhookRequest) -> WebhookResponse:
    conversation, replies = conversation_service.process_incoming_message(
        phone=payload.message.from_phone,
        text=payload.message.text,
    )
    return WebhookResponse(
        phone=conversation.phone,
        state=conversation.current_state,
        messages_sent=replies,
    )

