from __future__ import annotations

import logging

from app.domain.models import ConversationState
from app.integrations.sage import SageMockService
from app.repositories.memory import InMemoryConversationRepository
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


GREETING = "Hola 👋 ¿Necesitas tóner ahora mismo?"


class ConversationService:
    def __init__(
        self,
        conversation_repository: InMemoryConversationRepository,
        sage_service: SageMockService,
        job_service: JobService,
    ) -> None:
        self.conversation_repository = conversation_repository
        self.sage_service = sage_service
        self.job_service = job_service

    def process_incoming_message(self, phone: str, text: str) -> tuple[ConversationState, list[str]]:
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
        )

        if created or conversation.current_state == "new" or conversation.current_state.startswith("closed_"):
            self._send_reply(conversation, replies, GREETING, next_state="awaiting_need_now")
            self.conversation_repository.save(conversation)
            return conversation, replies

        handler_name = f"_handle_{conversation.current_state}"
        handler = getattr(self, handler_name, self._handle_unknown_state)
        handler(conversation, normalized_text, replies)
        self.conversation_repository.save(conversation)
        return conversation, replies

    def _handle_unknown_state(self, conversation: ConversationState, _: str, replies: list[str]) -> None:
        self._send_reply(
            conversation,
            replies,
            "Ha ocurrido una inconsistencia en la demo. Reinicia la conversación desde el endpoint debug.",
            next_state=conversation.current_state,
        )

    def _handle_awaiting_need_now(self, conversation: ConversationState, text: str, replies: list[str]) -> None:
        decision = normalize_yes_no(text)
        if decision == "no":
            self._add_tag(conversation, "toner_no_now")
            self.job_service.schedule_reminder_45_days(conversation.phone)
            self._send_reply(
                conversation,
                replies,
                "Perfecto 😊 Cuando lo necesites, escríbenos por aquí y te lo gestionamos rápido.",
                next_state="closed_no_need",
            )
            return
        if decision == "yes":
            self._add_tag(conversation, "toner_yes_now")
            self._send_reply(
                conversation,
                replies,
                "Perfecto 👌 Dime por favor la marca y el modelo de tu impresora.",
                next_state="awaiting_printer_model",
            )
            return
        self._send_reply(
            conversation,
            replies,
            "No te he entendido del todo. ¿Necesitas tóner ahora mismo? Responde Sí o No.",
            next_state=conversation.current_state,
        )

    def _handle_awaiting_printer_model(self, conversation: ConversationState, text: str, replies: list[str]) -> None:
        conversation.printer_raw = text
        logger.info("Stored printer model phone=%s printer_raw=%s", conversation.phone, text)
        self._send_reply(
            conversation,
            replies,
            "Genial. ¿Qué tipo de tóner prefieres?\nOpciones: Ecológico Ábitat / Original / Compatible",
            next_state="awaiting_toner_type",
        )

    def _handle_awaiting_toner_type(self, conversation: ConversationState, text: str, replies: list[str]) -> None:
        toner_type = normalize_toner_type(text)
        if toner_type is None:
            self._send_reply(
                conversation,
                replies,
                "No te he entendido del todo. ¿Prefieres tóner Ecológico Ábitat, Original o Compatible?",
                next_state=conversation.current_state,
            )
            return
        conversation.toner_type = toner_type
        self._add_tag(conversation, f"toner_type_{toner_type}")
        self._send_reply(
            conversation,
            replies,
            "Perfecto. ¿Cuántas unidades necesitas?",
            next_state="awaiting_units",
        )

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
        exists = self.sage_service.check_customer(conversation.phone)
        conversation.sage_customer_exists = exists
        if exists:
            self._add_tag(conversation, "sage_existing_customer")
            self._send_reply(
                conversation,
                replies,
                "Perfecto 🙌 Te lo preparamos. La entrega se realiza en un máximo de 72h.",
                next_state="awaiting_empty_pickup_existing_customer",
            )
            self._send_reply(
                conversation,
                replies,
                "Antes de cerrar 😊 ¿Necesitas que te recojamos los cartuchos vacíos? (Sí/No)",
                next_state="awaiting_empty_pickup_existing_customer",
            )
            return
        self._add_tag(conversation, "sage_new_customer")
        self._send_reply(
            conversation,
            replies,
            "Perfecto 🙌 Para prepararte el pedido necesito estos datos:\n📍 Dirección de entrega\n📧 Email para enviarte el presupuesto para tu aceptación",
            next_state="awaiting_new_customer_data",
        )

    def _handle_awaiting_empty_pickup_existing_customer(
        self,
        conversation: ConversationState,
        text: str,
        replies: list[str],
    ) -> None:
        decision = normalize_yes_no(text)
        if decision == "no":
            conversation.empty_pickup_requested = False
            self._send_reply(
                conversation,
                replies,
                "Perfecto. Quedamos pendientes. Gracias 🙌",
                next_state="closed_existing_without_pickup",
            )
            return
        if decision == "yes":
            conversation.empty_pickup_requested = True
            self._send_reply(
                conversation,
                replies,
                "Genial. ¿Cuántas unidades de vacíos tienes para recoger?",
                next_state="awaiting_empty_units_existing_customer",
            )
            return
        self._send_reply(
            conversation,
            replies,
            "No te he entendido del todo. ¿Necesitas que te recojamos los cartuchos vacíos? Responde Sí o No.",
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
        self._send_reply(
            conversation,
            replies,
            "¿Qué tipo son? Opciones: Ecológico Ábitat / Original / Compatible",
            next_state="awaiting_empty_type_existing_customer",
        )

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
                "No te he entendido del todo. ¿Prefieres Ecológico Ábitat, Original o Compatible?",
                next_state=conversation.current_state,
            )
            return
        conversation.empty_type = empty_type
        self._add_tag(conversation, f"empty_type_{empty_type}")
        self._send_reply(
            conversation,
            replies,
            "Perfecto. ¿Qué día y en qué franja horaria te va bien la recogida?",
            next_state="awaiting_pickup_slot_existing_customer",
        )

    def _handle_awaiting_pickup_slot_existing_customer(
        self,
        conversation: ConversationState,
        text: str,
        replies: list[str],
    ) -> None:
        conversation.pickup_slot_text = text
        self._send_reply(
            conversation,
            replies,
            "Perfecto 🙌 Queda registrada la recogida. Te confirmaremos por este canal si hubiera cualquier ajuste.",
            next_state="closed_existing_with_pickup",
        )

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
        self._send_reply(
            conversation,
            replies,
            "Gracias 😊 En breve te enviaremos el presupuesto y te contactaremos por teléfono/email para confirmar el pago y proceder con la entrega.",
            next_state="awaiting_empty_pickup_new_customer",
        )
        self._send_reply(
            conversation,
            replies,
            "¿Quieres que te recojamos también los cartuchos vacíos? (Sí/No)",
            next_state="awaiting_empty_pickup_new_customer",
        )

    def _handle_awaiting_empty_pickup_new_customer(
        self,
        conversation: ConversationState,
        text: str,
        replies: list[str],
    ) -> None:
        decision = normalize_yes_no(text)
        if decision == "no":
            conversation.empty_pickup_requested = False
            self._send_reply(
                conversation,
                replies,
                "Perfecto 🙌 Quedamos pendientes del presupuesto. Gracias.",
                next_state="closed_new_without_pickup",
            )
            return
        if decision == "yes":
            conversation.empty_pickup_requested = True
            self._send_reply(
                conversation,
                replies,
                "Genial. ¿Cuántas unidades tienes para recoger?",
                next_state="awaiting_empty_units_new_customer",
            )
            return
        self._send_reply(
            conversation,
            replies,
            "No te he entendido del todo. ¿Quieres que te recojamos también los cartuchos vacíos? Responde Sí o No.",
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
        self._send_reply(
            conversation,
            replies,
            "¿Son ecológicos Ábitat, originales o compatibles?",
            next_state="awaiting_empty_type_new_customer",
        )

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
                "No te he entendido del todo. ¿Prefieres Ecológico Ábitat, Original o Compatible?",
                next_state=conversation.current_state,
            )
            return
        conversation.empty_type = empty_type
        self._add_tag(conversation, f"empty_type_{empty_type}")
        if empty_type == "original":
            message = (
                "Perfecto 🙌 La recogida de originales es gratuita.\n"
                "¿Qué día y en qué franja horaria te va bien?"
            )
        else:
            message = (
                "Perfecto 😊 Te informamos que la recogida de este tipo de vacíos tiene un coste. "
                "Te lo incluiremos en el presupuesto antes de confirmar.\n"
                "¿Qué día y en qué franja horaria te va bien?"
            )
        self._send_reply(
            conversation,
            replies,
            message,
            next_state="awaiting_pickup_slot_new_customer",
        )

    def _handle_awaiting_pickup_slot_new_customer(
        self,
        conversation: ConversationState,
        text: str,
        replies: list[str],
    ) -> None:
        conversation.pickup_slot_text = text
        self._send_reply(
            conversation,
            replies,
            "Perfecto 🙌 Queda registrada la recogida.\nTe contactaremos por teléfono/email para confirmar presupuesto, pago y entrega.",
            next_state="closed_new_with_pickup",
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
