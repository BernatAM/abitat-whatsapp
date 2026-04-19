import logging


logger = logging.getLogger(__name__)


class EmailMockService:
    def send_reminder(self, phone: str) -> None:
        logger.info("EMAIL mock send reminder phone=%s", phone)

