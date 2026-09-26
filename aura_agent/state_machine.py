"""Formal Agent State Machine with explicit transition matrix and entry/exit hooks."""

from typing import Any, Callable, Dict, List, Optional, Set
from aura_core.enums import AgentState, ReasonCodes
from aura_core.events import AgentStateChangeEvent, global_event_bus
from aura_core.logger import log_decision


class AgentStateMachine:
    """Formal State Machine governing agent lifecycle states, transitions, and hooks (Section 21)."""

    # Allowed state transition matrix
    VALID_TRANSITIONS: Dict[AgentState, Set[AgentState]] = {
        AgentState.IDLE: {
            AgentState.UNDERSTANDING,
            AgentState.PLANNING,
            AgentState.FAILED,
        },
        AgentState.UNDERSTANDING: {
            AgentState.PLANNING,
            AgentState.WAITING_FOR_USER,
            AgentState.ESCALATED,
            AgentState.FAILED,
        },
        AgentState.PLANNING: {
            AgentState.EXECUTING,
            AgentState.WAITING_FOR_USER,
            AgentState.ESCALATED,
            AgentState.FAILED,
        },
        AgentState.EXECUTING: {
            AgentState.MONITORING,
            AgentState.VERIFYING,
            AgentState.REPLANNING,
            AgentState.WAITING_FOR_USER,
            AgentState.ESCALATED,
            AgentState.FAILED,
        },
        AgentState.MONITORING: {
            AgentState.EXECUTING,
            AgentState.VERIFYING,
            AgentState.REPLANNING,
            AgentState.ESCALATED,
            AgentState.FAILED,
        },
        AgentState.VERIFYING: {
            AgentState.EXECUTING,
            AgentState.PLANNING,
            AgentState.REPLANNING,
            AgentState.COMPLETED,
            AgentState.FAILED,
            AgentState.ESCALATED,
        },
        AgentState.REPLANNING: {
            AgentState.PLANNING,
            AgentState.EXECUTING,
            AgentState.WAITING_FOR_USER,
            AgentState.ESCALATED,
            AgentState.FAILED,
        },
        AgentState.WAITING_FOR_USER: {
            AgentState.PLANNING,
            AgentState.EXECUTING,
            AgentState.REPLANNING,
            AgentState.FAILED,
            AgentState.IDLE,
        },
        AgentState.COMPLETED: {
            AgentState.IDLE,
        },
        AgentState.ESCALATED: {
            AgentState.IDLE,
            AgentState.PLANNING,
            AgentState.FAILED,
        },
        AgentState.FAILED: {
            AgentState.IDLE,
            AgentState.PLANNING,
        },
    }

    def __init__(self, initial_state: AgentState = AgentState.IDLE) -> None:
        self.current_state: AgentState = initial_state
        self.state_history: List[AgentState] = [initial_state]
        self._entry_hooks: Dict[AgentState, List[Callable[[AgentState, str], Any]]] = {}
        self._exit_hooks: Dict[AgentState, List[Callable[[AgentState, str], Any]]] = {}

    def register_entry_hook(self, state: AgentState, callback: Callable[[AgentState, str], Any]) -> None:
        """Registers a callback executed when entering a specific state."""
        self._entry_hooks.setdefault(state, []).append(callback)

    def register_exit_hook(self, state: AgentState, callback: Callable[[AgentState, str], Any]) -> None:
        """Registers a callback executed when exiting a specific state."""
        self._exit_hooks.setdefault(state, []).append(callback)

    def can_transition(self, target_state: AgentState) -> bool:
        """Checks if transition from current state to target state is legally allowed."""
        allowed = self.VALID_TRANSITIONS.get(self.current_state, set())
        return target_state in allowed

    async def transition(self, target_state: AgentState, reason: str = "") -> bool:
        """Transitions state, triggering exit and entry hooks and broadcasting event."""
        if not self.can_transition(target_state):
            log_decision(
                event="INVALID_STATE_TRANSITION",
                trigger="STATE_MACHINE_AUDIT",
                action="REJECT_TRANSITION",
                reason_codes=[ReasonCodes.TASK_VERIFICATION_FAILED],
                extra={"from": self.current_state.value, "to": target_state.value, "reason": reason},
            )
            return False

        prev_state = self.current_state

        # Run exit hooks
        for hook in self._exit_hooks.get(prev_state, []):
            try:
                hook(prev_state, reason)
            except Exception:
                pass

        # Update state
        self.current_state = target_state
        self.state_history.append(target_state)

        # Run entry hooks
        for hook in self._entry_hooks.get(target_state, []):
            try:
                hook(target_state, reason)
            except Exception:
                pass

        # Broadcast state change event
        event = AgentStateChangeEvent(
            event_id=f"sm_trans_{target_state.value}_{len(self.state_history)}",
            previous_state=prev_state,
            new_state=target_state,
            reason=reason,
        )
        await global_event_bus.publish(event)
        return True

    def reset(self) -> None:
        """Resets state machine back to IDLE."""
        self.current_state = AgentState.IDLE
        self.state_history = [AgentState.IDLE]
