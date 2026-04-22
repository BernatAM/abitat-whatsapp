from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

from psycopg import rows
from psycopg_pool import ConnectionPool

from app.domain.models import ConversationState, HistoryItem, ScheduledJob, utcnow


logger = logging.getLogger(__name__)


def build_pool(database_url: str) -> ConnectionPool:
    return ConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=10,
        kwargs={"row_factory": rows.dict_row},
        open=True,
    )


class PostgresConversationRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def get(self, phone: str) -> ConversationState | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                select
                    c.id as contact_id,
                    c.phone,
                    c.email,
                    c.default_address,
                    c.created_at as contact_created_at,
                    c.updated_at as contact_updated_at,
                    s.current_state,
                    s.customer_existed_before_flow,
                    s.printer_brand,
                    s.printer_model,
                    s.printer_raw,
                    s.toner_type,
                    s.toner_units,
                    s.sage_customer_exists,
                    s.delivery_address,
                    s.budget_email,
                    s.empty_pickup_requested,
                    s.empty_units,
                    s.empty_type,
                    s.pickup_slot_text,
                    s.created_at,
                    s.updated_at
                from contacts c
                join contact_flow_state s on s.contact_id = c.id
                where c.phone = %s
                """,
                (phone,),
            ).fetchone()
            if row is None:
                return None
            return self._hydrate_conversation(conn, row)

    def get_or_create(self, phone: str) -> tuple[ConversationState, bool]:
        existing = self.get(phone)
        if existing is not None:
            return existing, False

        with self.pool.connection() as conn:
            with conn.transaction():
                existing_contact = conn.execute(
                    "select id from contacts where phone = %s",
                    (phone,),
                ).fetchone()
                contact_existed_before_flow = existing_contact is not None
                contact = conn.execute(
                    """
                    insert into contacts (phone)
                    values (%s)
                    on conflict (phone) do update set phone = excluded.phone
                    returning id, phone, created_at, updated_at
                    """,
                    (phone,),
                ).fetchone()
                conn.execute(
                    """
                    insert into contact_flow_state (
                        contact_id,
                        current_state,
                        customer_existed_before_flow
                    )
                    values (%s, 'awaiting_need_now', %s)
                    on conflict (contact_id) do nothing
                    """,
                    (contact["id"], contact_existed_before_flow),
                )
        conversation = self.get(phone)
        if conversation is None:
            raise RuntimeError(f"Failed to create conversation for phone={phone}")
        conversation.current_state = "new"
        return conversation, True

    def save(self, conversation: ConversationState) -> ConversationState:
        if conversation.contact_id is None:
            conversation, _ = self.get_or_create(conversation.phone)

        with self.pool.connection() as conn:
            with conn.transaction():
                contact_id = self._ensure_contact(conn, conversation.phone)
                conversation.contact_id = contact_id
                conn.execute(
                    """
                    insert into contact_flow_state (
                        contact_id,
                        current_state,
                        is_closed,
                        printer_raw,
                        printer_brand,
                        printer_model,
                        toner_type,
                        toner_units,
                        sage_customer_exists,
                        delivery_address,
                        budget_email,
                        empty_pickup_requested,
                        empty_units,
                        empty_type,
                        pickup_slot_text,
                        last_inbound_message_at,
                        last_outbound_message_at
                    )
                    values (
                        %(contact_id)s,
                        %(current_state)s,
                        %(is_closed)s,
                        %(printer_raw)s,
                        %(printer_brand)s,
                        %(printer_model)s,
                        %(toner_type)s,
                        %(toner_units)s,
                        %(sage_customer_exists)s,
                        %(delivery_address)s,
                        %(budget_email)s,
                        %(empty_pickup_requested)s,
                        %(empty_units)s,
                        %(empty_type)s,
                        %(pickup_slot_text)s,
                        %(last_inbound_message_at)s,
                        %(last_outbound_message_at)s
                    )
                    on conflict (contact_id) do update set
                        current_state = excluded.current_state,
                        is_closed = excluded.is_closed,
                        printer_raw = excluded.printer_raw,
                        printer_brand = excluded.printer_brand,
                        printer_model = excluded.printer_model,
                        toner_type = excluded.toner_type,
                        toner_units = excluded.toner_units,
                        sage_customer_exists = excluded.sage_customer_exists,
                        delivery_address = excluded.delivery_address,
                        budget_email = excluded.budget_email,
                        empty_pickup_requested = excluded.empty_pickup_requested,
                        empty_units = excluded.empty_units,
                        empty_type = excluded.empty_type,
                        pickup_slot_text = excluded.pickup_slot_text,
                        last_inbound_message_at = excluded.last_inbound_message_at,
                        last_outbound_message_at = excluded.last_outbound_message_at
                    """,
                    self._flow_params(contact_id, conversation),
                )
                conn.execute(
                    """
                    update contacts
                    set email = coalesce(%s, email),
                        default_address = coalesce(%s, default_address)
                    where id = %s
                    """,
                    (conversation.budget_email, conversation.delivery_address, contact_id),
                )
                self._persist_tags(conn, contact_id, conversation.tags)
                self._persist_new_history(conn, contact_id, conversation)
        conversation.persisted_history_count = len(conversation.history)
        return conversation

    def reset(self, phone: str) -> ConversationState:
        conversation, _ = self.get_or_create(phone)
        if conversation.contact_id is None:
            raise RuntimeError(f"Conversation has no contact_id phone={phone}")
        with self.pool.connection() as conn:
            with conn.transaction():
                conn.execute("delete from messages where contact_id = %s", (conversation.contact_id,))
                conn.execute("delete from contact_tags where contact_id = %s", (conversation.contact_id,))
                conn.execute(
                    """
                    update contact_flow_state set
                        current_state = 'awaiting_need_now',
                        is_closed = false,
                        printer_raw = null,
                        printer_brand = null,
                        printer_model = null,
                        toner_type = null,
                        toner_units = null,
                        sage_customer_exists = null,
                        sage_customer_code = null,
                        delivery_address = null,
                        budget_email = null,
                        empty_pickup_requested = null,
                        empty_units = null,
                        empty_type = null,
                        pickup_slot_text = null,
                        last_inbound_message_at = null,
                        last_outbound_message_at = null,
                        last_flow_reset_at = now()
                    where contact_id = %s
                    """,
                    (conversation.contact_id,),
                )
        reset_conversation = self.get(phone)
        if reset_conversation is None:
            raise RuntimeError(f"Failed to reset conversation phone={phone}")
        reset_conversation.current_state = "new"
        reset_conversation.persisted_history_count = 0
        return reset_conversation

    def list_all(self) -> list[ConversationState]:
        with self.pool.connection() as conn:
            rows_ = conn.execute(
                """
                select
                    c.id as contact_id,
                    c.phone,
                    c.email,
                    c.default_address,
                    c.created_at as contact_created_at,
                    c.updated_at as contact_updated_at,
                    s.current_state,
                    s.customer_existed_before_flow,
                    s.printer_brand,
                    s.printer_model,
                    s.printer_raw,
                    s.toner_type,
                    s.toner_units,
                    s.sage_customer_exists,
                    s.delivery_address,
                    s.budget_email,
                    s.empty_pickup_requested,
                    s.empty_units,
                    s.empty_type,
                    s.pickup_slot_text,
                    s.created_at,
                    s.updated_at
                from contacts c
                join contact_flow_state s on s.contact_id = c.id
                order by s.updated_at desc
                limit 200
                """
            ).fetchall()
            return [self._hydrate_conversation(conn, row) for row in rows_]

    def _hydrate_conversation(self, conn, row: dict[str, Any]) -> ConversationState:
        tags = [
            tag_row["code"]
            for tag_row in conn.execute(
                """
                select t.code
                from contact_tags ct
                join tags t on t.id = ct.tag_id
                where ct.contact_id = %s
                order by ct.created_at asc
                """,
                (row["contact_id"],),
            ).fetchall()
        ]
        message_rows = conn.execute(
            """
            select
                direction,
                text_content,
                state_before,
                state_after,
                wa_message_id,
                wa_conversation_id,
                wa_status,
                message_type,
                raw_payload,
                created_at
            from messages
            where contact_id = %s
            order by created_at asc, id asc
            """,
            (row["contact_id"],),
        ).fetchall()
        history = [
            HistoryItem(
                timestamp=message["created_at"],
                direction=message["direction"],
                text=message["text_content"] or "",
                state_before=message["state_before"] or "",
                state_after=message["state_after"] or "",
                wa_message_id=message["wa_message_id"],
                wa_conversation_id=message["wa_conversation_id"],
                wa_status=message["wa_status"],
                message_type=message["message_type"],
                raw_payload=message["raw_payload"],
            )
            for message in message_rows
        ]
        current_state = row["current_state"]
        if not history:
            current_state = "new"
        return ConversationState(
            phone=row["phone"],
            contact_id=row["contact_id"],
            current_state=current_state,
            tags=tags,
            printer_brand=row["printer_brand"],
            printer_model=row["printer_model"],
            printer_raw=row["printer_raw"],
            toner_type=row["toner_type"],
            toner_units=row["toner_units"],
            sage_customer_exists=row["sage_customer_exists"],
            delivery_address=row["delivery_address"],
            budget_email=row["budget_email"] or row["email"],
            empty_pickup_requested=row["empty_pickup_requested"],
            empty_units=row["empty_units"],
            empty_type=row["empty_type"],
            pickup_slot_text=row["pickup_slot_text"],
            history=history,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            persisted_history_count=len(history),
        )

    def _ensure_contact(self, conn, phone: str) -> int:
        row = conn.execute(
            """
            insert into contacts (phone)
            values (%s)
            on conflict (phone) do update set phone = excluded.phone
            returning id
            """,
            (phone,),
        ).fetchone()
        return row["id"]

    def _flow_params(self, contact_id: int, conversation: ConversationState) -> dict[str, Any]:
        last_inbound = self._last_message_at(conversation, "inbound")
        last_outbound = self._last_message_at(conversation, "outbound")
        return {
            "contact_id": contact_id,
            "current_state": self._db_state(conversation.current_state),
            "is_closed": conversation.current_state.startswith("closed_"),
            "printer_raw": conversation.printer_raw,
            "printer_brand": conversation.printer_brand,
            "printer_model": conversation.printer_model,
            "toner_type": conversation.toner_type,
            "toner_units": conversation.toner_units,
            "sage_customer_exists": conversation.sage_customer_exists,
            "delivery_address": conversation.delivery_address,
            "budget_email": conversation.budget_email,
            "empty_pickup_requested": conversation.empty_pickup_requested,
            "empty_units": conversation.empty_units,
            "empty_type": conversation.empty_type,
            "pickup_slot_text": conversation.pickup_slot_text,
            "last_inbound_message_at": last_inbound,
            "last_outbound_message_at": last_outbound,
        }

    def _db_state(self, state: str) -> str:
        if state == "new":
            return "awaiting_need_now"
        return state

    def _last_message_at(self, conversation: ConversationState, direction: str) -> datetime | None:
        matching = [item.timestamp for item in conversation.history if item.direction == direction]
        return max(matching) if matching else None

    def _persist_tags(self, conn, contact_id: int, tags: list[str]) -> None:
        for tag in tags:
            tag_row = conn.execute(
                """
                insert into tags (code)
                values (%s)
                on conflict (code) do update set code = excluded.code
                returning id
                """,
                (tag,),
            ).fetchone()
            conn.execute(
                """
                insert into contact_tags (contact_id, tag_id)
                values (%s, %s)
                on conflict (contact_id, tag_id) do nothing
                """,
                (contact_id, tag_row["id"]),
            )

    def _persist_new_history(
        self,
        conn,
        contact_id: int,
        conversation: ConversationState,
    ) -> None:
        for item in conversation.history[conversation.persisted_history_count :]:
            conn.execute(
                """
                insert into messages (
                    contact_id,
                    direction,
                    provider,
                    wa_message_id,
                    wa_conversation_id,
                    wa_status,
                    message_type,
                    text_content,
                    raw_payload,
                    state_before,
                    state_after,
                    created_at
                )
                values (%s, %s, 'whatsapp_cloud_api', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (provider, wa_message_id)
                where wa_message_id is not null
                do nothing
                """,
                (
                    contact_id,
                    item.direction,
                    item.wa_message_id,
                    item.wa_conversation_id,
                    item.wa_status,
                    item.message_type,
                    item.text,
                    json.dumps(item.raw_payload) if item.raw_payload is not None else None,
                    item.state_before,
                    item.state_after,
                    item.timestamp,
                ),
            )

    def customer_exists(self, phone: str) -> bool:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                select
                    c.email,
                    c.default_address,
                    s.customer_existed_before_flow
                from contacts c
                left join contact_flow_state s on s.contact_id = c.id
                where c.phone = %s
                """,
                (phone,),
            ).fetchone()
            if row is None:
                return False
            return bool(row["email"] or row["default_address"] or row["customer_existed_before_flow"])

    def upsert_toner_order(self, conversation: ConversationState) -> None:
        if conversation.contact_id is None or not self._has_order_data(conversation):
            return
        with self.pool.connection() as conn:
            with conn.transaction():
                active_order = conn.execute(
                    """
                    select id
                    from toner_orders
                    where contact_id = %s
                      and status in ('draft', 'pending_budget', 'confirmed', 'pickup_requested')
                    order by updated_at desc
                    limit 1
                    """,
                    (conversation.contact_id,),
                ).fetchone()
                payload = {
                    "contact_id": conversation.contact_id,
                    "phone": conversation.phone,
                    "printer_brand": conversation.printer_brand,
                    "printer_model": conversation.printer_model,
                    "printer_raw": conversation.printer_raw,
                    "toner_type": conversation.toner_type,
                    "toner_units": conversation.toner_units,
                    "customer_exists": conversation.sage_customer_exists,
                    "delivery_address": conversation.delivery_address,
                    "budget_email": conversation.budget_email,
                    "status": self._order_status(conversation),
                    "empty_pickup_requested": conversation.empty_pickup_requested,
                    "empty_units": conversation.empty_units,
                    "empty_type": conversation.empty_type,
                    "pickup_slot_text": conversation.pickup_slot_text,
                }
                if active_order:
                    payload["id"] = active_order["id"]
                    conn.execute(
                        """
                        update toner_orders set
                            phone = %(phone)s,
                            printer_brand = %(printer_brand)s,
                            printer_model = %(printer_model)s,
                            printer_raw = %(printer_raw)s,
                            toner_type = %(toner_type)s,
                            toner_units = %(toner_units)s,
                            customer_exists = %(customer_exists)s,
                            delivery_address = %(delivery_address)s,
                            budget_email = %(budget_email)s,
                            status = %(status)s,
                            empty_pickup_requested = %(empty_pickup_requested)s,
                            empty_units = %(empty_units)s,
                            empty_type = %(empty_type)s,
                            pickup_slot_text = %(pickup_slot_text)s
                        where id = %(id)s
                        """,
                        payload,
                    )
                    return
                conn.execute(
                    """
                    insert into toner_orders (
                        contact_id,
                        phone,
                        printer_brand,
                        printer_model,
                        printer_raw,
                        toner_type,
                        toner_units,
                        customer_exists,
                        delivery_address,
                        budget_email,
                        status,
                        empty_pickup_requested,
                        empty_units,
                        empty_type,
                        pickup_slot_text
                    )
                    values (
                        %(contact_id)s,
                        %(phone)s,
                        %(printer_brand)s,
                        %(printer_model)s,
                        %(printer_raw)s,
                        %(toner_type)s,
                        %(toner_units)s,
                        %(customer_exists)s,
                        %(delivery_address)s,
                        %(budget_email)s,
                        %(status)s,
                        %(empty_pickup_requested)s,
                        %(empty_units)s,
                        %(empty_type)s,
                        %(pickup_slot_text)s
                    )
                    """,
                    payload,
                )

    def _has_order_data(self, conversation: ConversationState) -> bool:
        return any(
            [
                conversation.toner_units,
                conversation.empty_pickup_requested,
                conversation.empty_units,
                conversation.pickup_slot_text,
            ]
        )

    def _order_status(self, conversation: ConversationState) -> str:
        if conversation.current_state.startswith("closed_"):
            return "closed"
        if conversation.sage_customer_exists is False:
            return "pending_budget"
        if conversation.empty_pickup_requested:
            return "pickup_requested"
        if conversation.toner_units:
            return "confirmed"
        return "draft"


class PostgresJobRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def add(self, job: ScheduledJob) -> ScheduledJob:
        with self.pool.connection() as conn:
            with conn.transaction():
                contact_id = self._ensure_contact(conn, job.phone)
                row = conn.execute(
                    """
                    insert into scheduled_jobs (contact_id, job_type, payload, run_at)
                    values (%s, %s, %s, %s)
                    returning id, status, created_at
                    """,
                    (contact_id, job.job_type, json.dumps(job.payload), job.run_at),
                ).fetchone()
                job.id = str(row["id"])
                job.status = row["status"]
                job.created_at = row["created_at"]
        return job

    def list_all(self) -> list[ScheduledJob]:
        with self.pool.connection() as conn:
            rows_ = conn.execute(
                """
                select
                    sj.id,
                    sj.job_type,
                    c.phone,
                    sj.payload,
                    sj.run_at,
                    sj.status,
                    sj.executed_at,
                    sj.attempts,
                    sj.max_attempts,
                    sj.last_error,
                    sj.created_at
                from scheduled_jobs sj
                join contacts c on c.id = sj.contact_id
                order by sj.run_at asc
                limit 500
                """
            ).fetchall()
            return [self._job_from_row(row) for row in rows_]

    def mark_executed(self, job: ScheduledJob) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                update scheduled_jobs
                set status = 'done',
                    executed_at = coalesce(%s, now()),
                    attempts = attempts + 1
                where id = %s
                """,
                (job.executed_at, int(job.id)),
            )

    def _job_from_row(self, row: dict[str, Any]) -> ScheduledJob:
        return ScheduledJob(
            id=str(row["id"]),
            job_type=row["job_type"],
            phone=row["phone"],
            payload=row["payload"] or {},
            run_at=row["run_at"],
            executed=row["status"] == "done",
            executed_at=row["executed_at"],
            status=row["status"],
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
            last_error=row["last_error"],
            created_at=row["created_at"],
        )

    def _ensure_contact(self, conn, phone: str) -> int:
        row = conn.execute(
            """
            insert into contacts (phone)
            values (%s)
            on conflict (phone) do update set phone = excluded.phone
            returning id
            """,
            (phone,),
        ).fetchone()
        return row["id"]


class PostgresProcessedEventRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

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
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                insert into processed_events (
                    provider,
                    provider_event_id,
                    event_type,
                    payload_hash
                )
                values (%s, %s, %s, %s)
                on conflict (provider, provider_event_id) do nothing
                returning id
                """,
                (provider, provider_event_id, event_type, payload_hash),
            ).fetchone()
            return row is not None
