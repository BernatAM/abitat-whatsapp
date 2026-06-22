from __future__ import annotations

import logging

from app.domain.models import ConversationState
from app.services.jobs import JobService
from app.utils.parsing import (
    extract_email,
    extract_units,
    normalize_toner_type,
    normalize_yes_no,
    normalize_whitespace,
    strip_email_from_text,
)


logger = logging.getLogger(__name__)


TEXT_1 = "Hola 👋 ¿Necesitas tóner ahora mismo?"
TEXT_2 = "Perfecto 😊 Cuando lo necesites, escríbenos por aquí y te lo gestionamos rápido."
TEXT_4 = "Perfecto 👌 Dime por favor la marca de tu impresora."
TEXT_5 = "Genial. Ahora dime el modelo de tu impresora."
TEXT_6 = "Genial. ¿Qué tipo de tóner prefieres?\nOpciones: Ecológico Ábitat / Original / Compatible"
TEXT_7 = "Perfecto. ¿Cuántas unidades necesitas?"
TEXT_8 = "Perfecto 🙌 Te lo preparamos. La entrega se realiza en un máximo de 72h."
TEXT_9 = "Antes de cerrar 😊 ¿Necesitas que te recojamos los cartuchos vacíos? (Sí/No)"
TEXT_10 = "Perfecto. Quedamos pendientes. Gracias 🙌"
TEXT_11 = "Genial. ¿Cuántas unidades de vacíos tienes para recoger?"
TEXT_12 = "¿Qué tipo son? Opciones: Ecológico Ábitat / Original / Compatible"
TEXT_13 = "Perfecto. Pasaremos a recogerlo dentro de nuestro horario habitual de recogidas, de lunes a viernes de 9h a 14h."
TEXT_14 = "Perfecto 🙌 Queda registrada la recogida. Te confirmaremos por este canal si hubiera cualquier ajuste."
TEXT_15 = (
    "Perfecto 🙌 Para prepararte el pedido necesito estos datos:\n"
    "📍 Dirección de entrega\n"
    "📧 Email para enviarte el presupuesto para tu aceptación"
)
TEXT_16 = (
    "Gracias 😊 En breve te enviaremos el presupuesto y te contactaremos por teléfono/email "
    "para confirmar el pago y proceder con la entrega."
)
TEXT_17 = "¿Quieres que te recojamos también los cartuchos vacíos? (Sí/No)"
TEXT_18 = "Perfecto 🙌 Quedamos pendientes del presupuesto. Gracias."
TEXT_19 = "Genial. ¿Cuántas unidades tienes para recoger?"
TEXT_20 = "¿Son ecológicos Ábitat, originales o compatibles?"
TEXT_21 = "Perfecto 🙌 La recogida de originales es gratuita."
TEXT_22 = (
    "Perfecto 😊 Te informamos que la recogida de este tipo de vacíos tiene un coste. "
    "Te lo incluiremos en el presupuesto antes de confirmar."
)
TEXT_23 = (
    "Perfecto 🙌 Queda registrada la recogida.\n"
    "Te contactaremos por teléfono/email para confirmar presupuesto, pago y entrega."
)
TEXT_PICKUP_STANDARD = "Perfecto. Pasaremos a recogerlo dentro de nuestro horario habitual de recogidas, de lunes a viernes de 9h a 14h."
TEXT_CONFIRMATION_PROMPT = "Responde Sí para confirmar el pedido o No si quieres revisarlo con atención al cliente."


class ConversationService:
    def __init__(
        self,
        conversation_repository,
        job_service: JobService,
        customer_service_phone: str = "900 000 000",
    ) -> None:
        self.conversation_repository = conversation_repository
        self.job_service = job_service
        self.customer_service_phone = customer_service_phone

    def process_incoming_message(
        self,
        phone: str,
        text: str,
        wa_message_id: str | None = None,
        wa_conversation_id: str | None = None,
        raw_payload: dict | None = None,
    ) -> tuple[ConversationState, list[str]]:
        conversation, created = self.conversation_repository.get_or_create(phone)
        normalized_text = normalize_whitespace(text)
        replies: list[str] = []
        initial_state = conversation.current_state

        logger.info("Inbound message phone=%s state=%s text=%s", phone, initial_state, normalized_text)
        conversation.add_history(
            direction="inbound",
            text=normalized_text,
            state_before=initial_state,
            state_after=initial_state,
            wa_message_id=wa_message_id,
            wa_conversation_id=wa_conversation_id,
            raw_payload=raw_payload,
        )

        if created or conversation.current_state == "new" or conversation.current_state.startswith("closed_"):
            if conversation.current_state.startswith("closed_"):
                self._clear_flow_data(conversation)
            self._send_reply(conversation, replies, TEXT_1, next_state="awaiting_need_now")
            self.conversation_repository.save(conversation)
            return conversation, replies

        handler_name = f"_handle_{conversation.current_state}"
        handler = getattr(self, handler_name, self._handle_unknown_state)
        if self._wants_customer_service(normalized_text):
            self._send_customer_service_reply(conversation, replies, next_state=conversation.current_state)
            self.conversation_repository.save(conversation)
            return conversation, replies
        was_order_confirmed = conversation.order_confirmed
        handler(conversation, normalized_text, replies)
        self._persist_order(conversation)
        self.conversation_repository.save(conversation)
        if conversation.order_confirmed and not was_order_confirmed:
            self.job_service.send_order_confirmed_email(conversation)
        return conversation, replies

    def _handle_unknown_state(self, conversation: ConversationState, _: str, replies: list[str]) -> None:
        self._send_reply(
            conversation,
            replies,
            self._customer_service_text(),
            next_state=conversation.current_state,
        )

    def _handle_awaiting_need_now(self, conversation: ConversationState, text: str, replies: list[str]) -> None:
        decision = normalize_yes_no(text)
        if decision == "no":
            self._add_tag(conversation, "toner_no_now")
            self._send_reply(conversation, replies, TEXT_2, next_state="awaiting_empty_pickup_no_need")
            self._send_reply(conversation, replies, TEXT_17, next_state="awaiting_empty_pickup_no_need")
            return
        if decision == "yes":
            self._add_tag(conversation, "toner_yes_now")
            self._send_reply(conversation, replies, TEXT_4, next_state="awaiting_printer_brand")
            return
        self._send_reply(
            conversation,
            replies,
            f"No te he entendido del todo. ¿Necesitas tóner ahora mismo? Responde Sí o No.\n\n{self._customer_service_text()}",
            next_state=conversation.current_state,
        )

    def _handle_awaiting_empty_pickup_no_need(
        self,
        conversation: ConversationState,
        text: str,
        replies: list[str],
    ) -> None:
        decision = normalize_yes_no(text)
        if decision == "no":
            conversation.empty_pickup_requested = False
            self.job_service.schedule_reminder_45_days(conversation.phone)
            self._send_reply(conversation, replies, TEXT_10, next_state="closed_no_need")
            return
        if decision == "yes":
            conversation.empty_pickup_requested = True
            self._send_reply(conversation, replies, TEXT_19, next_state="awaiting_empty_units_no_need")
            return
        self._send_reply(
            conversation,
            replies,
            f"No te he entendido del todo. ¿Quieres que te recojamos también los cartuchos vacíos? Responde Sí o No.\n\n{self._customer_service_text()}",
            next_state=conversation.current_state,
        )

    def _handle_awaiting_empty_units_no_need(
        self,
        conversation: ConversationState,
        text: str,
        replies: list[str],
    ) -> None:
        units = extract_units(text)
        if units is None:
            self._send_reply(
                conversation,
                replies,
                "¿Cuántas unidades tienes para recoger? Puedes indicarme solo el número.",
                next_state=conversation.current_state,
            )
            return
        conversation.empty_units = units
        self._send_reply(conversation, replies, TEXT_20, next_state="awaiting_empty_type_no_need")

    def _handle_awaiting_empty_type_no_need(
        self,
        conversation: ConversationState,
        text: str,
        replies: list[str],
    ) -> None:
        empty_type = normalize_toner_type(text)
        if empty_type is None:
            self._send_reply(
                conversation,
                replies,
                f"No te he entendido del todo. ¿Prefieres Ecológico Ábitat, Original o Compatible?\n\n{self._customer_service_text()}",
                next_state=conversation.current_state,
            )
            return
        conversation.empty_type = empty_type
        self._add_tag(conversation, f"empty_type_{empty_type}")
        self._send_reply(
            conversation,
            replies,
            TEXT_21 if empty_type == "original" else TEXT_22,
            next_state=conversation.current_state,
        )
        self._request_pickup_confirmation(conversation, replies)

    def _handle_awaiting_pickup_slot_no_need(
        self,
        conversation: ConversationState,
        text: str,
        replies: list[str],
    ) -> None:
        self._request_pickup_confirmation(conversation, replies)

    def _handle_awaiting_printer_brand(self, conversation: ConversationState, text: str, replies: list[str]) -> None:
        conversation.printer_brand = text
        logger.info("Stored printer brand phone=%s printer_brand=%s", conversation.phone, text)
        self._send_reply(conversation, replies, TEXT_5, next_state="awaiting_printer_model")

    def _handle_awaiting_printer_model(self, conversation: ConversationState, text: str, replies: list[str]) -> None:
        conversation.printer_model = text
        conversation.printer_raw = " ".join(
            part for part in [conversation.printer_brand, conversation.printer_model] if part
        )
        logger.info("Stored printer model phone=%s printer_model=%s", conversation.phone, text)
        self._send_reply(conversation, replies, TEXT_6, next_state="awaiting_toner_type")

    def _handle_awaiting_toner_type(self, conversation: ConversationState, text: str, replies: list[str]) -> None:
        toner_type = normalize_toner_type(text)
        if toner_type is None:
            self._send_reply(
                conversation,
                replies,
                f"No te he entendido del todo. ¿Prefieres tóner Ecológico Ábitat, Original o Compatible?\n\n{self._customer_service_text()}",
                next_state=conversation.current_state,
            )
            return
        conversation.toner_type = toner_type
        self._add_tag(conversation, f"toner_type_{toner_type}")
        self._send_reply(conversation, replies, TEXT_7, next_state="awaiting_units")

    def _handle_awaiting_units(self, conversation: ConversationState, text: str, replies: list[str]) -> None:
        units = extract_units(text)
        if units is None:
            self._send_reply(
                conversation,
                replies,
                "¿Cuántas unidades necesitas? Puedes indicarme solo el número.",
                next_state=conversation.current_state,
            )
            return
        conversation.toner_units = units
        exists = self._customer_exists_in_database(conversation)
        conversation.sage_customer_exists = exists
        if exists:
            self._add_tag(conversation, "sage_existing_customer")
            self._send_reply(conversation, replies, TEXT_8, next_state="awaiting_empty_pickup_existing_customer")
            self._send_reply(conversation, replies, TEXT_9, next_state="awaiting_empty_pickup_existing_customer")
            return
        self._add_tag(conversation, "sage_new_customer")
        self._send_reply(conversation, replies, TEXT_15, next_state="awaiting_new_customer_data")

    def _handle_awaiting_empty_pickup_existing_customer(
        self,
        conversation: ConversationState,
        text: str,
        replies: list[str],
    ) -> None:
        decision = normalize_yes_no(text)
        if decision == "no":
            conversation.empty_pickup_requested = False
            self._request_order_confirmation(conversation, replies)
            return
        if decision == "yes":
            conversation.empty_pickup_requested = True
            self._send_reply(conversation, replies, TEXT_11, next_state="awaiting_empty_units_existing_customer")
            return
        self._send_reply(
            conversation,
            replies,
            f"No te he entendido del todo. ¿Necesitas que te recojamos los cartuchos vacíos? Responde Sí o No.\n\n{self._customer_service_text()}",
            next_state=conversation.current_state,
        )

    def _handle_awaiting_empty_units_existing_customer(
        self,
        conversation: ConversationState,
        text: str,
        replies: list[str],
    ) -> None:
        units = extract_units(text)
        if units is None:
            self._send_reply(
                conversation,
                replies,
                "¿Cuántas unidades tienes para recoger? Puedes indicarme solo el número.",
                next_state=conversation.current_state,
            )
            return
        conversation.empty_units = units
        self._send_reply(conversation, replies, TEXT_12, next_state="awaiting_empty_type_existing_customer")

    def _handle_awaiting_empty_type_existing_customer(
        self,
        conversation: ConversationState,
        text: str,
        replies: list[str],
    ) -> None:
        empty_type = normalize_toner_type(text)
        if empty_type is None:
            self._send_reply(
                conversation,
                replies,
                f"No te he entendido del todo. ¿Prefieres Ecológico Ábitat, Original o Compatible?\n\n{self._customer_service_text()}",
                next_state=conversation.current_state,
            )
            return
        conversation.empty_type = empty_type
        self._add_tag(conversation, f"empty_type_{empty_type}")
        self._request_pickup_confirmation(conversation, replies)

    def _handle_awaiting_pickup_slot_existing_customer(
        self,
        conversation: ConversationState,
        text: str,
        replies: list[str],
    ) -> None:
        self._request_pickup_confirmation(conversation, replies)

    def _handle_awaiting_new_customer_data(self, conversation: ConversationState, text: str, replies: list[str]) -> None:
        email = extract_email(text)
        address = strip_email_from_text(text, email)
        if email:
            conversation.budget_email = email
        if address:
            conversation.delivery_address = address
        if not conversation.budget_email and not conversation.delivery_address:
            self._send_reply(
                conversation,
                replies,
                "Me faltan la dirección de entrega y el email para enviarte el presupuesto. ¿Me los puedes indicar?",
                next_state=conversation.current_state,
            )
            return
        if not conversation.budget_email:
            self._send_reply(
                conversation,
                replies,
                "Me falta el email para enviarte el presupuesto. ¿Me lo puedes indicar?",
                next_state=conversation.current_state,
            )
            return
        if not conversation.delivery_address:
            self._send_reply(
                conversation,
                replies,
                "Me falta la dirección de entrega. ¿Me la puedes indicar?",
                next_state=conversation.current_state,
            )
            return
        self._send_reply(conversation, replies, TEXT_16, next_state="awaiting_empty_pickup_new_customer")
        self._send_reply(conversation, replies, TEXT_17, next_state="awaiting_empty_pickup_new_customer")

    def _handle_awaiting_empty_pickup_new_customer(
        self,
        conversation: ConversationState,
        text: str,
        replies: list[str],
    ) -> None:
        decision = normalize_yes_no(text)
        if decision == "no":
            conversation.empty_pickup_requested = False
            self._request_order_confirmation(conversation, replies)
            return
        if decision == "yes":
            conversation.empty_pickup_requested = True
            self._send_reply(conversation, replies, TEXT_19, next_state="awaiting_empty_units_new_customer")
            return
        self._send_reply(
            conversation,
            replies,
            f"No te he entendido del todo. ¿Quieres que te recojamos también los cartuchos vacíos? Responde Sí o No.\n\n{self._customer_service_text()}",
            next_state=conversation.current_state,
        )

    def _handle_awaiting_empty_units_new_customer(
        self,
        conversation: ConversationState,
        text: str,
        replies: list[str],
    ) -> None:
        units = extract_units(text)
        if units is None:
            self._send_reply(
                conversation,
                replies,
                "¿Cuántas unidades tienes para recoger? Puedes indicarme solo el número.",
                next_state=conversation.current_state,
            )
            return
        conversation.empty_units = units
        self._send_reply(conversation, replies, TEXT_20, next_state="awaiting_empty_type_new_customer")

    def _handle_awaiting_empty_type_new_customer(
        self,
        conversation: ConversationState,
        text: str,
        replies: list[str],
    ) -> None:
        empty_type = normalize_toner_type(text)
        if empty_type is None:
            self._send_reply(
                conversation,
                replies,
                f"No te he entendido del todo. ¿Prefieres Ecológico Ábitat, Original o Compatible?\n\n{self._customer_service_text()}",
                next_state=conversation.current_state,
            )
            return
        conversation.empty_type = empty_type
        self._add_tag(conversation, f"empty_type_{empty_type}")
        self._send_reply(
            conversation,
            replies,
            TEXT_21 if empty_type == "original" else TEXT_22,
            next_state=conversation.current_state,
        )
        self._request_pickup_confirmation(conversation, replies)

    def _handle_awaiting_pickup_slot_new_customer(
        self,
        conversation: ConversationState,
        text: str,
        replies: list[str],
    ) -> None:
        self._request_pickup_confirmation(conversation, replies)

    def _handle_awaiting_order_confirmation(
        self,
        conversation: ConversationState,
        text: str,
        replies: list[str],
    ) -> None:
        decision = normalize_yes_no(text)
        if decision == "yes":
            conversation.order_confirmed = True
            if not conversation.toner_units:
                self.job_service.schedule_reminder_45_days(conversation.phone)
            self._send_reply(
                conversation,
                replies,
                self._final_text_for(conversation),
                next_state=self._final_state_for(conversation),
            )
            return
        if decision == "no":
            conversation.order_confirmed = False
            self._send_reply(
                conversation,
                replies,
                f"No registramos el pedido. {self._customer_service_text()}",
                next_state="closed_unconfirmed",
            )
            return
        self._send_reply(
            conversation,
            replies,
            f"No te he entendido del todo. {TEXT_CONFIRMATION_PROMPT}\n\n{self._customer_service_text()}",
            next_state=conversation.current_state,
        )

    def _send_reply(
        self,
        conversation: ConversationState,
        replies: list[str],
        text: str,
        next_state: str,
    ) -> None:
        state_before = conversation.current_state
        conversation.current_state = next_state
        conversation.add_history(
            direction="outbound",
            text=text,
            state_before=state_before,
            state_after=next_state,
        )
        replies.append(text)
        logger.info(
            "Outbound message phone=%s from_state=%s to_state=%s text=%s",
            conversation.phone,
            state_before,
            next_state,
            text.replace("\n", " "),
        )

    def _add_tag(self, conversation: ConversationState, tag: str) -> None:
        if conversation.add_tag(tag):
            logger.info("Added tag phone=%s tag=%s", conversation.phone, tag)

    def _clear_flow_data(self, conversation: ConversationState) -> None:
        conversation.current_state = "new"
        conversation.printer_brand = None
        conversation.printer_model = None
        conversation.printer_raw = None
        conversation.toner_type = None
        conversation.toner_units = None
        conversation.sage_customer_exists = None
        conversation.delivery_address = None
        conversation.budget_email = None
        conversation.empty_pickup_requested = None
        conversation.empty_units = None
        conversation.empty_type = None
        conversation.pickup_slot_text = None
        conversation.order_confirmed = False

    def _customer_exists_in_database(self, conversation: ConversationState) -> bool:
        if hasattr(self.conversation_repository, "customer_exists"):
            exists = self.conversation_repository.customer_exists(conversation.phone)
            logger.info("Database customer check phone=%s exists=%s", conversation.phone, exists)
            return exists
        return False

    def _persist_order(self, conversation: ConversationState) -> None:
        if hasattr(self.conversation_repository, "upsert_toner_order"):
            self.conversation_repository.upsert_toner_order(conversation)

    def _request_pickup_confirmation(self, conversation: ConversationState, replies: list[str]) -> None:
        conversation.pickup_slot_text = TEXT_PICKUP_STANDARD
        self._send_reply(conversation, replies, TEXT_PICKUP_STANDARD, next_state=conversation.current_state)
        self._request_order_confirmation(conversation, replies)

    def _request_order_confirmation(self, conversation: ConversationState, replies: list[str]) -> None:
        conversation.order_confirmed = False
        self._send_reply(
            conversation,
            replies,
            f"{self._order_summary(conversation)}\n\n{TEXT_CONFIRMATION_PROMPT}",
            next_state="awaiting_order_confirmation",
        )

    def _order_summary(self, conversation: ConversationState) -> str:
        lines = ["Resumen del pedido:"]
        if conversation.toner_units:
            lines.append(f"- Impresora: {conversation.printer_raw or 'pendiente'}")
            lines.append(f"- Tóner: {conversation.toner_type or 'pendiente'}")
            lines.append(f"- Unidades de tóner: {conversation.toner_units}")
        if conversation.sage_customer_exists is False:
            lines.append(f"- Dirección: {conversation.delivery_address or 'pendiente'}")
            lines.append(f"- Email presupuesto: {conversation.budget_email or 'pendiente'}")
        if conversation.empty_pickup_requested:
            lines.append("- Recogida de vacíos: Sí")
            lines.append(f"- Unidades de vacíos: {conversation.empty_units or 'pendiente'}")
            lines.append(f"- Tipo de vacíos: {conversation.empty_type or 'pendiente'}")
            lines.append(f"- Horario de recogida: {conversation.pickup_slot_text or 'pendiente'}")
        else:
            lines.append("- Recogida de vacíos: No")
        return "\n".join(lines)

    def _final_state_for(self, conversation: ConversationState) -> str:
        if not conversation.toner_units:
            return "closed_no_need"
        if conversation.sage_customer_exists:
            return "closed_existing_with_pickup" if conversation.empty_pickup_requested else "closed_existing_without_pickup"
        return "closed_new_with_pickup" if conversation.empty_pickup_requested else "closed_new_without_pickup"

    def _final_text_for(self, conversation: ConversationState) -> str:
        if not conversation.toner_units:
            return TEXT_14
        if conversation.sage_customer_exists:
            return TEXT_14 if conversation.empty_pickup_requested else TEXT_10
        return TEXT_23 if conversation.empty_pickup_requested else TEXT_18

    def _customer_service_text(self) -> str:
        return f"Para cualquier otra consulta, puedes contactar con atención al cliente en el {self.customer_service_phone}."

    def _send_customer_service_reply(
        self,
        conversation: ConversationState,
        replies: list[str],
        next_state: str,
    ) -> None:
        self._send_reply(conversation, replies, self._customer_service_text(), next_state=next_state)

    def _wants_customer_service(self, text: str) -> bool:
        value = normalize_whitespace(text).lower()
        markers = [
            "atencion al cliente",
            "atención al cliente",
            "telefono",
            "teléfono",
            "llamar",
            "hablar con alguien",
            "hablar con una persona",
            "operador",
            "otra cosa",
            "otra consulta",
            "reclamacion",
            "reclamación",
            "factura",
        ]
        return any(marker in value for marker in markers)
