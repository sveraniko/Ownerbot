from __future__ import annotations

import configparser
from pathlib import Path
import re

from app.core.contracts import BASELINE_MIGRATION_MAX_COUNT, BASELINE_MIGRATION_MIN_COUNT


def _versions_dir() -> Path:
    alembic_ini = Path("app/storage/alembic.ini")
    parser = configparser.ConfigParser()
    parser.read(alembic_ini, encoding="utf-8")
    script_location = parser.get("alembic", "script_location")
    return Path(script_location) / "versions"


def test_baseline_only_single_revision_file() -> None:
    versions = _versions_dir()
    revision_files = sorted(path for path in versions.glob("*.py") if path.name != "__init__.py")
    assert len(revision_files) >= BASELINE_MIGRATION_MIN_COUNT
    assert len(revision_files) <= BASELINE_MIGRATION_MAX_COUNT


def test_no_revision_above_0001() -> None:
    revision_files = sorted(path.name for path in _versions_dir().glob("*.py") if path.name != "__init__.py")
    assert not any("0002" in name for name in revision_files)
    assert not any(re.search(r"000[2-9]", name) for name in revision_files)
