# AURA — Autonomous Assistive Robotics Agent
> *A genuine, fully-autonomous Agentic AI robotics system providing physical assistance, accessible navigation, and multi-tier human-in-the-loop collaboration.*

---

## Overview & Key Architecture Highlights

AURA (Autonomous Assistive Robotics Agent) is engineered as an **Agent-Centric Autonomous System** where AI intelligence is the central coordinator responsible for:
- Understanding multimodal user goals and user accessibility constraints.
- Dynamically synthesizing Directed Acyclic Graph (DAG) mission plans.
- Dispatching strictly-typed tool calls to simulated/physical robotics specialists.
- Monitoring environmental obstacles, battery drain, and task execution in real time.
- Recovering gracefully through runtime DAG splicing and Level-2 Human Confirmation.
- Enforcing un-bypassable deterministic safety boundaries and Emergency Stop controls.

---

## System Architecture & Specialist Layers

```
                                  ┌────────────────────────┐
                                  │      User Request      │
                                  └───────────┬────────────┘
                                              │
                                              ▼
                             ┌─────────────────────────────────┐
                             │    Orchestrator Agent (AURA)    │
                             │   - State Machine (11 states)   │
                             │   - Task Decomposer (DAG)       │
                             │   - Uncertainty Handler         │
                             └───────────────┬─────────────────┘
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼                                           ▼
          ┌─────────────────────────┐                 ┌─────────────────────────┐
          │      Tool Registry      │                 │     Mission Monitor     │
          │  - Pydantic Validation  │                 │  - Battery / Obstacles  │
          │  - Structured JSON Out  │                 │  - Realtime EventBus    │
          └────────────┬────────────┘                 └────────────┬────────────┘
                       │                                           │
         ┌─────────────┼─────────────┐                             │
         ▼             ▼             ▼                             ▼
  ┌────────────┐ ┌────────────┐ ┌────────────┐               ┌────────────┐
  │ Navigation │ │ Perception │ │Accessibil. │               │ Replanner  │
  │ Specialist │ │ Specialist │ │ Specialist │               │ & Splicing │
  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘               └─────┬──────┘
        │              │              │                            │
        └──────────────┴──────┬───────┴────────────────────────────┘
                              │
                              ▼
            ┌──────────────────────────────────┐
            │   Deterministic Safety Gate      │
            │   - Velocity Clamping (<=0.5m/s) │
            │   - Zero-Stairs Prohibitions     │
            │   - Hardware-Level E-STOP        │
            └─────────────────┬────────────────┘
                              │
                              ▼
            ┌──────────────────────────────────┐
            │ Physical Simulation / ROS 2 Jazzy│
            │ - Unicycle Kinematic Integration │
            │ - Campus Grid World & Obstacles  │
            │ - Object Tracker & Camera Vision │
            └──────────────────────────────────┘
```

---

## Quickstart & Demonstration

### 1. Run Complete Automated Regression Suite (74 Tests)
```bash
./scripts/run_all_tests.py
# or
.venv/bin/pytest tests/ -v
```

### 2. Run Benchmark & Accessibility Compliance Engine
```bash
.venv/bin/python3 scripts/benchmark_system.py
```

### 3. Launch Interactive Operator Dashboard (Web UI & Live Map)
```bash
.venv/bin/uvicorn dashboard.app:app --host 0.0.0.0 --port 8000 --reload
```
Open **http://localhost:8000** in your browser to view:
- Live 2D Campus Topology Canvas
- Real-time Robot Telemetry HUD
- Mission Task DAG Lifecycle
- Human-in-the-Loop Clarification Popups
- Chaos Engineering Controls (Block Corridors, Drop Battery, E-STOP)

---

## 🎯 Master Demo Scenarios Covered

1. **Master Scenario 1 (Retrieve Bag + Accessible Guide with Runtime Dynamic Obstacle)**:
   - Robot picks up bag at reception and begins guiding the user to the library.
   - Dynamic obstacle is injected into Corridor A mid-mission.
   - Agent detects blockage, invalidates downstream subtasks, splices an alternative accessible route via Corridor B, and successfully delivers the user to the library without using stairs.
2. **Master Scenario 2 (Sensory Ambiguity & Disambiguation / Level 2 HITL)**:
   - Injects two candidate bags with overlapping confidence ($0.54$ vs $0.48$).
   - `UncertaintyHandler` triggers Level-2 Human Confirmation.
   - User response resolves the ambiguity, boosting selected candidate confidence to $0.98$ and enabling autonomous retrieval.
3. **Master Scenario 3 (All Routes Blocked / Level 3 Escalation)**:
   - Blocks both accessible corridors (A and B).
   - Verifies the agent **strictly refrains** from taking the hazardous staircase and escalates with `NO_SAFE_ROUTE`.
4. **Master Scenario 4 (Critical Low Battery Recovery Trigger)**:
   - Drops battery level below $20\%$, verifying immediate critical health warnings and emergency recovery triggers.

---
