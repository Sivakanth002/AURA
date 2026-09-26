"""Unit tests for Phase 11: Agent State Machine and Dynamic Planner."""

import pytest

from aura_core.enums import AgentState, TaskStatus
from aura_core.models import MissionPlan, Task
from aura_agent.dynamic_planner import DynamicPlanner
from aura_agent.state_machine import AgentStateMachine


@pytest.mark.anyio
async def test_state_machine_legal_transitions():
    """Verify valid state transitions and history tracking."""
    sm = AgentStateMachine()
    assert sm.current_state == AgentState.IDLE

    # IDLE -> UNDERSTANDING -> PLANNING -> EXECUTING -> VERIFYING -> COMPLETED
    assert await sm.transition(AgentState.UNDERSTANDING, "Goal received") is True
    assert await sm.transition(AgentState.PLANNING, "Decomposing") is True
    assert await sm.transition(AgentState.EXECUTING, "Running subtask") is True
    assert await sm.transition(AgentState.VERIFYING, "Checking post-conditions") is True
    assert await sm.transition(AgentState.COMPLETED, "Done") is True

    assert len(sm.state_history) == 6
    assert sm.current_state == AgentState.COMPLETED


@pytest.mark.anyio
async def test_state_machine_rejects_illegal_transition():
    """Verify state machine blocks invalid transition jumps (e.g. IDLE -> COMPLETED directly)."""
    sm = AgentStateMachine()

    # Direct IDLE -> COMPLETED is illegal
    assert sm.can_transition(AgentState.COMPLETED) is False
    res = await sm.transition(AgentState.COMPLETED)
    assert res is False
    assert sm.current_state == AgentState.IDLE


@pytest.mark.anyio
async def test_state_machine_hooks():
    """Verify entry and exit hook execution."""
    sm = AgentStateMachine()
    entered_states = []
    exited_states = []

    sm.register_entry_hook(AgentState.PLANNING, lambda s, r: entered_states.append(s))
    sm.register_exit_hook(AgentState.UNDERSTANDING, lambda s, r: exited_states.append(s))

    await sm.transition(AgentState.UNDERSTANDING)
    await sm.transition(AgentState.PLANNING)

    assert AgentState.UNDERSTANDING in exited_states
    assert AgentState.PLANNING in entered_states


def test_dynamic_planner_dag_validation():
    """Verify cycle detection and prerequisite resolution in task DAG."""
    planner = DynamicPlanner()

    # Valid DAG
    tasks_valid = [
        Task(task_id="T01", description="A", prerequisites=[], expected_outcome="A"),
        Task(task_id="T02", description="B", prerequisites=["T01"], expected_outcome="B"),
    ]
    valid, err = planner.validate_dag(tasks_valid)
    assert valid is True
    assert err is None

    # Circular DAG: T01 -> T02 -> T01
    tasks_circular = [
        Task(task_id="T01", description="A", prerequisites=["T02"], expected_outcome="A"),
        Task(task_id="T02", description="B", prerequisites=["T01"], expected_outcome="B"),
    ]
    invalid, cycle_err = planner.validate_dag(tasks_circular)
    assert invalid is False
    assert "Circular task dependency" in cycle_err
