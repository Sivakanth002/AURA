"""Unit tests for Phase 2: Differential-drive kinematic robot simulation."""

import math
from aura_core.enums import ReasonCodes, RobotStatus
from aura_core.models import RobotState
from aura_sim.robot_simulator import DifferentialDriveRobotSim


def test_robot_initialization_and_state():
    """Verify robot initializes with configured defaults and valid state."""
    sim = DifferentialDriveRobotSim(robot_id="test_bot", initial_pose=(1.0, 2.0, 0.0))
    state = sim.get_state()
    
    assert isinstance(state, RobotState)
    assert state.robot_id == "test_bot"
    assert state.location == [1.0, 2.0]
    assert state.battery == 100.0
    assert state.status == RobotStatus.AVAILABLE
    assert state.carrying_object is None


def test_kinematics_and_velocity_clamping():
    """Verify differential drive kinematics and max velocity enforcement."""
    sim = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    
    # Request speed exceeding maximum
    sim.set_velocity(linear=5.0, angular=3.0)
    assert sim.linear_velocity == sim.max_linear_velocity
    assert sim.angular_velocity == sim.max_angular_velocity

    # Step forward for 1.0 second
    sim.set_velocity(linear=1.0, angular=0.0)
    sim.step(dt=1.0)
    
    assert math.isclose(sim.x, 1.0, rel_tol=1e-2)
    assert math.isclose(sim.y, 0.0, abs_tol=1e-2)
    assert sim.status == RobotStatus.NAVIGATING


def test_unicycle_navigation_controller():
    """Verify unicycle controller can navigate to a target coordinate."""
    sim = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    target_x, target_y = 2.0, 1.0
    
    # Iterate navigation steps
    reached = False
    for _ in range(100):
        reached = sim.navigate_towards(target_x, target_y, speed=0.5, dt=0.1)
        if reached:
            break
            
    assert reached is True
    assert sim.distance_to(target_x, target_y) <= 0.2
    assert sim.status == RobotStatus.AVAILABLE


def test_interaction_zone_retrieval_and_delivery():
    """Verify interaction-zone state transition for object retrieval and delivery."""
    sim = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    bag_id = "bag_reception_01"
    
    # Object is 5 meters away -> Retrieval must FAIL deterministically
    far_result = sim.retrieve_object(bag_id, [5.0, 0.0])
    assert far_result["success"] is False
    assert far_result["reason_code"] == ReasonCodes.TASK_VERIFICATION_FAILED.value
    assert sim.carrying_object is None

    # Move robot to within 0.5m of object
    sim.x, sim.y = 4.8, 0.0
    close_result = sim.retrieve_object(bag_id, [5.0, 0.0])
    assert close_result["success"] is True
    assert close_result["carrying_object"] == bag_id
    assert sim.carrying_object == bag_id

    # Attempting to retrieve a second object while carrying one must FAIL
    second_result = sim.retrieve_object("another_bag", [4.9, 0.0])
    assert second_result["success"] is False
    assert second_result["reason_code"] == ReasonCodes.TASK_DEPENDENCY_NOT_MET.value

    # Deliver object when far from target -> Must FAIL
    far_delivery = sim.deliver_object([10.0, 10.0])
    assert far_delivery["success"] is False
    assert far_delivery["reason_code"] == ReasonCodes.TASK_VERIFICATION_FAILED.value
    assert sim.carrying_object == bag_id

    # Move to delivery destination -> Must SUCCEED
    sim.x, sim.y = 9.8, 10.0
    valid_delivery = sim.deliver_object([10.0, 10.0])
    assert valid_delivery["success"] is True
    assert valid_delivery["delivered_object"] == bag_id
    assert sim.carrying_object is None


def test_battery_discharge_and_critical_stop():
    """Verify battery drains with distance and critical low battery stops robot."""
    sim = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    sim.set_velocity(1.0, 0.0)
    
    # Traverse 20 meters: 20 * 0.15% = 3.0% drain
    for _ in range(200):
        sim.step(dt=0.1)
    
    assert sim.battery_level < 100.0
    assert math.isclose(sim.battery_level, 97.0, abs_tol=0.2)

    # Force low battery below critical threshold (20%)
    sim.battery_level = 15.0
    sim.step(dt=0.1)
    assert sim.is_battery_critical() is True
    assert sim.status == RobotStatus.ERROR

    # Attempting to set velocity with critical battery must be rejected
    accepted = sim.set_velocity(0.5, 0.0)
    assert accepted is False
    assert sim.linear_velocity == 0.0

    # Recharge restores full functionality
    sim.recharge()
    assert sim.battery_level == 100.0
    assert sim.status == RobotStatus.AVAILABLE


def test_emergency_stop():
    """Verify Emergency Stop deterministically halts motion."""
    sim = DifferentialDriveRobotSim(initial_pose=(0.0, 0.0, 0.0))
    sim.set_velocity(1.0, 0.0)
    
    sim.trigger_estop()
    assert sim.estop_active is True
    assert sim.linear_velocity == 0.0
    assert sim.status == RobotStatus.ESTOP

    # Cannot move while in E-stop
    sim.step(dt=1.0)
    assert sim.x == 0.0
    assert sim.set_velocity(1.0, 0.0) is False

    # Releasing E-stop allows normal operation
    sim.release_estop()
    assert sim.estop_active is False
    assert sim.status == RobotStatus.AVAILABLE
