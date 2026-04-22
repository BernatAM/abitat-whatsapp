from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.domain.models import ConversationState, HistoryItem, ScheduledJob


logger = logging.getLogger(__name__)


class SupabaseRestError(RuntimeError):
    pass


class SupabaseRestClient:
    def __init__(self, supabase_url: str, supabase_key: str) -> None:
        self.base_url = supabase_url.rstrip("/")
        self.key = supabase_key

    def get(self, table: str, params: dict[str, str] | None = None) -> Any:
        return self.request("GET", table, params=params)

    def post(
        self,
        table: str,
        payload: dict[str, Any] | list[dict[str, Any]],
        params: dict[str, str] | None = None,
        prefer: str = "return=representation",
    ) -> Any:
        return self.request("POST", table, payload=payload, params=params, prefer=prefer)

    def patch(
        self,
        table: str,
        payload: dict[str, Any],
        params: dict[str, str],
        prefer: str = "return=representation",
    ) -> Any:
        return self.request("PATCH", table, payload=payload, params=params, prefer=prefer)

    def delete(self, table: str, params: dict[str, str]) -> Any:
        return self.request("DELETE", table, params=params, prefer="return=minimal")

    def request(
        self,
        method: str,
        table: str,
        payload: dict[str, Any] | list[dict[str, Any]] | None = None,
        params: dict[str, str] | None = None,
        prefer: str | None = None,
    ) -> Any:
        query = f"?{urlencode(params)}" if params else ""
        url = f"{self.base_url}/rest/v1/{table}{query}"
        body = json.dumps(payload, default=str).encode("utf-8") if payload is not None else None
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        request = Request(url=url, data=body, method=method, headers=headers)
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise SupabaseRestError(f"Supabase REST {method} {table} failed: {exc.code} {error_body}") from exc
        except URLError as exc:
            raise SupabaseRestError(f"Supabase REST network error: {exc.reason}") from exc


class SupabaseConversationRepository:
    def __init__(self, client: SupabaseRestClient) -> None:
        self.client = client

    def get(self, phone: str) -> ConversationState | None:
        contact = self._get_contact(phone)
        if contact is None:
            return None
        flow = self._get_flow(contact["id"])
        if flow is None:
            return None
        return self._hydrate(contact, flow)

    def get_or_create(self, phone: str) -> tuple[ConversationState, bool]:
        existing = self.get(phone)
        if existing is not None:
            return existing, False

        contact = self._ensure_contact(phone)
        self._ensure_flow(contact["id"])
        conversation = self.get(phone)
        if conversation is None:
            raise RuntimeError(f"Failed to create Supabase conversation phone={phone}")
        conversation.current_state = "new"
        return conversation, True

    def save(self, conversation: ConversationState) -> ConversationState:
        contact = self._ensure_contact(conversation.phone)
        conversation.contact_id = contact["id"]
        self._ensure_flow(contact["id"])
        self._update_flow(contact["id"], conversation)
        self._update_contact(contact["id"], conversation)
        self._persist_tags(contact["id"], conversation.tags)
        self._persist_new_history(contact["id"], conversation)
        conversation.persisted_history_count = len(conversation.history)
        return conversation

    def reset(self, phone: str) -> ConversationState:
        contact = self._ensure_contact(phone)
        contact_id = contact["id"]
        self.client.delete("messages", {"contact_id": f"eq.{contact_id}"})
        self.client.delete("contact_tags", {"contact_id": f"eq.{contact_id}"})
        self.client.patch(
            "contact_flow_state",
            {
                "current_state": "awaiting_need_now",
                "is_closed": False,
                "printer_raw": None,
                "toner_type": None,
                "toner_units": None,
                "sage_customer_exists": None,
                "sage_customer_code": None,
                "delivery_address": None,
                "budget_email": None,
                "empty_pickup_requested": None,
                "empty_units": None,
                "empty_type": None,
                "pickup_slot_text": None,
                "last_inbound_message_at": None,
                "last_outbound_message_at": None,
                "last_flow_reset_at": datetime.utcnow().isoformat(),
            },
            {"contact_id": f"eq.{contact_id}"},
        )
        conversation = self.get(phone)
        if conversation is None:
            raise RuntimeError(f"Failed to reset Supabase conversation phone={phone}")
        conversation.current_state = "new"
        conversation.persisted_history_count = 0
        return conversation

    def list_all(self) -> list[ConversationState]:
        flows = self.client.get(
            "contact_flow_state",
            {
                "select": "*",
                "order": "updated_at.desc",
                "limit": "200",
            },
        )
        conversations: list[ConversationState] = []
        for flow in flows or []:
            contact = self._get_contact_by_id(flow["contact_id"])
            if contact is not None:
                conversations.append(self._hydrate(contact, flow))
        return conversations

    def _get_contact(self, phone: str) -> dict[str, Any] | None:
        rows = self.client.get(
            "contacts",
            {
                "phone": f"eq.{phone}",
                "select": "*",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def _get_contact_by_id(self, contact_id: int) -> dict[str, Any] | None:
        rows = self.client.get(
            "contacts",
            {"id": f"eq.{contact_id}", "select": "*", "limit": "1"},
        )
        return rows[0] if rows else None

    def _ensure_contact(self, phone: str) -> dict[str, Any]:
        contact = self._get_contact(phone)
        if contact is not None:
            return contact
        try:
            rows = self.client.post("contacts", {"phone": phone})
            return rows[0]
        except SupabaseRestError:
            contact = self._get_contact(phone)
            if contact is not None:
                return contact
            raise

    def _get_flow(self, contact_id: int) -> dict[str, Any] | None:
        rows = self.client.get(
            "contact_flow_state",
            {"contact_id": f"eq.{contact_id}", "select": "*", "limit": "1"},
        )
        return rows[0] if rows else None

    def _ensure_flow(self, contact_id: int) -> dict[str, Any]:
        flow = self._get_flow(contact_id)
        if flow is not None:
            return flow
        try:
            rows = self.client.post(
                "contact_flow_state",
                {"contact_id": contact_id, "current_state": "awaiting_need_now"},
            )
            return rows[0]
        except SupabaseRestError:
            flow = self._get_flow(contact_id)
            if flow is not None:
                return flow
            raise

    def _update_flow(self, contact_id: int, conversation: ConversationState) -> None:
        self.client.patch(
            "contact_flow_state",
            {
                "current_state": self._db_state(conversation.current_state),
                "is_closed": conversation.current_state.startswith("closed_"),
                "printer_raw": conversation.printer_raw,
                "toner_type": conversation.toner_type,
                "toner_units": conversation.toner_units,
                "sage_customer_exists": conversation.sage_customer_exists,
                "delivery_address": conversation.delivery_address,
                "budget_email": conversation.budget_email,
                "empty_pickup_requested": conversation.empty_pickup_requested,
                "empty_units": conversation.empty_units,
                "empty_type": conversation.empty_type,
                "pickup_slot_text": conversation.pickup_slot_text,
                "last_inbound_message_at": self._last_message_at(conversation, "inbound"),
                "last_outbound_message_at": self._last_message_at(conversation, "outbound"),
            },
            {"contact_id": f"eq.{contact_id}"},
        )

    def _update_contact(self, contact_id: int, conversation: ConversationState) -> None:
        payload: dict[str, Any] = {}
        if conversation.budget_email:
            payload["email"] = conversation.budget_email
        if conversation.delivery_address:
            payload["default_address"] = conversation.delivery_address
        if payload:
            self.client.patch("contacts", payload, {"id": f"eq.{contact_id}"})

    def _hydrate(self, contact: dict[str, Any], flow: dict[str, Any]) -> ConversationState:
        contact_id = contact["id"]
        tags = self._get_tags(contact_id)
        history = self._get_history(contact_id)
        current_state = flow["current_state"]
        if not history:
            current_state = "new"
        return ConversationState(
            phone=contact["phone"],
            contact_id=contact_id,
            current_state=current_state,
            tags=tags,
            printer_raw=flow.get("printer_raw"),
            toner_type=flow.get("toner_type"),
            toner_units=flow.get("toner_units"),
            sage_customer_exists=flow.get("sage_customer_exists"),
            delivery_address=flow.get("delivery_address"),
            budget_email=flow.get("budget_email") or contact.get("email"),
            empty_pickup_requested=flow.get("empty_pickup_requested"),
            empty_units=flow.get("empty_units"),
            empty_type=flow.get("empty_type"),
            pickup_slot_text=flow.get("pickup_slot_text"),
            history=history,
            created_at=self._parse_dt(flow["created_at"]),
            updated_at=self._parse_dt(flow["updated_at"]),
            persisted_history_count=len(history),
        )

    def _get_tags(self, contact_id: int) -> list[str]:
        rows = self.client.get(
            "contact_tags",
            {
                "contact_id": f"eq.{contact_id}",
                "select": "tags(code)",
                "order": "created_at.asc",
            },
        )
        return [row["tags"]["code"] for row in rows or [] if row.get("tags")]

    def _get_history(self, contact_id: int) -> list[HistoryItem]:
        rows = self.client.get(
            "messages",
            {
                "contact_id": f"eq.{contact_id}",
                "select": "*",
                "order": "created_at.asc,id.asc",
            },
        )
        return [
            HistoryItem(
                timestamp=self._parse_dt(row["created_at"]),
                direction=row["direction"],
                text=row.get("text_content") or "",
                state_before=row.get("state_before") or "",
                state_after=row.get("state_after") or "",
                wa_message_id=row.get("wa_message_id"),
                wa_conversation_id=row.get("wa_conversation_id"),
                wa_status=row.get("wa_status"),
                message_type=row.get("message_type") or "text",
                raw_payload=row.get("raw_payload"),
            )
            for row in rows or []
        ]

    def _persist_tags(self, contact_id: int, tags: list[str]) -> None:
        for tag in tags:
            tag_id = self._ensure_tag(tag)
            try:
                self.client.post(
                    "contact_tags",
                    {"contact_id": contact_id, "tag_id": tag_id},
                    prefer="return=minimal",
                )
            except SupabaseRestError as exc:
                if "duplicate key" not in str(exc):
                    raise

    def _ensure_tag(self, code: str) -> int:
        rows = self.client.get("tags", {"code": f"eq.{code}", "select": "id", "limit": "1"})
        if rows:
            return rows[0]["id"]
        try:
            rows = self.client.post("tags", {"code": code})
            return rows[0]["id"]
        except SupabaseRestError:
            rows = self.client.get("tags", {"code": f"eq.{code}", "select": "id", "limit": "1"})
            if rows:
                return rows[0]["id"]
            raise

    def _persist_new_history(self, contact_id: int, conversation: ConversationState) -> None:
        for item in conversation.history[conversation.persisted_history_count :]:
            payload = {
                "contact_id": contact_id,
                "direction": item.direction,
                "provider": "whatsapp_cloud_api",
                "wa_message_id": item.wa_message_id,
                "wa_conversation_id": item.wa_conversation_id,
                "wa_status": item.wa_status,
                "message_type": item.message_type,
                "text_content": item.text,
                "raw_payload": item.raw_payload,
                "state_before": item.state_before,
                "state_after": item.state_after,
                "created_at": item.timestamp.isoformat(),
            }
            try:
                self.client.post("messages", payload, prefer="return=minimal")
            except SupabaseRestError as exc:
                if item.wa_message_id and "duplicate key" in str(exc):
                    continue
                raise

    def _db_state(self, state: str) -> str:
        return "awaiting_need_now" if state == "new" else state

    def _last_message_at(self, conversation: ConversationState, direction: str) -> str | None:
        timestamps = [item.timestamp for item in conversation.history if item.direction == direction]
        return max(timestamps).isoformat() if timestamps else None

    def _parse_dt(self, value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))


class SupabaseJobRepository:
    def __init__(self, client: SupabaseRestClient) -> None:
        self.client = client

    def add(self, job: ScheduledJob) -> ScheduledJob:
        contact = self._ensure_contact(job.phone)
        rows = self.client.post(
            "scheduled_jobs",
            {
                "contact_id": contact["id"],
                "job_type": job.job_type,
                "payload": job.payload,
                "run_at": job.run_at.isoformat(),
            },
        )
        row = rows[0]
        job.id = str(row["id"])
        job.status = row["status"]
        job.created_at = self._parse_dt(row["created_at"])
        return job

    def list_all(self) -> list[ScheduledJob]:
        rows = self.client.get(
            "scheduled_jobs",
            {
                "select": "*,contacts(phone)",
                "order": "run_at.asc",
                "limit": "500",
            },
        )
        return [self._job_from_row(row) for row in rows or []]

    def mark_executed(self, job: ScheduledJob) -> None:
        self.client.patch(
            "scheduled_jobs",
            {
                "status": "done",
                "executed_at": job.executed_at.isoformat() if job.executed_at else datetime.utcnow().isoformat(),
                "attempts": job.attempts + 1,
            },
            {"id": f"eq.{job.id}"},
            prefer="return=minimal",
        )

    def _ensure_contact(self, phone: str) -> dict[str, Any]:
        rows = self.client.get(
            "contacts",
            {"phone": f"eq.{phone}", "select": "*", "limit": "1"},
        )
        if rows:
            return rows[0]
        try:
            rows = self.client.post("contacts", {"phone": phone})
            return rows[0]
        except SupabaseRestError:
            rows = self.client.get(
                "contacts",
                {"phone": f"eq.{phone}", "select": "*", "limit": "1"},
            )
            if rows:
                return rows[0]
            raise

    def _job_from_row(self, row: dict[str, Any]) -> ScheduledJob:
        return ScheduledJob(
            id=str(row["id"]),
            job_type=row["job_type"],
            phone=(row.get("contacts") or {}).get("phone", ""),
            payload=row.get("payload") or {},
            run_at=self._parse_dt(row["run_at"]),
            executed=row["status"] == "done",
            executed_at=self._parse_dt(row["executed_at"]) if row.get("executed_at") else None,
            status=row["status"],
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
            last_error=row.get("last_error"),
            created_at=self._parse_dt(row["created_at"]),
        )

    def _parse_dt(self, value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))


class SupabaseProcessedEventRepository:
    def __init__(self, client: SupabaseRestClient) -> None:
        self.client = client

    def try_register(
        self,
        provider: str,
        provider_event_id: str,
        event_type: str | None,
        payload: dict[str, Any],
    ) -> bool:
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        try:
            self.client.post(
                "processed_events",
                {
                    "provider": provider,
                    "provider_event_id": provider_event_id,
                    "event_type": event_type,
                    "payload_hash": payload_hash,
                },
                prefer="return=minimal",
            )
            return True
        except SupabaseRestError as exc:
            if "duplicate key" in str(exc):
                return False
            raise
