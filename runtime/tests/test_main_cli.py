from __future__ import annotations

from office_agent.__main__ import DEFAULT_HOST, DEFAULT_PORT, main


def test_main_help_exits_zero(capsys):
    try:
        main(["--help"])
    except SystemExit as e:
        assert e.code == 0
    out = capsys.readouterr().out
    assert "--host" in out
    assert "--port" in out
    assert str(DEFAULT_PORT) in out or DEFAULT_HOST in out


def test_defaults():
    assert DEFAULT_HOST == "127.0.0.1"
    assert DEFAULT_PORT == 8765


def test_run_script_executes(tmp_path, capsys):
    script = tmp_path / "hi.py"
    script.write_text("print('ok-from-run-script')\n", encoding="utf-8")
    main(["--run-script", str(script)])
    assert "ok-from-run-script" in capsys.readouterr().out

