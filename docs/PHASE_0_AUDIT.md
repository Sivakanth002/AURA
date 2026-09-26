# Phase 0: Environment Audit & Architecture Decisions

**Project**: AURA — Autonomous Assistive Robotics Agent  
**Timestamp**: 2026-09-16  
**Auditor**: Antigravity Agent  

---

## 1. System Inventory

| Component | Detected Value | Status / Impact |
| :--- | :--- | :--- |
| **Operating System** | Linux 7.0.0-30-generic x86_64 (Ubuntu 24.04 LTS Noble base) | Supported |
| **Python Runtime** | Python 3.12.3 (`/usr/bin/python3`, `.venv` created) | Supported |
| **ROS 2 Distribution**| **ROS 2 Jazzy Jalisco** located at `/opt/ros/jazzy` | Detected (`rclpy` available) |
| **Colcon Build Tool** | Colcon 0.21.0 | Available on system |
| **Gazebo / Gz** | `gazebo_msgs` available; Full Gazebo sim engine not installed | Dual-mode sim required |
| **Nav2 Stack** | Not installed on host | Replaceable 2D A* occupancy grid required |
| **Hardware GPU** | No dedicated NVIDIA GPU (`nvidia-smi` not found) | CPU-optimized execution |
| **LLM Environment** | No API keys set (`OPENAI_API_KEY`, `GEMINI_API_KEY` empty) | **Deterministic Fallback Engine** required |

---

## 2. Architectural Decisions Derived from Phase 0

1. **Replaceable Navigation & Simulation (Dual-Engine Mode)**:
   - Per Master Prompt Section 6.2 ("If Nav2/Gazebo is impractical in the development environment, implement a 2D simulation with occupancy grid, A*, obstacle detection, dynamic obstacles, route replanning. The navigation interface must remain replaceable"):
   - We will implement a high-fidelity pure Python 2D Grid World with metric topology, accessibility penalties, dynamic obstacles, and differential-drive kinematics in `aura_sim/`.
   - ROS 2 Jazzy packages are scaffolded in `ros2_ws/src/` with `aura_interfaces` and `aura_ros2_bridge` so any ROS 2 deployment can plug directly into Nav2.

2. **Deterministic Fallback Engine (Zero-LLM Operation)**:
   - Per Master Prompt Section 20 & 44 ("If the LLM is unavailable: AURA must degrade gracefully. Fallback: Deterministic state machine + Predefined recovery policies + Deterministic navigation"):
   - We implement `aura_llm/fallback_engine.py` as a primary offline executor that processes goals, executes task decomposition, invokes tools, validates safety, and performs dynamic replanning without relying on external API availability or costs.
   - LLM providers (`OpenAIProvider`, `GeminiProvider`, `LocalProvider`) can be activated by providing API keys in `.env`.

3. **Core Dependencies Verified in `.venv`**:
   - `pydantic 2.13.5`: Strict data contracts and JSON Schema generation.
   - `fastapi 0.141.1` & `uvicorn 0.53.0`: Real-time dashboard backend.
   - `websockets 17.1`: Full-duplex live telemetry and agent trace streaming.
   - `networkx 3.6.1`: Topological graph analysis and accessibility routing.
   - `pytest 9.1.1`: Automated unit, integration, and scenario testing.
   - `pyyaml 6.0.3`: Centralized configuration loading.

---

## 3. Phase 0 Verification Sign-Off

- [x] Environment inspected
- [x] OS, Python 3.12, and ROS 2 Jazzy state established
- [x] Virtual environment `.venv` initialized
- [x] Core dependencies installed and verified
- [x] Architectural assumptions documented
- **Phase 0 Status: COMPLETE** (Ready for Phase 1)
