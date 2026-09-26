#!/usr/bin/env python3
"""Interactive Terminal World State & Campus Map Visualizer for AURA."""

import argparse
import math
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from aura_core.enums import RobotStatus
from aura_core.models import WorldState
from aura_core.state_manager import WorldStateManager
from aura_sim.failure_injector import FailureInjector
from aura_sim.grid_world import CampusGridWorld
from aura_sim.object_simulator import ObjectSimulator
from aura_sim.robot_simulator import DifferentialDriveRobotSim

# ANSI color codes
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"
BG_DARK = "\033[100m"


def render_ascii_map(grid_world: CampusGridWorld, robot: DifferentialDriveRobotSim, objects_sim: ObjectSimulator) -> str:
    """Renders a 2D ASCII spatial map of the campus with robot, objects, and obstacles."""
    # Map bounds in meters: X from -1 to 11, Y from -7 to 13
    # Discretization grid
    x_min, x_max = -1, 11
    y_min, y_max = -7, 13
    
    # Scale: 1 cell = 1m horizontally, 1 line = 1m vertically
    lines = []
    lines.append(f"{BOLD}{CYAN}┌────────────────────────────────────────────────────────────────────────┐{RESET}")
    lines.append(f"{BOLD}{CYAN}│                   AURA CAMPUS MAP & SEMANTIC TOPOLOGY                  │{RESET}")
    lines.append(f"{BOLD}{CYAN}└────────────────────────────────────────────────────────────────────────┘{RESET}")
    
    # Waypoints lookup
    waypoints = {
        (0, 0): f"{GREEN}[RECEPTION]{RESET}",
        (5, 0): f"{BLUE}[JUNCTION]{RESET}",
        (5, -6): f"{MAGENTA}[CLASSROOM]{RESET}",
        (5, 4): f"{CYAN}[CORR_A-S]{RESET}",
        (5, 8): f"{CYAN}[CORR_A-M]{RESET}",
        (10, 0): f"{GREEN}[CORR_B-E]{RESET}",
        (10, 8): f"{GREEN}[CORR_B-RAMP]{RESET}",
        (2, 8): f"{RED}[STAIRS ❌]{RESET}",
        (5, 12): f"{YELLOW}[LIBRARY]{RESET}",
    }

    rx, ry = int(round(robot.x)), int(round(robot.y))
    
    # Check dynamic obstacles
    obstacles = {
        (int(round(obs["location"][0])), int(round(obs["location"][1]))): obs
        for obs in grid_world.dynamic_obstacles.values()
    }

    # Check objects
    objs = {
        (int(round(o.location[0])), int(round(o.location[1]))): o
        for o in objects_sim.get_all_objects()
    }

    for y in range(y_max, y_min - 1, -1):
        row_str = f" {y:2d}m │ "
        x = x_min
        while x <= x_max:
            cell_pos = (x, y)
            if (x, y) == (rx, ry):
                row_str += f"{BOLD}{WHITE}🤖[ROBOT]{RESET} "
                x += 3
            elif cell_pos in obstacles:
                row_str += f"{BOLD}{RED}🛑[BLOCKED]{RESET} "
                x += 3
            elif cell_pos in objs:
                obj = objs[cell_pos]
                icon = "🎒" if obj.type == "bag" else "📚"
                row_str += f"{YELLOW}{icon}[{obj.id[:6]}]{RESET} "
                x += 3
            elif cell_pos in waypoints:
                tag = waypoints[cell_pos]
                row_str += f"{tag} "
                x += 3
            else:
                # Corridor path hints
                if x == 5 and -6 <= y <= 12:
                    row_str += " │  "
                elif y == 0 and 0 <= x <= 10:
                    row_str += " ── "
                elif x == 10 and 0 <= y <= 8:
                    row_str += " ║  "
                elif y == 12 and 5 <= x <= 10:
                    row_str += " ══ "
                else:
                    row_str += " ·  "
                x += 1
        lines.append(row_str)

    lines.append(f"     └{'─' * 52}")
    lines.append(f"       {'  '.join(f'{x:2d}' for x in range(x_min, x_max + 1, 2))}")
    return "\n".join(lines)


def render_dashboard(state_mgr: WorldStateManager) -> str:
    """Renders real-time HUD and system health telemetry."""
    ws = state_mgr.get_world_state()
    robot = ws.robot
    user = ws.user

    # Battery progress bar
    bars = int(robot.battery / 10)
    battery_bar = "█" * bars + "░" * (10 - bars)
    bat_color = GREEN if robot.battery > 40 else (YELLOW if robot.battery > 20 else RED)

    status_color = GREEN if robot.status == RobotStatus.AVAILABLE else (YELLOW if robot.status == RobotStatus.NAVIGATING else RED)

    corr_a_status = ws.environment.get("corridor_A", "CLEAR")
    corr_a_color = GREEN if corr_a_status == "CLEAR" else RED
    corr_b_status = ws.environment.get("corridor_B", "CLEAR")
    corr_b_color = GREEN if corr_b_status == "CLEAR" else RED

    hud = []
    hud.append(f"\n{BOLD}{WHITE}╔══════════════════════════════ TELEMETRY & WORLD STATE ══════════════════════════════╗{RESET}")
    hud.append(f"{BOLD}  ROBOT PLATFORM:{RESET} [{robot.robot_id}]")
    hud.append(f"    • Pose:       X={robot.location[0]:.2f}m, Y={robot.location[1]:.2f}m, Yaw={robot.orientation:.2f} rad")
    hud.append(f"    • Nearest:    {CYAN}{robot.nearest_waypoint}{RESET}")
    hud.append(f"    • Status:     {status_color}{robot.status.value}{RESET}")
    hud.append(f"    • Battery:    {bat_color}[{battery_bar}] {robot.battery:.1f}%{RESET}")
    hud.append(f"    • Carrying:   {MAGENTA}{robot.carrying_object or 'None'}{RESET}")
    hud.append(f"    • Velocity:   Linear={robot.linear_velocity:.2f} m/s, Angular={robot.angular_velocity:.2f} rad/s")
    hud.append("")
    hud.append(f"{BOLD}  USER PROFILE & ACCESSIBILITY:{RESET}")
    hud.append(f"    • User ID:    {user.user_id}")
    hud.append(f"    • Accessible: {GREEN if user.accessible_routes else RED}{user.accessible_routes}{RESET} (Avoids stairs & high inclines)")
    hud.append(f"    • Speed Cap:  {user.speed_limit:.2f} m/s (Reduced speed: {user.reduced_speed})")
    hud.append(f"    • Modality:   {user.interaction.upper()} (Audio feedback: {user.audio_feedback})")
    hud.append("")
    hud.append(f"{BOLD}  ENVIRONMENTAL CORRIDORS:{RESET}")
    hud.append(f"    • Corridor A (Standard route):   {corr_a_color}{corr_a_status}{RESET}")
    hud.append(f"    • Corridor B (Accessible ramp):  {corr_b_color}{corr_b_status}{RESET}")
    hud.append(f"    • Staircase (Short cut):         {RED}{ws.environment.get('stairs_landing', 'ACCESSIBILITY_BLOCKED')}{RESET}")
    hud.append("")
    hud.append(f"{BOLD}  PERCEIVED OBJECTS:{RESET}")
    for obj_id, obj in ws.objects.items():
        hud.append(f"    • [{obj.id}] type={obj.type}, loc={obj.location}, conf={obj.confidence:.2f}, attrs={obj.attributes}")
    hud.append(f"{BOLD}{WHITE}╚══════════════════════════════════════════════════════════════════════════════════════╝{RESET}")
    return "\n".join(hud)


def main() -> None:
    parser = argparse.ArgumentParser(description="AURA World State & Campus Map Visualizer")
    parser.add_argument("--live", action="store_true", help="Run in continuous live refresh mode")
    parser.add_argument("--block-corridor-a", action="store_true", help="Inject a dynamic obstacle into Corridor A")
    parser.add_argument("--json", action="store_true", help="Print raw WorldState JSON schema snapshot")
    args = parser.parse_args()

    grid_world = CampusGridWorld()
    robot_sim = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    object_sim = ObjectSimulator()
    state_mgr = WorldStateManager(grid_world=grid_world, robot_sim=robot_sim, object_sim=object_sim)

    if args.block_corridor_a:
        grid_world.add_dynamic_obstacle("dyn_obs_demo", [5.0, 8.0], corridor_id="corridor_A", radius=0.6)

    if args.json:
        ws = state_mgr.get_world_state()
        print(ws.model_dump_json(indent=2))
        return

    try:
        while True:
            if args.live:
                os.system("clear" if os.name == "posix" else "cls")
            map_str = render_ascii_map(grid_world, robot_sim, object_sim)
            hud_str = render_dashboard(state_mgr)
            print(map_str)
            print(hud_str)

            if not args.live:
                break
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nVisualizer stopped.")


if __name__ == "__main__":
    main()
