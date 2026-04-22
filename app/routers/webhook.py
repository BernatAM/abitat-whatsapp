import logging

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.domain.schemas import WebhookResponse, WhatsAppWebhookRequest
from app.integrations.whatsapp import parse_meta_webhook_messages
from app.services.container import (
    conversation_service,
    processed_event_repository,
    settings,
    whatsapp_client,
)


router = APIRouter(prefix="/webhook", tags=["webhook"])
logger = logging.getLogger(__name__)


@router.get("/whatsapp")
def verify_whatsapp_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> Response:
    expected_token = settings.whatsapp_verify_token
    if hub_mode != "subscribe" or not expected_token or hub_verify_token != expected_token:
        raise HTTPException(status_code=403, detail="Webhook verification failed")
    return Response(content=hub_challenge, media_type="text/plain")


@router.post("/whatsapp", response_model=WebhookResponse)
async def whatsapp_webhook(request: Request) -> WebhookResponse:
    payload = await request.json()

    if "message" in payload:
        parsed = WhatsAppWebhookRequest.model_validate(payload)
        conversation, replies = conversation_service.process_incoming_message(
            phone=parsed.message.from_phone,
            text=parsed.message.text,
        )
        return WebhookResponse(
            phone=conversation.phone,
            state=conversation.current_state,
            messages_sent=replies,
        )

    incoming_messages = parse_meta_webhook_messages(payload)
    if not incoming_messages:
        return WebhookResponse(phone="", state="ignored", messages_sent=[])

    current_phone = incoming_messages[0].phone
    current_state = "ignored"
    all_replies: list[str] = []

    for incoming in incoming_messages:
        if incoming.message_id:
            registered = processed_event_repository.try_register(
                provider="whatsapp_cloud_api",
                provider_event_id=incoming.message_id,
                event_type="message.text",
                payload=incoming.raw,
            )
            if not registered:
                logger.info("Ignoring duplicate WhatsApp webhook event message_id=%s", incoming.message_id)
                continue
        conversation, replies = conversation_service.process_incoming_message(
            phone=incoming.phone,
            text=incoming.text,
            wa_message_id=incoming.message_id,
            wa_conversation_id=incoming.conversation_id,
            raw_payload=incoming.raw,
        )
        current_phone = conversation.phone
        current_state = conversation.current_state
        all_replies.extend(replies)
        for reply in replies:
            try:
                whatsapp_client.send_text_message(to_phone=incoming.phone, text=reply)
            except RuntimeError as exc:
                logger.error("Failed to send WhatsApp reply phone=%s error=%s", incoming.phone, exc)

    return WebhookResponse(
        phone=current_phone,
        state=current_state,
        messages_sent=all_replies,
    )
