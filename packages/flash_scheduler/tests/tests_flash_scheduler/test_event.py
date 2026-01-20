import pytest
from datetime import datetime, timedelta
from flash_scheduler.events import Event, EventManager, EventListener, SchedulerEvent
from flash_scheduler.schemas import (
    JobDefinition,
    ExecutionResult,
    IntervalTriggerConfig,
)

# Apply asyncio marker to all tests in this module
pytestmark = pytest.mark.asyncio


class MockListener(EventListener):
    """A concrete implementation of EventListener for testing."""

    def __init__(self):
        self.received_events = []
        self.call_count = 0

    async def on_event(self, event: Event) -> None:
        self.call_count += 1
        self.received_events.append(event)


class FailingListener(EventListener):
    """A listener that consistently raises an exception."""

    async def on_event(self, event: Event) -> None:
        raise ValueError("Simulated listener failure")


def test_event_initialization():
    """Verify that the Event dataclass stores fields correctly using real schemas."""
    now = datetime.now()

    # Real JobDefinition
    job = JobDefinition(
        job_id="test-123",
        name="Test Job",
        func_ref="module:func",
        trigger=IntervalTriggerConfig(seconds=60),
    )

    # Real ExecutionResult based on the provided schema
    result = ExecutionResult(
        job_id="test-123",
        success=True,
        started_at=now,
        finished_at=now + timedelta(seconds=1),
        return_value="done",
        error_message=None,
        error_traceback=None,
    )

    event = Event(
        type=SchedulerEvent.JOB_EXECUTED,
        timestamp=now,
        job_id="test-123",
        job=job,
        result=result,
        payload={"meta": "data"},
    )
    assert event

    assert event.type == SchedulerEvent.JOB_EXECUTED
    assert event.timestamp == now
    assert event.job_id == "test-123"
    assert event.job
    assert event.job.name == "Test Job"
    assert event.result
    assert event.result.success is True
    assert event.result.return_value == "done"
    assert event.payload == {"meta": "data"}


async def test_event_manager_add_remove_listener():
    """Test the registration and unregistration of listeners."""
    manager = EventManager()
    listener = MockListener()

    manager.add_listener(listener)
    assert listener in manager._listeners

    # Ensure duplicates are not added
    manager.add_listener(listener)
    assert len(manager._listeners) == 1

    manager.remove_listener(listener)
    assert listener not in manager._listeners


async def test_event_manager_dispatch_to_single_listener():
    """Verify that dispatch sends the event to a registered listener."""
    manager = EventManager()
    listener = MockListener()
    manager.add_listener(listener)

    event = Event(type=SchedulerEvent.STARTUP, timestamp=datetime.now())
    await manager.dispatch(event)

    assert listener.call_count == 1
    assert listener.received_events[0] == event


async def test_event_manager_dispatch_to_multiple_listeners():
    """Verify that dispatch sends the event to all registered listeners concurrently."""
    manager = EventManager()
    listeners = [MockListener() for _ in range(3)]
    for l in listeners:
        manager.add_listener(l)

    event = Event(type=SchedulerEvent.JOB_ADDED, timestamp=datetime.now())
    await manager.dispatch(event)

    for l in listeners:
        assert l.call_count == 1
        assert l.received_events[0] == event


async def test_event_manager_error_isolation(caplog):
    """
    Ensure that a failing listener does not prevent other listeners
    from receiving events or crash the dispatch process.
    """
    manager = EventManager()
    failing_listener = FailingListener()
    success_listener = MockListener()

    manager.add_listener(failing_listener)
    manager.add_listener(success_listener)

    event = Event(type=SchedulerEvent.JOB_ERROR, timestamp=datetime.now())

    # This should not raise an exception
    await manager.dispatch(event)

    # Success listener should still have been called
    assert success_listener.call_count == 1
    # Check that the error was logged
    assert "Error in event listener" in caplog.text


async def test_dispatch_with_no_listeners():
    """Ensure dispatching with no listeners is a safe no-op."""
    manager = EventManager()
    event = Event(type=SchedulerEvent.SHUTDOWN, timestamp=datetime.now())
    # Should complete without error
    await manager.dispatch(event)
