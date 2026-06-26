"""Regression test for the asyncio.create_task GC bug in start_workflow.

Background tasks for the FinRisk workflow were spawned with
``asyncio.create_task(_run_and_store(state))`` and never retained,
allowing CPython's GC to drop them before they completed. This
test starts a background task and asserts that the task remains
live while it is in flight.
"""

from __future__ import annotations

import asyncio

import pytest

from src.api.workflows import _background_tasks


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINRISK_SKIP_BACKGROUND", "1")
    _background_tasks.clear()
    yield
    _background_tasks.clear()


async def test_background_task_is_retained_while_in_flight() -> None:
    """The task must appear in ``_background_tasks`` while it is
    running so the GC cannot collect it.

    We use a custom coroutine instead of the real ``_run_and_store``
    so the test can control how long the task stays in-flight.
    """
    started = asyncio.Event()
    finish = asyncio.Event()

    async def fake_run() -> None:
        started.set()
        await finish.wait()

    task = asyncio.create_task(fake_run())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    await started.wait()
    assert task in _background_tasks, "task was GC'd before completion"
    assert not task.done(), "task finished before retention check"

    # Release the coroutine and wait for the done-callback.
    finish.set()
    await task
    for _ in range(5):
        if task not in _background_tasks:
            break
        await asyncio.sleep(0)
    assert task not in _background_tasks, "done-callback did not discard the task"
