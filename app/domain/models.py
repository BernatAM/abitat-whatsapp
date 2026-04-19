from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class HistoryItem:
    timestamp: datetime
    direction: str
    text: str
    state_before: str
    state_after: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass
class ConversationState:
    phone: str
    current_state: str = "new"
    tags: list[str] = field(default_factory=list)
    printer_raw: str | None = None
    toner_type: str | None = None
    toner_units: int | None = None
    sage_customer_exists: bool | None = None
    delivery_address: str | None = None
    budget_email: str | None = None
    empty_pickup_requested: bool | None = None
    empty_units: int | None = None
    empty_type: str | None = None
    pickup_slot_text: str | None = None
    history: list[HistoryItem] = field(default_factory=list)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def add_tag(self, tag: str) -> bool:
        if tag in self.tags:
            return False
        self.tags.append(tag)
        self.updated_at = utcnow()
        return True

    def add_history(
        self,
        direction: str,
        text: str,
        state_before: str,
        state_after: str,
    ) -> None:
        self.history.append(
            HistoryItem(
                timestamp=utcnow(),
                direction=direction,
                text=text,
                state_before=state_before,
                state_after=state_after,
            )
        )
        self.updated_at = utcnow()

    def to_dict(self) -> dict[str, Any]:
        return {
            "phone": self.phone,
            "current_state": self.current_state,
            "tags": self.tags,
            "printer_raw": self.printer_raw,
            "toner_type": self.toner_type,
            "toner_units": self.toner_units,
            "sage_customer_exists": self.sage_customer_exists,
            "delivery_address": self.delivery_address,
            "budget_email": self.budget_email,
            "empty_pickup_requested": self.empty_pickup_requested,
            "empty_units": self.empty_units,
            "empty_type": self.empty_type,
            "pickup_slot_text": self.pickup_slot_text,
            "history": [item.to_dict() for item in self.history],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class ScheduledJob:
    id: str
    job_type: str
    phone: str
    run_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    executed: bool = False
    executed_at: datetime | None = None
    created_at: datetime = field(default_factory=utcnow)

    @classmethod
    def reminder_45_days(cls, phone: str) -> "ScheduledJob":
        return cls(
            id=str(uuid4()),
            job_type="toner_reminder_email",
            phone=phone,
            run_at=utcnow() + timedelta(days=45),
        )

    def mark_executed(self) -> None:
        self.executed = True
        self.executed_at = utcnow()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "job_type": self.job_type,
            "phone": self.phone,
            "run_at": self.run_at.isoformat(),
            "payload": self.payload,
            "executed": self.executed,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "created_at": self.created_at.isoformat(),
        }

