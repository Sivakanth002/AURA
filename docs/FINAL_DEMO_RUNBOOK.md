# 🎬 AURA Final Demonstration Runbook & Judge Demonstration Guide
> **Agentic AI Hackathon — Track 02: Assistive, Accessible & Inclusive Technology**

This document provides a step-by-step walkthrough for evaluating and running all capabilities of **AURA (Autonomous Assistive Robotics Agent)**.

---

## 🛠️ Step 0: Environment Verification

Ensure the virtual environment is ready:
```bash
cd /home/dhyan2006/.gemini/antigravity/scratch/aura
.venv/bin/python3 --version
```

---

## 🧪 Step 1: Run Full Automated Verification Suite

Run all 74 unit tests and integration scenarios:
```bash
./scripts/run_all_tests.py
```
**Expected Outcome:**
- `74 passed in ~1.2s`
- Confirms zero regressions across kinematics, DAG management, path planning, safety validation, and chaos scenarios.

---

## ⚡ Step 2: Run Performance & Accessibility Benchmarking

Execute the benchmark suite:
```bash
.venv/bin/python3 scripts/benchmark_system.py
```
**Expected Output:**
- Path Planning Latency: `< 0.05 ms`
- Tool Dispatch Overhead: `< 0.05 ms`
- Dynamic Replanning Duration: `< 0.5 ms`
- Accessibility Compliance Index: `100.0% (Grade A+)`

---

## 🖥️ Step 3: Launch Live Interactive Web Dashboard

Start the FastAPI / WebSocket dashboard server:
```bash
.venv/bin/uvicorn dashboard.app:app --host 0.0.0.0 --port 8000
```
Open your browser to: **`http://localhost:8000`**

### Live Features to Test in the Dashboard:
1. **Dispatch Master Goal**:
   - In the top search bar, enter:  
     `Get my bag from reception and take me to the library using an accessible route.`
   - Click **Dispatch Goal**.
   - Observe the 9-task DAG populate in real time with live state transitions (`PENDING` $\rightarrow$ `EXECUTING` $\rightarrow$ `VERIFYING` $\rightarrow$ `COMPLETED`).
2. **Dynamic Chaos Obstacle Injection (Master Scenario 1)**:
   - Click **🛑 Block Corridor A** on the right control panel.
   - Observe Corridor A turning red on the map.
   - Observe the agent immediately rerouting through **Corridor B** via the accessible ramp, without using stairs.
3. **Emergency Stop (Hardware Safety Gate)**:
   - Click **🚨 E-STOP** at the top right.
   - Observe all robotic actuation immediately freeze and latch in `ESTOP` status with zero LLM bypass.
