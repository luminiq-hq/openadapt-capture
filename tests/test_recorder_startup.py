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

    def get_lock(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


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


def _noop_write_fn(*args, **kwargs) -> None:
    pass


def test_write_events_signals_started_before_db_session(monkeypatch) -> None:
    started_event = threading.Event()
    db_called = threading.Event()
    allow_db_return = threading.Event()

    def fake_get_session_for_path(db_path, echo=False):
        db_called.set()
        allow_db_return.wait(timeout=1)
        return SimpleNamespace()

    monkeypatch.setattr(recorder_module, "get_session_for_path", fake_get_session_for_path)
    monkeypatch.setattr(recorder_module.signal, "signal", lambda *args, **kwargs: None)

    worker = threading.Thread(
        target=recorder_module.write_events,
        args=(
            "action",
            _noop_write_fn,
            queue.Queue(),
            _DummyCounter(),
            queue.Queue(),
            _DummyRecording(),
            "/tmp/fake.db",
            threading.Event(),
            started_event,
        ),
        daemon=True,
    )
    worker.start()

    assert db_called.wait(timeout=0.2), "expected DB session creation to begin"
    assert started_event.is_set(), (
        "write_events should signal readiness before DB session is ready"
    )

    allow_db_return.set()
    worker.join(timeout=1)


def test_performance_stats_writer_signals_started_before_db_session(monkeypatch) -> None:
    started_event = threading.Event()
    db_called = threading.Event()
    allow_db_return = threading.Event()

    def fake_get_session_for_path(db_path, echo=False):
        db_called.set()
        allow_db_return.wait(timeout=1)
        return SimpleNamespace()

    monkeypatch.setattr(recorder_module, "get_session_for_path", fake_get_session_for_path)
    monkeypatch.setattr(recorder_module.signal, "signal", lambda *args, **kwargs: None)

    worker = threading.Thread(
        target=recorder_module.performance_stats_writer,
        args=(
            queue.Queue(),
            _DummyRecording(),
            "/tmp/fake.db",
            threading.Event(),
            started_event,
        ),
        daemon=True,
    )
    worker.start()

    assert db_called.wait(timeout=0.2), "expected DB session creation to begin"
    assert started_event.is_set(), (
        "performance_stats_writer should signal readiness before DB session is ready"
    )

    allow_db_return.set()
    worker.join(timeout=1)


def test_memory_writer_signals_started_before_psutil_and_db(monkeypatch) -> None:
    started_event = threading.Event()
    psutil_called = threading.Event()
    allow_psutil_return = threading.Event()
    db_called = threading.Event()
    allow_db_return = threading.Event()

    class _FakeProcess:
        def memory_info(self):
            psutil_called.set()
            allow_psutil_return.wait(timeout=1)
            return SimpleNamespace(rss=0)
        def children(self, recursive=False):
            return []

    monkeypatch.setattr(recorder_module.psutil, "Process", lambda pid: _FakeProcess())

    def fake_get_session_for_path(db_path, echo=False):
        db_called.set()
        allow_db_return.wait(timeout=1)
        return SimpleNamespace()

    monkeypatch.setattr(recorder_module, "get_session_for_path", fake_get_session_for_path)
    monkeypatch.setattr(recorder_module.signal, "signal", lambda *args, **kwargs: None)

    worker = threading.Thread(
        target=recorder_module.memory_writer,
        args=(
            _DummyRecording(),
            "/tmp/fake.db",
            threading.Event(),
            1,
            started_event,
        ),
        daemon=True,
    )
    worker.start()

    assert started_event.wait(timeout=0.2), (
        "memory_writer should signal readiness immediately, before psutil or DB init"
    )

    allow_psutil_return.set()
    allow_db_return.set()
    worker.join(timeout=1)


@pytest.mark.skipif(
    recorder_module.Recorder is None,
    reason="pynput unavailable (headless)",
)
def test_wait_for_ready_tolerates_alive_recorder_without_ready_signal() -> None:
    rec = recorder_module.Recorder("/tmp/test_never_created")
    rec._record_thread = threading.Thread(target=lambda: time.sleep(60), daemon=True)
    rec._record_thread.start()

    ready = rec.wait_for_ready(timeout=0.1)
    assert ready is True, (
        "wait_for_ready should return True when recorder thread is alive even if ready signal was never sent"
    )

    rec._terminate_processing.set()
    rec._record_thread.join(timeout=1)


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
