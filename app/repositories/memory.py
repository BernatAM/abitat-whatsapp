from __future__ import annotations

from app.domain.models import ConversationState, ScheduledJob


class InMemoryConversationRepository:
    def __init__(self) -> None:
        self.conversations_by_phone: dict[str, ConversationState] = {}
        self.existing_customer_phones: set[str] = set()
        self.toner_orders_by_phone: dict[str, dict] = {}

    def get(self, phone: str) -> ConversationState | None:
        return self.conversations_by_phone.get(phone)

    def get_or_create(self, phone: str) -> tuple[ConversationState, bool]:
        existing = self.get(phone)
        if existing is not None:
            return existing, False
        conversation = ConversationState(phone=phone)
        self.save(conversation)
        return conversation, True

    def save(self, conversation: ConversationState) -> ConversationState:
        self.conversations_by_phone[conversation.phone] = conversation
        return conversation

    def reset(self, phone: str) -> ConversationState:
        conversation = ConversationState(phone=phone)
        self.save(conversation)
        return conversation

    def list_all(self) -> list[ConversationState]:
        return sorted(
            self.conversations_by_phone.values(),
            key=lambda item: item.updated_at,
            reverse=True,
        )

    def customer_exists(self, phone: str) -> bool:
        return phone in self.existing_customer_phones

    def mark_customer_exists(self, phone: str) -> None:
        self.existing_customer_phones.add(phone)

    def upsert_toner_order(self, conversation: ConversationState) -> None:
        if not self._has_order_data(conversation):
            return
        self.toner_orders_by_phone[conversation.phone] = {
            "phone": conversation.phone,
            "printer_brand": conversation.printer_brand,
            "printer_model": conversation.printer_model,
            "printer_raw": conversation.printer_raw,
            "toner_type": conversation.toner_type,
            "toner_units": conversation.toner_units,
            "customer_exists": conversation.sage_customer_exists,
            "delivery_address": conversation.delivery_address,
            "budget_email": conversation.budget_email,
            "status": conversation.current_state,
            "empty_pickup_requested": conversation.empty_pickup_requested,
            "empty_units": conversation.empty_units,
            "empty_type": conversation.empty_type,
            "pickup_slot_text": conversation.pickup_slot_text,
        }

    def _has_order_data(self, conversation: ConversationState) -> bool:
        return any(
            [
                conversation.toner_units,
                conversation.empty_pickup_requested,
                conversation.empty_units,
                conversation.pickup_slot_text,
            ]
        )


class InMemoryJobRepository:
    def __init__(self) -> None:
        self.scheduled_jobs: list[ScheduledJob] = []

    def add(self, job: ScheduledJob) -> ScheduledJob:
        self.scheduled_jobs.append(job)
        return job

    def list_all(self) -> list[ScheduledJob]:
        return list(self.scheduled_jobs)

    def mark_executed(self, job: ScheduledJob) -> None:
        return None


class NoopProcessedEventRepository:
    def try_register(
        self,
        provider: str,
        provider_event_id: str,
        event_type: str | None,
        payload: dict,
    ) -> bool:
        return True
