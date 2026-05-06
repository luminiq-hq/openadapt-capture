import multiprocessing
import queue
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from openadapt_capture import recorder as recorder_module

if sys.platform == "darwin":
    from openadapt_capture.window import _macos as macos_window
else:
    macos_window = None


class _DummyRecording:
    def __init__(self) -> None:
        self.timestamp = time.time()


class _DummyCounter:
    def __init__(self) -> None:
        self.value = 0


def test_process_events_marks_started_and_can_exit_without_input() -> None:
    started_event = threading.Event()
    terminate_processing = multiprocessing.Event()
    worker = threading.Thread(
        target=recorder_module.process_events,
        args=(
            queue.Queue(),
            queue.Queue(),
            queue.Queue(),
            queue.Queue(),
            queue.Queue(),
            queue.Queue(),
            queue.Queue(),
            _DummyRecording(),
            terminate_processing,
            started_event,
            _DummyCounter(),
            _DummyCounter(),
            _DummyCounter(),
            _DummyCounter(),
            _DummyCounter(),
        ),
        daemon=True,
    )

    worker.start()

    assert started_event.wait(timeout=0.2), (
        "process_events should signal readiness before the first event arrives"
    )

    terminate_processing.set()
    worker.join(timeout=1)
    assert not worker.is_alive(), "process_events should exit after termination with no input"


def test_read_screen_events_marks_started_before_first_screenshot(monkeypatch) -> None:
    started_event = threading.Event()
    terminate_processing = multiprocessing.Event()
    screenshot_entered = threading.Event()
    allow_screenshot_return = threading.Event()

    def fake_take_screenshot():
        screenshot_entered.set()
        allow_screenshot_return.wait(timeout=1)
        return None

    monkeypatch.setattr(recorder_module.utils, "take_screenshot", fake_take_screenshot)

    worker = threading.Thread(
        target=recorder_module.read_screen_events,
        args=(
            queue.Queue(),
            terminate_processing,
            _DummyRecording(),
            started_event,
        ),
        daemon=True,
    )

    worker.start()

    assert screenshot_entered.wait(timeout=0.2), "expected screenshot capture to begin"
    assert started_event.is_set(), (
        "read_screen_events should signal readiness before the first screenshot returns"
    )

    terminate_processing.set()
    allow_screenshot_return.set()
    worker.join(timeout=1)
    assert not worker.is_alive()


def test_read_window_events_marks_started_even_when_window_data_missing(monkeypatch) -> None:
    started_event = threading.Event()
    terminate_processing = multiprocessing.Event()

    monkeypatch.setattr(recorder_module.window, "get_active_window_data", lambda: {})

    worker = threading.Thread(
        target=recorder_module.read_window_events,
        args=(
            queue.Queue(),
            terminate_processing,
            _DummyRecording(),
            started_event,
        ),
        daemon=True,
    )

    worker.start()

    assert started_event.wait(timeout=0.2), (
        "read_window_events should signal readiness even when no initial window sample is available"
    )

    terminate_processing.set()
    worker.join(timeout=1)
    assert not worker.is_alive()


@pytest.mark.skipif(macos_window is None, reason="macOS-specific window capture")
def test_get_active_window_state_tolerates_missing_window_name(monkeypatch) -> None:
    monkeypatch.setattr(
        macos_window,
        "get_active_window_meta",
        lambda: {
            "kCGWindowOwnerName": "Safari",
            "kCGWindowNumber": 123,
            "kCGWindowBounds": {"X": 1, "Y": 2, "Width": 3, "Height": 4},
        },
    )
    monkeypatch.setattr(macos_window, "get_window_data", lambda meta: {})
    monkeypatch.setattr(macos_window, "deepconvert_objc", lambda value: value)

    state = macos_window.get_active_window_state(read_window_data=True)

    assert state is not None
    assert state["title"] == "Safari"
    assert state["window_id"] == 123
    assert state["left"] == 1
    assert state["top"] == 2
    assert state["width"] == 3
    assert state["height"] == 4
