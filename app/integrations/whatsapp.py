from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.services.config import Settings


logger = logging.getLogger(__name__)


@dataclass
class IncomingWhatsAppMessage:
    phone: str
    text: str
    raw: dict[str, Any]
    message_id: str | None = None
    conversation_id: str | None = None


class WhatsAppCloudClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_enabled(self) -> bool:
        return self.settings.whatsapp_send_enabled

    def send_message(self, to_phone: str, text: str) -> dict[str, Any] | None:
        buttons = buttons_for_text(text)
        if buttons:
            return self.send_button_message(to_phone=to_phone, text=text, buttons=buttons)
        return self.send_text_message(to_phone=to_phone, text=text)

    def send_text_message(self, to_phone: str, text: str) -> dict[str, Any] | None:
        if not self.is_enabled():
            logger.info(
                "WhatsApp send skipped because credentials are not configured phone=%s",
                to_phone,
            )
            return None

        url = (
            f"https://graph.facebook.com/{self.settings.whatsapp_graph_version}/"
            f"{self.settings.whatsapp_phone_number_id}/messages"
        )
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": text},
        }
        request = Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.whatsapp_access_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                raw_response = response.read().decode("utf-8")
                logger.info("WhatsApp outbound sent phone=%s response=%s", to_phone, raw_response)
                return json.loads(raw_response) if raw_response else {}
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            logger.exception(
                "WhatsApp outbound HTTP error phone=%s status=%s body=%s",
                to_phone,
                exc.code,
                error_body,
            )
            raise RuntimeError(f"WhatsApp send failed with status {exc.code}: {error_body}") from exc
        except URLError as exc:
            logger.exception("WhatsApp outbound network error phone=%s", to_phone)
            raise RuntimeError(f"WhatsApp send failed: {exc.reason}") from exc

    def send_button_message(
        self,
        to_phone: str,
        text: str,
        buttons: list[dict[str, str]],
    ) -> dict[str, Any] | None:
        if not self.is_enabled():
            logger.info(
                "WhatsApp button send skipped because credentials are not configured phone=%s",
                to_phone,
            )
            return None

        url = (
            f"https://graph.facebook.com/{self.settings.whatsapp_graph_version}/"
            f"{self.settings.whatsapp_phone_number_id}/messages"
        )
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": text},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": button["id"], "title": button["title"]},
                        }
                        for button in buttons
                    ]
                },
            },
        }
        request = Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.whatsapp_access_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                raw_response = response.read().decode("utf-8")
                logger.info("WhatsApp outbound buttons sent phone=%s response=%s", to_phone, raw_response)
                return json.loads(raw_response) if raw_response else {}
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            logger.exception(
                "WhatsApp outbound button HTTP error phone=%s status=%s body=%s",
                to_phone,
                exc.code,
                error_body,
            )
            raise RuntimeError(f"WhatsApp button send failed with status {exc.code}: {error_body}") from exc
        except URLError as exc:
            logger.exception("WhatsApp outbound button network error phone=%s", to_phone)
            raise RuntimeError(f"WhatsApp button send failed: {exc.reason}") from exc


def parse_meta_webhook_messages(payload: dict[str, Any]) -> list[IncomingWhatsAppMessage]:
    parsed_messages: list[IncomingWhatsAppMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                text_body = extract_message_text(message)
                if not text_body:
                    continue
                from_phone = message.get("from")
                if not from_phone:
                    continue
                parsed_messages.append(
                    IncomingWhatsAppMessage(
                        phone=from_phone,
                        text=text_body,
                        raw=message,
                        message_id=message.get("id"),
                        conversation_id=(message.get("context") or {}).get("id"),
                    )
                )
    return parsed_messages


def extract_message_text(message: dict[str, Any]) -> str | None:
    message_type = message.get("type")
    if message_type == "text":
        return (message.get("text") or {}).get("body")
    if message_type == "button":
        button = message.get("button") or {}
        return button.get("text") or button.get("payload")
    if message_type == "interactive":
        interactive = message.get("interactive") or {}
        if interactive.get("type") == "button_reply":
            reply = interactive.get("button_reply") or {}
            return reply.get("id") or reply.get("title")
    return None


YES_NO_BUTTONS = [
    {"id": "YES", "title": "Sí"},
    {"id": "NO", "title": "No"},
]

TONER_TYPE_BUTTONS = [
    {"id": "TONER_TYPE_ECOLOGICO", "title": "Ecológico Ábitat"},
    {"id": "TONER_TYPE_ORIGINAL", "title": "Original"},
    {"id": "TONER_TYPE_COMPATIBLE", "title": "Compatible"},
]


def buttons_for_text(text: str) -> list[dict[str, str]] | None:
    if text in {
        "Hola 👋 ¿Necesitas tóner ahora mismo?",
        "Antes de cerrar 😊 ¿Necesitas que te recojamos los cartuchos vacíos? (Sí/No)",
        "¿Quieres que te recojamos también los cartuchos vacíos? (Sí/No)",
    }:
        return YES_NO_BUTTONS
    if text in {
        "Genial. ¿Qué tipo de tóner prefieres?\nOpciones: Ecológico Ábitat / Original / Compatible",
        "¿Qué tipo son? Opciones: Ecológico Ábitat / Original / Compatible",
        "¿Son ecológicos Ábitat, originales o compatibles?",
    }:
        return TONER_TYPE_BUTTONS
    return None
