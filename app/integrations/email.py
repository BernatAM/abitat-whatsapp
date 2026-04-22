import logging


logger = logging.getLogger(__name__)


class EmailMockService:
    def send_reminder(self, phone: str) -> None:
        subject = "¿Necesitas tóner para tu impresora?"
        body = (
            "Hola, solo pasábamos a recordarte que podemos ayudarte con tóner original, "
            "compatible o ecológico Ábitat. Responde a este email o escríbenos por WhatsApp "
            "cuando lo necesites."
        )
        logger.info("EMAIL mock send reminder phone=%s subject=%s body=%s", phone, subject, body)
