from __future__ import annotations

import pytest

from office_agent.__main__ import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    _is_loopback_host,
    assert_bind_safety,
    main,
)


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


# --- M11：非回环绑定且无 API token 时必须拒绝启动 ---


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.0.0.2"])
def test_loopback_hosts_without_token_allowed(host):
    assert_bind_safety(host, None)  # 不抛异常即放行


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10", "10.0.0.5", "office.internal"])
def test_non_loopback_without_token_refused(host, capsys):
    with pytest.raises(SystemExit) as exc:
        assert_bind_safety(host, None)
    assert exc.value.code == 2
    assert "refuse to start" in capsys.readouterr().err


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10"])
def test_non_loopback_with_token_allowed(host):
    assert_bind_safety(host, "some-strong-token")


def test_is_loopback_host_unresolvable_treated_as_non_loopback():
    # 域名等无法解析为 IP 的，按非回环处理（安全优先）
    assert _is_loopback_host("example.internal") is False
    assert _is_loopback_host("127.0.0.1") is True


def test_main_refuses_non_loopback_without_token(monkeypatch, capsys):
    monkeypatch.delenv("OFFICE_AGENT_API_TOKEN", raising=False)
    called = []
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: called.append((a, k)))
    with pytest.raises(SystemExit) as exc:
        main(["--host", "0.0.0.0"])
    assert exc.value.code == 2
    assert called == []  # uvicorn 未被启动
    assert "OFFICE_AGENT_API_TOKEN" in capsys.readouterr().err


def test_main_loopback_without_token_starts(monkeypatch):
    monkeypatch.delenv("OFFICE_AGENT_API_TOKEN", raising=False)
    called = []
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: called.append((a, k)))
    main([])
    assert len(called) == 1
    assert called[0][1]["host"] == "127.0.0.1"

