"""Unit tests for Phase 10: Orchestrator Agent and Autonomous Execution Loop."""

import pytest

from aura_core.enums import AgentState, ReasonCodes, TaskStatus
from aura_agent.orchestrator import OrchestratorAgent


@pytest.mark.anyio
async def test_orchestrator_goal_acceptance():
    """Verify goal decomposition and initial state transitions."""
    agent = OrchestratorAgent()
    plan = await agent.accept_goal("Get my bag from reception and take me to the library using an accessible route.")

    assert plan is not None
    assert len(plan.tasks) == 9
    assert agent.current_plan.plan_id == plan.plan_id
    assert len(agent.decision_history) >= 1
    assert agent.decision_history[0].selected_action == "PLAN_DECOMPOSITION"


@pytest.mark.anyio
async def test_orchestrator_execute_mission_step_lifecycle():
    """Verify executing steps through the task manager with verification."""
    agent = OrchestratorAgent()
    await agent.accept_goal("Bring me my bag from reception")

    # Step 1: Locate bag (T01)
    step1 = await agent.execute_mission_step()
    assert step1["status"] == "TASK_COMPLETED"
    assert step1["task_id"] == "T01"

    task1 = agent.task_manager.get_task("T01")
    assert task1.status == TaskStatus.COMPLETED


@pytest.mark.anyio
async def test_orchestrator_full_mission_run_to_completion():
    """Verify full end-to-end execution of a retrieval mission."""
    agent = OrchestratorAgent()
    await agent.accept_goal("Bring me my bag from reception")

    result = await agent.run_until_completion_or_halt(max_steps=10)
    assert result["status"] == "MISSION_COMPLETED"
    assert agent.state == AgentState.COMPLETED
    assert agent.task_manager.is_mission_complete() is True


@pytest.mark.anyio
async def test_orchestrator_dynamic_replanning_on_obstacle():
    """Verify replanning and plan splicing when a route becomes blocked."""
    agent = OrchestratorAgent()
    await agent.accept_goal("Take me to the library using an accessible route")

    # Inject obstacle blocking Corridor A
    agent.state_manager.grid_world.add_dynamic_obstacle("obs_A", [5.0, 8.0], corridor_id="corridor_A")

    # Step through: planner will navigate via alternative Corridor B
    result = await agent.run_until_completion_or_halt(max_steps=10)
    assert result["status"] == "MISSION_COMPLETED"
    assert agent.tools.robot.distance_to(5.0, 12.0) <= 0.5
