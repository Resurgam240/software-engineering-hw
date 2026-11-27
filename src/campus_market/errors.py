"""Public domain failures with safe, stable HTTP representations."""


class DomainError(Exception):
    """Expected rejection; neither SQL nor private input is exposed to clients."""

    def __init__(self, code: str, message: str, status: int = 409, field: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.field = field

    def payload(self) -> dict:
        """Produce the documented business-error envelope."""
        return {"code": self.code, "message": self.message, "field": self.field}


def require(condition: bool, code: str, message: str, status: int = 409, field: str = ""):
    """Keep validation failures explicit at the rule that rejects the operation."""
    if not condition:
        raise DomainError(code, message, status, field)
