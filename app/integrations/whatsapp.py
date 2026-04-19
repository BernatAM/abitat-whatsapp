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


class WhatsAppCloudClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_enabled(self) -> bool:
        return self.settings.whatsapp_send_enabled

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


def parse_meta_webhook_messages(payload: dict[str, Any]) -> list[IncomingWhatsAppMessage]:
    parsed_messages: list[IncomingWhatsAppMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                if message.get("type") != "text":
                    continue
                text_body = (message.get("text") or {}).get("body")
                from_phone = message.get("from")
                if not from_phone or not text_body:
                    continue
                parsed_messages.append(
                    IncomingWhatsAppMessage(
                        phone=from_phone,
                        text=text_body,
                        raw=message,
                    )
                )
    return parsed_messages

