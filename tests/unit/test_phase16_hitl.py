"""Unit tests for Phase 16: Human-in-the-Loop Interface & Confirmation Protocol."""

import asyncio
import pytest

from aura_core.hitl_interface import HumanInTheLoopInterface


@pytest.mark.anyio
async def test_hitl_request_and_response():
    """Verify asynchronous user prompt dispatch and resolution."""
    hitl = HumanInTheLoopInterface(default_timeout=5.0)

    # Spawn background task to answer
    async def _auto_respond():
        await asyncio.sleep(0.05)
        # Find active prompt
        if hitl._pending_prompts:
            prompt_id = list(hitl._pending_prompts.keys())[0]
            await hitl.submit_simulated_user_response(
                prompt_id=prompt_id,
                selected_option="bag_reception_01",
                freeform_text="The black one please",
            )

    asyncio.create_task(_auto_respond())

    result = await hitl.request_user_confirmation(
        question="Which bag should I retrieve?",
        options=["bag_reception_01", "bag_reception_02"],
        timeout=2.0,
    )

    assert result["success"] is True
    assert result["timed_out"] is False
    assert result["selected_option"] == "bag_reception_01"
    assert result["freeform_text"] == "The black one please"


@pytest.mark.anyio
async def test_hitl_timeout_policy():
    """Verify timeout fallback behavior when user does not respond."""
    hitl = HumanInTheLoopInterface(default_timeout=0.1)

    result = await hitl.request_user_confirmation(
        question="Confirm action?",
        options=["option_A", "option_B"],
        timeout=0.1,
    )

    assert result["success"] is False
    assert result["timed_out"] is True
    assert result["selected_option"] == "option_A"
    assert "timed out" in result["message"]
