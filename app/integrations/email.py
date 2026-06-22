import logging
import smtplib
from email.message import EmailMessage

from app.domain.models import ConversationState


logger = logging.getLogger(__name__)


class EmailMockService:
    def __init__(self) -> None:
        self.order_emails: list[dict[str, str]] = []

    def send_reminder(self, phone: str) -> None:
        subject = "¿Necesitas tóner para tu impresora?"
        body = (
            "Hola, solo pasábamos a recordarte que podemos ayudarte con tóner original, "
            "compatible o ecológico Ábitat. Responde a este email o escríbenos por WhatsApp "
            "cuando lo necesites."
        )
        logger.info("EMAIL mock send reminder phone=%s subject=%s body=%s", phone, subject, body)

    def send_order_confirmed(self, conversation: ConversationState) -> None:
        subject = _order_subject(conversation)
        body = build_order_email_body(conversation)
        self.order_emails.append({"subject": subject, "body": body})
        logger.info("EMAIL mock send order phone=%s subject=%s body=%s", conversation.phone, subject, body)


class SmtpEmailService:
    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        from_email: str,
        to_email: str,
        use_tls: bool = True,
        use_ssl: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.to_email = to_email
        self.use_tls = use_tls
        self.use_ssl = use_ssl

    def send_reminder(self, phone: str) -> None:
        logger.info("SMTP reminder email is not configured for phone=%s", phone)

    def send_order_confirmed(self, conversation: ConversationState) -> None:
        message = EmailMessage()
        message["Subject"] = _order_subject(conversation)
        message["From"] = self.from_email
        message["To"] = self.to_email
        message.set_content(build_order_email_body(conversation))

        smtp_cls = smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
        with smtp_cls(self.host, self.port, timeout=20) as smtp:
            if self.use_tls and not self.use_ssl:
                smtp.starttls()
            if self.username and self.password:
                smtp.login(self.username, self.password)
            smtp.send_message(message)
        logger.info("SMTP order email sent phone=%s to=%s", conversation.phone, self.to_email)


def build_order_email_body(conversation: ConversationState) -> str:
    lines = [
        "Pedido confirmado desde WhatsApp",
        "",
        "Datos generales",
        f"- Teléfono WhatsApp: {conversation.phone}",
        f"- Contact ID: {_value(conversation.contact_id)}",
        f"- Pedido confirmado: {'Sí' if conversation.order_confirmed else 'No'}",
        f"- Cliente existente: {_bool_value(conversation.sage_customer_exists)}",
        "",
        "Tóner",
        f"- Marca impresora: {_value(conversation.printer_brand)}",
        f"- Modelo impresora: {_value(conversation.printer_model)}",
        f"- Impresora completa: {_value(conversation.printer_raw)}",
        f"- Tipo de tóner: {_value(conversation.toner_type)}",
        f"- Unidades de tóner: {_value(conversation.toner_units)}",
        "",
        "Presupuesto y entrega",
        f"- Dirección de entrega: {_value(conversation.delivery_address)}",
        f"- Email presupuesto: {_value(conversation.budget_email)}",
        "",
        "Recogida de vacíos",
        f"- Solicita recogida: {_bool_value(conversation.empty_pickup_requested)}",
        f"- Unidades de vacíos: {_value(conversation.empty_units)}",
        f"- Tipo de vacíos: {_value(conversation.empty_type)}",
        f"- Horario de recogida: {_value(conversation.pickup_slot_text)}",
    ]
    return "\n".join(lines)


def _order_subject(conversation: ConversationState) -> str:
    return f"Pedido WhatsApp confirmado - {conversation.phone}"


def _value(value: object) -> str:
    return "Pendiente/no indicado" if value is None or value == "" else str(value)


def _bool_value(value: bool | None) -> str:
    if value is True:
        return "Sí"
    if value is False:
        return "No"
    return "Pendiente/no indicado"
