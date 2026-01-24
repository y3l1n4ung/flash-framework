import sys

import pytest


@pytest.fixture
def temp_task_module(tmp_path):
    """
    Creates a REAL Python file in a temporary directory to serve as a task module.
    Shared across multiple test files to test executors and schedulers.
    """
    # 1. Create a package structure in the temp dir
    pkg_dir = tmp_path / "scheduler_integration"
    pkg_dir.mkdir(exist_ok=True)
    (pkg_dir / "__init__.py").touch()

    # 2. Write the task definitions to the file
    tasks_content = """
import asyncio

async def async_add(x: int, y: int) -> int:
    await asyncio.sleep(0.01)
    return x + y

def sync_multiply(x: int, y: int) -> int:
    return x * y

async def async_success_task(x: int, y: int) -> int:
    await asyncio.sleep(0.01)
    return x + y

async def async_long_running_task() -> int:
    await asyncio.sleep(1.0)
    return 1

def sync_success_task(x: int, y: int) -> int:
    return x * y

async def async_failing_task():
    raise ValueError("Oops async")

def sync_failing_task():
    raise ValueError("Oops sync")
"""
    (pkg_dir / "tasks.py").write_text(tasks_content, encoding="utf-8")

    # 3. Add the temp root to sys.path
    sys.path.insert(0, str(tmp_path))

    full_module_name = "scheduler_integration.tasks"
    yield full_module_name

    # 4. Cleanup
    if str(tmp_path) in sys.path:
        sys.path.remove(str(tmp_path))

    for mod in list(sys.modules):
        if mod.startswith("scheduler_integration"):
            del sys.modules[mod]
