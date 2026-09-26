#!/usr/bin/env python3
"""Unified Test Suite and Verification Runner for AURA."""

import subprocess
import sys
import time
from pathlib import Path


def run_tests() -> int:
    project_root = Path(__file__).resolve().parent.parent
    venv_pytest = project_root / ".venv" / "bin" / "pytest"

    if not venv_pytest.exists():
        venv_pytest = "pytest"

    print("=" * 70)
    print("🚀 AURA — AUTONOMOUS ASSISTIVE ROBOTICS AGENT")
    print("🎯 Full Regression Test Suite & Verification Runner")
    print("=" * 70)
    print(f"📁 Working Directory: {project_root}")
    print(f"⚙️  Pytest Executable: {venv_pytest}\n")

    start_time = time.time()

    # Execute pytest across unit and integration tests
    cmd = [
        str(venv_pytest),
        str(project_root / "tests"),
        "-v",
        "--tb=short",
    ]

    result = subprocess.run(cmd, cwd=project_root)
    elapsed = time.time() - start_time

    print("\n" + "=" * 70)
    if result.returncode == 0:
        print(f"✅ ALL TESTS PASSED in {elapsed:.2f}s")
        print("🌟 Verification Complete: All subsystem contracts and chaos scenarios satisfied.")
    else:
        print(f"❌ TEST SUITE FAILED with returncode {result.returncode} in {elapsed:.2f}s")
    print("=" * 70)

    return result.returncode


if __name__ == "__main__":
    sys.exit(run_tests())
