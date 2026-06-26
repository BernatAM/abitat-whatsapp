from app.domain.models import ConversationState
from app.integrations.email import EmailMockService, build_order_email_body
from app.integrations.whatsapp import buttons_for_text, extract_message_text
from app.repositories.memory import InMemoryConversationRepository, InMemoryJobRepository
from app.services.conversation import (
    TEXT_4,
    TEXT_5,
    TEXT_6,
    TEXT_8,
    TEXT_9,
    TEXT_14,
    TEXT_CONFIRMATION_PROMPT,
    TEXT_17,
    TEXT_19,
    TEXT_20,
    TEXT_22,
    TEXT_PICKUP_STANDARD,
    ConversationService,
)
from app.services.jobs import JobService
from app.utils.parsing import normalize_toner_type


def build_service() -> tuple[ConversationService, InMemoryConversationRepository, InMemoryJobRepository]:
    conversation_repository = InMemoryConversationRepository()
    job_repository = InMemoryJobRepository()
    job_service = JobService(job_repository, EmailMockService())
    service = ConversationService(conversation_repository, job_service)
    return service, conversation_repository, job_repository


def test_printer_is_split_into_brand_and_model() -> None:
    service, repository, _ = build_service()
    phone = "+34600000001"

    service.process_incoming_message(phone, "Hola")
    _, replies = service.process_incoming_message(phone, "Si")
    assert replies == [TEXT_4]

    conversation, replies = service.process_incoming_message(phone, "HP")
    assert conversation.current_state == "awaiting_printer_model"
    assert conversation.printer_brand == "HP"
    assert replies == [TEXT_5]

    conversation, replies = service.process_incoming_message(phone, "LaserJet Pro")
    assert conversation.current_state == "awaiting_toner_type"
    assert conversation.printer_model == "LaserJet Pro"
    assert conversation.printer_raw == "HP LaserJet Pro"
    assert replies == [TEXT_6]

    assert repository.toner_orders_by_phone == {}


def test_initial_no_can_request_pickup_and_schedules_reminder() -> None:
    service, repository, jobs = build_service()
    phone = "+34600000002"

    service.process_incoming_message(phone, "Hola")
    _, replies = service.process_incoming_message(phone, "No")
    assert replies == [
        "Perfecto 😊 Cuando lo necesites, escríbenos por aquí y te lo gestionamos rápido.",
        TEXT_17,
    ]

    _, replies = service.process_incoming_message(phone, "Si")
    assert replies == [TEXT_19]
    service.process_incoming_message(phone, "3")
    conversation, replies = service.process_incoming_message(phone, "Compatible")
    assert conversation.current_state == "awaiting_order_confirmation"
    assert replies[0] == TEXT_22
    assert replies[1] == TEXT_PICKUP_STANDARD
    assert replies[2].startswith("Resumen del pedido:")
    assert TEXT_CONFIRMATION_PROMPT in replies[2]
    assert repository.toner_orders_by_phone == {}

    conversation, replies = service.process_incoming_message(phone, "Si")
    assert conversation.current_state == "closed_no_need"
    assert replies == [TEXT_14]
    assert len(jobs.list_all()) == 1
    assert repository.toner_orders_by_phone[phone]["empty_type"] == "compatible"
    assert repository.toner_orders_by_phone[phone]["order_confirmed"] is True
    email_service = service.job_service.email_service
    assert len(email_service.order_emails) == 1
    body = email_service.order_emails[0]["body"]
    assert f"Horario de recogida: {TEXT_PICKUP_STANDARD}" in body
    assert "Estado final previsto" not in body
    assert "Tags:" not in body
    assert "Trazabilidad" not in body


def test_existing_customer_is_checked_from_database_repository() -> None:
    service, repository, _ = build_service()
    phone = "+34600000004"
    repository.mark_customer_exists(phone)

    for text in ["Hola", "Si", "Brother", "HL-L2375DW", "Original"]:
        service.process_incoming_message(phone, text)

    conversation, replies = service.process_incoming_message(phone, "2")
    assert conversation.sage_customer_exists is True
    assert conversation.current_state == "awaiting_empty_pickup_existing_customer"
    assert replies == [TEXT_8, TEXT_9]
    assert repository.toner_orders_by_phone == {}

    conversation, replies = service.process_incoming_message(phone, "No")
    assert conversation.current_state == "awaiting_order_confirmation"
    assert replies[0].startswith("Resumen del pedido:")

    conversation, replies = service.process_incoming_message(phone, "Si")
    assert conversation.current_state == "closed_existing_without_pickup"
    assert repository.toner_orders_by_phone[phone]["customer_exists"] is True
    assert repository.toner_orders_by_phone[phone]["order_confirmed"] is True
    email_service = service.job_service.email_service
    assert len(email_service.order_emails) == 1
    body = email_service.order_emails[0]["body"]
    assert "Marca impresora: Brother" in body
    assert "Unidades de tóner: 2" in body
    assert "Estado final previsto" not in body
    assert "Tags:" not in body
    assert "Trazabilidad" not in body


def test_existing_customer_with_pickup_gets_order_confirmation_and_email() -> None:
    service, repository, _ = build_service()
    phone = "+34600000006"
    repository.mark_customer_exists(phone)

    for text in ["Hola", "Si", "Brother", "HL-L2375DW", "Original", "2", "Si", "3"]:
        service.process_incoming_message(phone, text)

    conversation, replies = service.process_incoming_message(phone, "Original")
    assert conversation.current_state == "awaiting_order_confirmation"
    assert replies[0] == TEXT_PICKUP_STANDARD
    assert replies[1].startswith("Resumen del pedido:")
    assert "- Recogida de vacíos: Sí" in replies[1]
    assert TEXT_CONFIRMATION_PROMPT in replies[1]

    conversation, replies = service.process_incoming_message(phone, "Si")
    assert conversation.current_state == "closed_existing_with_pickup"
    assert replies == [TEXT_14]
    assert repository.toner_orders_by_phone[phone]["order_confirmed"] is True
    assert len(service.job_service.email_service.order_emails) == 1


def test_new_customer_without_pickup_gets_order_confirmation_and_email() -> None:
    service, repository, _ = build_service()
    phone = "+34600000007"

    for text in [
        "Hola",
        "Si",
        "HP",
        "LaserJet Pro",
        "Compatible",
        "4",
        "Calle Mayor 10, Madrid compras@cliente.es",
    ]:
        service.process_incoming_message(phone, text)

    conversation, replies = service.process_incoming_message(phone, "No")
    assert conversation.current_state == "awaiting_order_confirmation"
    assert replies[0].startswith("Resumen del pedido:")
    assert "- Recogida de vacíos: No" in replies[0]
    assert TEXT_CONFIRMATION_PROMPT in replies[0]

    conversation, replies = service.process_incoming_message(phone, "Si")
    assert conversation.current_state == "closed_new_without_pickup"
    assert repository.toner_orders_by_phone[phone]["order_confirmed"] is True
    assert len(service.job_service.email_service.order_emails) == 1


def test_new_customer_with_pickup_gets_standard_schedule_then_order_confirmation_and_email() -> None:
    service, repository, _ = build_service()
    phone = "+34600000008"

    for text in [
        "Hola",
        "Si",
        "HP",
        "LaserJet Pro",
        "Compatible",
        "4",
        "Calle Mayor 10, Madrid compras@cliente.es",
        "Si",
        "6",
    ]:
        service.process_incoming_message(phone, text)

    conversation, replies = service.process_incoming_message(phone, "Compatible")
    assert conversation.current_state == "awaiting_order_confirmation"
    assert replies[0] == TEXT_22
    assert replies[1] == TEXT_PICKUP_STANDARD
    assert replies[2].startswith("Resumen del pedido:")
    assert "- Horario de recogida: " + TEXT_PICKUP_STANDARD in replies[2]
    assert TEXT_CONFIRMATION_PROMPT in replies[2]

    conversation, replies = service.process_incoming_message(phone, "Si")
    assert conversation.current_state == "closed_new_with_pickup"
    assert repository.toner_orders_by_phone[phone]["order_confirmed"] is True
    assert len(service.job_service.email_service.order_emails) == 1


def test_interactive_button_reply_uses_stable_id_before_title() -> None:
    message = {
        "type": "interactive",
        "interactive": {
            "type": "button_reply",
            "button_reply": {
                "id": "TONER_TYPE_ECOLOGICO",
                "title": "Ecológico Ábitat",
            },
        },
    }

    assert extract_message_text(message) == "TONER_TYPE_ECOLOGICO"


def test_order_confirmation_prompt_uses_yes_no_buttons() -> None:
    buttons = buttons_for_text(
        "Resumen del pedido:\n"
        "- Impresora: HP LaserJet\n\n"
        "Responde Sí para confirmar el pedido o No si quieres revisarlo con atención al cliente."
    )

    assert buttons == [
        {"id": "YES", "title": "Sí"},
        {"id": "NO", "title": "No"},
    ]


def test_yes_no_retry_prompt_uses_buttons_and_updated_customer_service_phone() -> None:
    service, _, _ = build_service()
    phone = "+34600000009"

    service.process_incoming_message(phone, "Hola")
    _, replies = service.process_incoming_message(phone, "No entiendo")

    assert replies == [
        "No te he entendido del todo. ¿Necesitas tóner ahora mismo? Responde Sí o No.\n\n"
        "Para cualquier otra consulta, puedes contactar con atención al cliente en el 664 499 424."
    ]
    assert buttons_for_text(replies[0]) == [
        {"id": "YES", "title": "Sí"},
        {"id": "NO", "title": "No"},
    ]


def test_toner_type_retry_prompt_uses_toner_type_buttons() -> None:
    buttons = buttons_for_text(
        "No te he entendido del todo. ¿Prefieres tóner Ecológico Ábitat, Original o Compatible?\n\n"
        "Para cualquier otra consulta, puedes contactar con atención al cliente en el 664 499 424."
    )

    assert buttons == [
        {"id": "TONER_TYPE_ECOLOGICO", "title": "Ecológico Ábitat"},
        {"id": "TONER_TYPE_ORIGINAL", "title": "Original"},
        {"id": "TONER_TYPE_COMPATIBLE", "title": "Compatible"},
    ]


def test_order_email_body_contains_only_order_details() -> None:
    body = build_order_email_body(
        ConversationState(
            phone="34657705038",
            contact_id=2,
            order_confirmed=True,
            sage_customer_exists=True,
            tags=["toner_yes_now"],
            printer_brand="Epson",
            printer_model="2500",
            printer_raw="Epson 2500",
            toner_type="ecologico",
            toner_units=1,
            delivery_address="Calle Mayor 1",
            budget_email="test@test.com",
            empty_pickup_requested=True,
            empty_units=3,
            empty_type="ecologico",
            pickup_slot_text=TEXT_PICKUP_STANDARD,
        )
    )

    assert "Dirección de entrega: Calle Mayor 1" in body
    assert f"Horario de recogida: {TEXT_PICKUP_STANDARD}" in body
    assert "Estado final previsto" not in body
    assert "Tags:" not in body
    assert "Trazabilidad" not in body
    assert "Estado conversacional actual" not in body


def test_ecological_toner_button_variants_are_understood() -> None:
    assert normalize_toner_type("TONER_TYPE_ECOLOGICO") == "ecologico"
    assert normalize_toner_type("àbitat_toner_ecologico") == "ecologico"
    assert normalize_toner_type("Ecológico Ábitat") == "ecologico"


def test_ecological_toner_button_advances_conversation() -> None:
    service, _, _ = build_service()
    phone = "+34600000005"

    for text in ["Hola", "Si", "HP", "LaserJet Pro"]:
        service.process_incoming_message(phone, text)

    conversation, replies = service.process_incoming_message(phone, "àbitat_toner_ecologico")

    assert conversation.current_state == "awaiting_units"
    assert conversation.toner_type == "ecologico"
    assert replies == ["Perfecto. ¿Cuántas unidades necesitas?"]
