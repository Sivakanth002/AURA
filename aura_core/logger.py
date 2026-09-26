"""Structured JSON logger and audit trail engine."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from aura_core.enums import ReasonCodes


class StructuredJSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "structured_data"):
            log_entry.update(record.structured_data)  # type: ignore[attr-defined]
        return json.dumps(log_entry)


def get_logger(name: str = "aura") -> logging.Logger:
    """Returns a configured structured logger instance."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredJSONFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


_audit_logger = get_logger("aura.audit")


def log_decision(
    event: str,
    trigger: Optional[str],
    action: str,
    reason_codes: List[ReasonCodes],
    affected_task: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Logs a structured agent decision per Section 28 & 41."""
    data = {
        "event": event,
        "trigger": trigger,
        "action": action,
        "affected_task": affected_task,
        "reason_codes": [rc.value if isinstance(rc, ReasonCodes) else rc for rc in reason_codes],
    }
    if extra:
        data.update(extra)
    _audit_logger.info(action, extra={"structured_data": data})


def log_tool_invocation(
    tool_name: str,
    arguments: Dict[str, Any],
    result: Optional[Dict[str, Any]] = None,
    success: bool = True,
    duration_ms: float = 0.0,
) -> None:
    """Logs tool calls and their verified outcomes."""
    data = {
        "event": "TOOL_INVOCATION",
        "tool": tool_name,
        "arguments": arguments,
        "success": success,
        "duration_ms": duration_ms,
        "result": result,
    }
    _audit_logger.info(f"Tool {tool_name} executed", extra={"structured_data": data})
