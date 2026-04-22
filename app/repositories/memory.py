from __future__ import annotations

from app.domain.models import ConversationState, ScheduledJob


class InMemoryConversationRepository:
    def __init__(self) -> None:
        self.conversations_by_phone: dict[str, ConversationState] = {}

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
