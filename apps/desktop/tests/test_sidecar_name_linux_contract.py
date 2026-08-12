from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "src-tauri" / "src" / "lib.rs"


def test_sidecar_exe_name_has_unix_branch():
    text = LIB.read_text(encoding="utf-8")
    assert "office-agent-runtime.exe" in text
    assert '"office-agent-runtime"' in text
    assert "cfg!(windows)" in text or "cfg(windows)" in text
