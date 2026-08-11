"""Text contracts for runtime exit cleanup + dirty-port reclaim (lib.rs)."""

from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "src-tauri" / "src" / "lib.rs"


def _lib() -> str:
    return LIB.read_text(encoding="utf-8")


def test_exit_requested_triggers_runtime_cleanup():
    text = _lib()
    assert "ExitRequested" in text
    assert "RunEvent::Exit" in text
    # Cleanup must be shared / invoked on both paths (not only Exit).
    assert "shutdown_owned_runtime" in text or "stop_owned_runtime" in text


def test_windows_job_object_kill_on_close():
    text = _lib()
    assert "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE" in text
    assert "AssignProcessToJobObject" in text or "assign_process_to_job" in text


def test_startup_reclaims_stale_runtime_when_token_rejected():
    text = _lib()
    assert "runtime_accepts_token" in text or "probe_runtime_token" in text
    assert "request_runtime_shutdown" in text
    # Must not unconditionally skip spawn when port is up.
    assert "skip auto-start" in text  # log still ok for accept-token path
    assert "reclaim" in text.lower() or "stale" in text.lower()
