"""Human-in-the-Loop (HITL) communication channel and user confirmation manager."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from aura_core.enums import AutonomyLevel, ReasonCodes
from aura_core.events import BaseEvent, global_event_bus
from aura_core.logger import log_decision


class UserInteractionRequest(BaseEvent):
    """Event emitted when agent requires user response or confirmation."""
    event_type: str = "USER_INTERACTION_REQUEST"
    prompt_id: str
    question: str
    options: List[str]
    context: Optional[str] = None
    timeout_seconds: float = 30.0


class UserInteractionResponse(BaseEvent):
    """Event emitted when user provides feedback."""
    event_type: str = "USER_INTERACTION_RESPONSE"
    prompt_id: str
    selected_option: str
    freeform_text: Optional[str] = None


class HumanInTheLoopInterface:
    """Manages asynchronous dialogue, option selection, and timeout policies with the human user."""

    def __init__(self, default_timeout: float = 30.0) -> None:
        self.default_timeout = default_timeout
        self._pending_prompts: Dict[str, asyncio.Future] = {}
        self.interaction_history: List[Dict[str, Any]] = []

        # Subscribe to user responses
        global_event_bus.subscribe("USER_INTERACTION_RESPONSE", self._on_user_response)

    async def _on_user_response(self, event: BaseEvent) -> None:
        if isinstance(event, UserInteractionResponse):
            fut = self._pending_prompts.get(event.prompt_id)
            if fut and not fut.done():
                fut.set_result(event)
                self.interaction_history.append({
                    "prompt_id": event.prompt_id,
                    "response": event.selected_option,
                    "freeform": event.freeform_text,
                    "timestamp": datetime.now(timezone.utc).timestamp(),
                })

    async def request_user_confirmation(
        self,
        question: str,
        options: List[str],
        context: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Dispatches an interactive confirmation request and awaits user response or timeout."""
        prompt_id = f"hitl_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending_prompts[prompt_id] = future

        # Publish request event for UI/Dashboard/Console subscribers
        req_event = UserInteractionRequest(
            event_id=f"evt_{prompt_id}",
            prompt_id=prompt_id,
            question=question,
            options=options,
            context=context,
            timeout_seconds=timeout or self.default_timeout,
        )
        await global_event_bus.publish(req_event)

        log_decision(
            event="USER_CONFIRMATION_REQUESTED",
            trigger="HITL_GATEWAY",
            action="AWAIT_HUMAN_FEEDBACK",
            reason_codes=[ReasonCodes.USER_CLARIFICATION_REQUIRED],
            extra={"prompt_id": prompt_id, "question": question, "options": options},
        )

        wait_time = timeout or self.default_timeout
        try:
            response_event: UserInteractionResponse = await asyncio.wait_for(future, timeout=wait_time)
            del self._pending_prompts[prompt_id]
            return {
                "success": True,
                "prompt_id": prompt_id,
                "selected_option": response_event.selected_option,
                "freeform_text": response_event.freeform_text,
                "timed_out": False,
            }
        except asyncio.TimeoutError:
            if prompt_id in self._pending_prompts:
                del self._pending_prompts[prompt_id]
            log_decision(
                event="USER_CONFIRMATION_TIMEOUT",
                trigger="HITL_TIMEOUT",
                action="FALLBACK_DEFAULT_POLICY",
                reason_codes=[ReasonCodes.TASK_VERIFICATION_FAILED],
                extra={"prompt_id": prompt_id},
            )
            return {
                "success": False,
                "prompt_id": prompt_id,
                "selected_option": options[0] if options else None,
                "timed_out": True,
                "message": f"User interaction timed out after {wait_time}s.",
            }

    async def submit_simulated_user_response(
        self,
        prompt_id: str,
        selected_option: str,
        freeform_text: Optional[str] = None,
    ) -> bool:
        """Simulates incoming user response (used by tests and simulated user actors)."""
        resp_event = UserInteractionResponse(
            event_id=f"resp_{prompt_id}",
            prompt_id=prompt_id,
            selected_option=selected_option,
            freeform_text=freeform_text,
        )
        await global_event_bus.publish(resp_event)
        return True
