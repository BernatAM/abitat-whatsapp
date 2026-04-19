import logging


logger = logging.getLogger(__name__)


class SageMockService:
    def __init__(self) -> None:
        self.forced_results: dict[str, bool] = {}

    def check_customer(self, phone: str) -> bool:
        if phone in self.forced_results:
            result = self.forced_results[phone]
            logger.info("SAGE mock forced result phone=%s exists=%s", phone, result)
            return result
        digits = "".join(char for char in phone if char.isdigit())
        last_digit = int(digits[-1]) if digits else 0
        result = last_digit % 2 == 0
        logger.info("SAGE mock computed result phone=%s exists=%s", phone, result)
        return result

    def set_exists(self, phone: str) -> None:
        self.forced_results[phone] = True

    def set_new(self, phone: str) -> None:
        self.forced_results[phone] = False

