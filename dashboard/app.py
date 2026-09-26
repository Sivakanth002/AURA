"""FastAPI Backend Server providing REST endpoints and WebSockets for the Operator Dashboard."""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from aura_agent.orchestrator import OrchestratorAgent
from aura_core.enums import AgentState, AutonomyLevel, ReasonCodes
from aura_core.events import BaseEvent, global_event_bus
from aura_sim.failure_injector import FailureInjector


app = FastAPI(title="AURA Operator Dashboard", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files directory
STATIC_DIR = Path("/home/dhyan2006/.gemini/antigravity/scratch/aura/dashboard/static")
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Shared Agent Singleton
agent_instance: Optional[OrchestratorAgent] = None
failure_injector: Optional[FailureInjector] = None
active_websockets: List[WebSocket] = []


def get_agent() -> OrchestratorAgent:
    global agent_instance, failure_injector
    if agent_instance is None:
        agent_instance = OrchestratorAgent()
        failure_injector = FailureInjector(
            grid_world=agent_instance.state_manager.grid_world,
            robot_sim=agent_instance.state_manager.robot_sim,
            object_sim=agent_instance.state_manager.object_sim,
        )
    return agent_instance


# ─── Event Bus to WebSocket Bridge ───────────────────────────────────────────

async def broadcast_event_to_websockets(event: BaseEvent) -> None:
    """Relays event bus messages in real-time to all connected dashboard WebSockets."""
    if not active_websockets:
        return

    payload = {
        "event_type": event.event_type,
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "data": event.model_dump(),
    }
    msg_str = json.dumps(payload)

    disconnected = []
    for ws in active_websockets:
        try:
            await ws.send_text(msg_str)
        except Exception:
            disconnected.append(ws)

    for ws in disconnected:
        if ws in active_websockets:
            active_websockets.remove(ws)


# Subscribe wildcard to event bus
global_event_bus.subscribe("*", broadcast_event_to_websockets)


# ─── REST API Models ─────────────────────────────────────────────────────────

class GoalRequest(BaseModel):
    goal: str
    user_id: Optional[str] = "user_wheelchair_01"


class DisambiguationResponse(BaseModel):
    prompt_id: str
    selected_option: str
    freeform_text: Optional[str] = None


class ObstacleInjectionRequest(BaseModel):
    corridor_id: str
    location: List[float] = [5.0, 8.0]


# ─── REST Endpoints ──────────────────────────────────────────────────────────

@app.get("/")
async def root():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "AURA Operator Dashboard API is running."}


@app.get("/api/state")
async def get_state():
    """Returns full WorldState snapshot."""
    agent = get_agent()
    state = agent.state_manager.get_world_state()
    return {
        "world_state": state.model_dump(),
        "agent_state": agent.state.value,
        "decisions_count": len(agent.decision_history),
    }


@app.get("/api/map")
async def get_map():
    """Returns campus map nodes, edges, and active corridor status."""
    agent = get_agent()
    grid = agent.state_manager.grid_world
    return {
        "nodes": grid.nodes,
        "edges": grid.edges,
        "corridor_status": grid.corridor_status,
    }


@app.get("/api/decisions")
async def get_decisions():
    """Returns structured agent decision logs."""
    agent = get_agent()
    return [d.model_dump() for d in agent.decision_history]


@app.post("/api/goal")
async def submit_goal(req: GoalRequest):
    """Submits a new user goal to the agent."""
    agent = get_agent()
    plan = await agent.accept_goal(req.goal)
    # Run in background execution loop
    asyncio.create_task(agent.run_until_completion_or_halt())
    return {
        "success": True,
        "plan_id": plan.plan_id,
        "tasks_count": len(plan.tasks),
    }


@app.post("/api/step")
async def step_mission():
    """Manually steps one mission subtask."""
    agent = get_agent()
    res = await agent.execute_mission_step()
    return res


@app.post("/api/disambiguate")
async def submit_disambiguation(req: DisambiguationResponse):
    """Submits user disambiguation selection."""
    from aura_core.hitl_interface import UserInteractionResponse
    resp_evt = UserInteractionResponse(
        event_id=f"resp_{req.prompt_id}",
        prompt_id=req.prompt_id,
        selected_option=req.selected_option,
        freeform_text=req.freeform_text,
    )
    await global_event_bus.publish(resp_evt)
    return {"success": True}


@app.post("/api/chaos/inject_obstacle")
async def inject_obstacle(req: ObstacleInjectionRequest):
    """Chaos engineering: injects a dynamic corridor obstacle."""
    global failure_injector
    get_agent()
    if failure_injector:
        res = await failure_injector.inject_obstacle(req.corridor_id, req.location)
        return res
    return {"success": False, "message": "FailureInjector not initialized"}


@app.post("/api/chaos/restore_corridor")
async def restore_corridor(corridor_id: str):
    """Chaos engineering: removes obstacle and restores corridor."""
    global failure_injector
    get_agent()
    if failure_injector:
        res = await failure_injector.restore_route(corridor_id)
        return res
    return {"success": False}


@app.post("/api/chaos/low_battery")
async def inject_low_battery(battery_level: float = 15.0):
    """Chaos engineering: drops battery to critical level."""
    global failure_injector
    get_agent()
    if failure_injector:
        res = failure_injector.inject_low_battery(battery_level)
        return res
    return {"success": False}


@app.post("/api/estop")
async def trigger_estop():
    """Hardware-level Emergency Stop."""
    agent = get_agent()
    res = agent.tools.robot.trigger_estop()
    return {"success": True, "status": "ESTOP"}


@app.post("/api/reset")
async def reset_world():
    """Resets entire simulation and agent state."""
    global agent_instance, failure_injector
    agent_instance = None
    failure_injector = None
    get_agent()
    return {"success": True, "message": "World reset to initial state."}


# ─── WebSocket Endpoint ──────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming ping/commands
            await websocket.send_text(json.dumps({"type": "PONG"}))
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
