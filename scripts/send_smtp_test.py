from __future__ import annotations

import argparse
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


SMTP_KEYS = [
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_FROM_EMAIL",
    "SMTP_TO_EMAIL",
    "SMTP_USE_TLS",
    "SMTP_USE_SSL",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a simple SMTP test email using .env values.")
    parser.add_argument("--env-file", default=".env", help="Path to the env file. Default: .env")
    parser.add_argument("--to", default=None, help="Override SMTP_TO_EMAIL for this test.")
    parser.add_argument("--dry-run", action="store_true", help="Only print loaded SMTP config; do not send.")
    args = parser.parse_args()

    env_path = Path(args.env_file)
    load_env_file(env_path)
    if args.to:
        os.environ["SMTP_TO_EMAIL"] = args.to

    print(f"Loaded env file: {env_path.resolve()}")
    print_smtp_config()

    missing = required_missing()
    if missing:
        raise SystemExit(f"Missing required SMTP variables: {', '.join(missing)}")
    if args.dry_run:
        print("Dry run enabled. No email sent.")
        return

    send_test_email()
    print("SMTP test email sent.")


def load_env_file(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Env file not found: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = strip_quotes(value.strip())


def strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def print_smtp_config() -> None:
    print("SMTP variables:")
    for key in SMTP_KEYS:
        value = os.getenv(key)
        shown = mask_secret(value) if key == "SMTP_PASSWORD" else value
        print(f"- {key}={shown if shown not in (None, '') else '<empty>'}")


def mask_secret(value: str | None) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def required_missing() -> list[str]:
    required = ["SMTP_HOST", "SMTP_FROM_EMAIL", "SMTP_TO_EMAIL"]
    return [key for key in required if not os.getenv(key)]


def send_test_email() -> None:
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    from_email = os.environ["SMTP_FROM_EMAIL"]
    to_email = os.environ["SMTP_TO_EMAIL"]
    use_tls = parse_bool(os.getenv("SMTP_USE_TLS", "true"))
    use_ssl = parse_bool(os.getenv("SMTP_USE_SSL", "false"))

    message = EmailMessage()
    message["Subject"] = "Prueba SMTP Abitat"
    message["From"] = from_email
    message["To"] = to_email
    message.set_content(
        "Email de prueba enviado desde scripts/send_smtp_test.py.\n\n"
        "Si lo recibes, las variables SMTP se estan cargando y el servidor acepta el envio."
    )

    smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    print(f"Connecting to {host}:{port} ssl={use_ssl} tls={use_tls}...")
    with smtp_cls(host, port, timeout=20) as smtp:
        smtp.set_debuglevel(1)
        if use_tls and not use_ssl:
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)


def parse_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "si"}


if __name__ == "__main__":
    main()
