import multiprocessing
import queue
import time
from pathlib import Path

from openadapt_capture import recorder as recorder_module


class _DummyTask:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.started = False

    def start(self) -> None:
        self.started = True

    def join(self, timeout: float | None = None) -> None:
        return None


class _DummyValue:
    def __init__(self, _typecode: str, value: int) -> None:
        self.value = value


class _DummyRecording:
    def __init__(self) -> None:
        self.timestamp = time.time()


def test_record_exits_startup_wait_when_termination_requested(
    monkeypatch,
    tmp_path: Path,
) -> None:
    terminate_processing = multiprocessing.Event()

    monkeypatch.setattr(
        recorder_module,
        "create_recording",
        lambda task_description, capture_dir: (_DummyRecording(), str(tmp_path / "recording.db")),
    )
    monkeypatch.setattr(recorder_module.utils, "WrapStdout", lambda fn: fn)
    monkeypatch.setattr(recorder_module.sq, "SynchronizedQueue", queue.Queue)
    monkeypatch.setattr(recorder_module.threading, "Thread", _DummyTask)
    monkeypatch.setattr(recorder_module.multiprocessing, "Process", _DummyTask)
    monkeypatch.setattr(recorder_module.multiprocessing, "Value", _DummyValue)
    monkeypatch.setattr(recorder_module.config, "RECORD_IMAGES", True)
    monkeypatch.setattr(recorder_module.config, "RECORD_WINDOW_DATA", False)
    monkeypatch.setattr(recorder_module.config, "RECORD_BROWSER_EVENTS", False)
    monkeypatch.setattr(recorder_module.config, "RECORD_VIDEO", False)
    monkeypatch.setattr(recorder_module.config, "RECORD_AUDIO", False)
    monkeypatch.setattr(recorder_module.config, "PLOT_PERFORMANCE", False)

    sleep_calls = 0

    def fake_sleep(_seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 1:
            terminate_processing.set()
            return
        raise AssertionError(
            "record() kept waiting for startup after termination was requested"
        )

    monkeypatch.setattr(recorder_module.time, "sleep", fake_sleep)

    recorder_module.record(
        task_description="test",
        capture_dir=str(tmp_path),
        terminate_processing=terminate_processing,
    )

    assert terminate_processing.is_set()
    assert sleep_calls == 1
