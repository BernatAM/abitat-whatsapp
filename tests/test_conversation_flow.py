from app.integrations.email import EmailMockService
from app.integrations.whatsapp import extract_message_text
from app.repositories.memory import InMemoryConversationRepository, InMemoryJobRepository
from app.services.conversation import (
    TEXT_4,
    TEXT_5,
    TEXT_6,
    TEXT_8,
    TEXT_9,
    TEXT_14,
    TEXT_17,
    TEXT_19,
    TEXT_20,
    TEXT_22,
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
    _, replies = service.process_incoming_message(phone, "Compatible")
    assert replies == [TEXT_22]

    conversation, replies = service.process_incoming_message(phone, "Martes mañana")
    assert conversation.current_state == "closed_no_need"
    assert replies == [TEXT_14]
    assert len(jobs.list_all()) == 1
    assert repository.toner_orders_by_phone[phone]["empty_type"] == "compatible"


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
    assert repository.toner_orders_by_phone[phone]["customer_exists"] is True


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
