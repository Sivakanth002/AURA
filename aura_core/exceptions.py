"""Domain exceptions for AURA system."""

from typing import List, Optional
from aura_core.enums import ReasonCodes


class AuraException(Exception):
    """Base exception for all AURA domain errors."""
    def __init__(self, message: str, reason_code: Optional[ReasonCodes] = None) -> None:
        super().__init__(message)
        self.message = message
        self.reason_code = reason_code


class SafetyViolationError(AuraException):
    """Raised when an action violates deterministic safety rules."""
    def __init__(self, message: str, reason_code: ReasonCodes = ReasonCodes.SAFETY_LIMIT_EXCEEDED) -> None:
        super().__init__(message, reason_code)


class NavigationBlockedError(AuraException):
    """Raised when path execution is blocked by dynamic obstacles."""
    def __init__(self, message: str, reason_code: ReasonCodes = ReasonCodes.ROUTE_BLOCKED) -> None:
        super().__init__(message, reason_code)


class NoFeasibleRouteError(AuraException):
    """Raised when no accessible route exists between origin and destination."""
    def __init__(self, message: str, reason_code: ReasonCodes = ReasonCodes.NO_SAFE_ROUTE) -> None:
        super().__init__(message, reason_code)


class PerceptionUncertaintyError(AuraException):
    """Raised when perception confidence is below required thresholds."""
    def __init__(self, message: str, reason_code: ReasonCodes = ReasonCodes.LOW_OBJECT_CONFIDENCE) -> None:
        super().__init__(message, reason_code)


class VerificationFailedError(AuraException):
    """Raised when post-action outcome verification fails."""
    def __init__(self, message: str, reason_code: ReasonCodes = ReasonCodes.TASK_VERIFICATION_FAILED) -> None:
        super().__init__(message, reason_code)


class ToolValidationError(AuraException):
    """Raised when tool arguments or preconditions fail validation."""
    def __init__(self, message: str, reason_code: ReasonCodes = ReasonCodes.TASK_DEPENDENCY_NOT_MET) -> None:
        super().__init__(message, reason_code)
