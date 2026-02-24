import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def env_demo_mode(monkeypatch):
    monkeypatch.setenv("UPSTREAM_MODE", "DEMO")
    monkeypatch.delenv("UPSTREAM_BASE_URL", raising=False)
    monkeypatch.delenv("UPSTREAM_API_KEY", raising=False)


@pytest.fixture
def fixed_time_utc(monkeypatch):
    class _FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 1, 15)

    monkeypatch.setattr("app.notify.digest_builder.date", _FixedDate)
    return _FixedDate.today()
