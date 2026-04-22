import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.container import conversation_repository, conversation_service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prueba el flujo conversacional en consola sin red ni HTTP.",
    )
    parser.add_argument(
        "--phone",
        default="+34600000000",
        help="Telefono de la conversacion. Por defecto +34600000000.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Resetea la conversacion antes de empezar.",
    )
    return parser


def reset_conversation(phone: str) -> str:
    conversation_repository.reset(phone)
    return "Conversation reset"


def print_response(phone: str, state: str, replies: list[str]) -> None:
    print(f"\ntelefono: {phone}")
    print(f"estado: {state}")
    if not replies:
        print("respuestas: []")
        return

    print("respuestas:")
    for index, reply in enumerate(replies, start=1):
        print(f"  {index}. {reply}")


def print_state(phone: str) -> None:
    conversation = conversation_repository.get(phone)
    if conversation is None:
        print("sin conversacion")
        return
    print(f"estado actual: {conversation.current_state}")
    print(f"tags: {conversation.tags}")


def main() -> int:
    args = build_parser().parse_args()
    if args.reset:
        print(f"reset ok: {reset_conversation(args.phone)}")

    print(f"telefono: {args.phone}")
    print("Escribe un mensaje y pulsa Enter. Usa /exit para salir.")
    print("Comandos: /reset reinicia, /state muestra estado.")

    while True:
        try:
            text = input("> ").strip()
        except EOFError:
            print()
            return 0

        if not text:
            continue
        if text.lower() in {"/exit", "/quit"}:
            return 0
        if text.lower() == "/reset":
            print(f"reset ok: {reset_conversation(args.phone)}")
            continue
        if text.lower() == "/state":
            print_state(args.phone)
            continue

        conversation, replies = conversation_service.process_incoming_message(args.phone, text)
        print_response(conversation.phone, conversation.current_state, replies)


if __name__ == "__main__":
    sys.exit(main())
