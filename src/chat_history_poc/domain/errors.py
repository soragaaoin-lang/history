class PocError(Exception):
    """Base error with a stable machine-readable code."""

    code = "POC_ERROR"

    def __str__(self) -> str:
        return f"{self.code}: {super().__str__()}"


class SessionNotFoundError(PocError):
    code = "SESSION_NOT_FOUND"


class DecisionValidationError(PocError):
    code = "DECISION_VALIDATION_ERROR"


class EvidenceNotFoundError(PocError):
    code = "DECISION_EVIDENCE_NOT_FOUND"

