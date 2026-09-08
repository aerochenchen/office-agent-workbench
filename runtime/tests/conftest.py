import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _clear_deployment_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OFFICE_AGENT_DEPLOYMENT", raising=False)
