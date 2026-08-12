from pathlib import Path

import pytest

from chat_history_poc.repositories.sqlite_repository import SQLiteRepository


@pytest.fixture
def fixture_path() -> Path:
    return Path(__file__).parent / "fixtures" / "sample_codex_session.jsonl"


@pytest.fixture
def repository(tmp_path: Path) -> SQLiteRepository:
    return SQLiteRepository(tmp_path / "test.db")

