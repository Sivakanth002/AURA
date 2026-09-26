"""Abstract Base Class for all AURA domain specialist modules."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseSpecialist(ABC):
    """Base specialist interface providing common logging and telemetry hooks."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Returns the operational status of the specialist."""
        pass
