from __future__ import annotations

import json
from pathlib import Path

from chat_history_poc.domain.errors import SessionNotFoundError
from chat_history_poc.repositories.sqlite_repository import SQLiteRepository
from chat_history_poc.services.ingest_service import IngestService
from chat_history_poc.services.render_service import RenderService


class FileExchangeAnalysisRunner:
    """Creates files for a human-mediated AI round trip; it never calls an AI API."""

    runner_type = "file_exchange"


class AnalysisBundleService:
    def __init__(self, repository: SQLiteRepository, artifacts_dir: Path, prompt_path: Path):
        self.repository = repository
        self.artifacts_dir = artifacts_dir
        self.prompt_path = prompt_path

    def export(self, session_id: str) -> Path:
        if not self.repository.session_exists(session_id):
            raise SessionNotFoundError(session_id)
        target = self.artifacts_dir / session_id
        target.mkdir(parents=True, exist_ok=True)
        events = self.repository.events(session_id)
        normalized = {"session_id": session_id, "source_type": "codex", "events": [e.to_dict() for e in events]}
        (target / "normalized_session.json").write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        report = IngestService(self.repository).report(session_id)
        (target / "normalization_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        RenderService(self.repository, self.artifacts_dir).conversation(session_id)
        (target / "analysis_prompt.md").write_text(self.prompt_path.read_text(encoding="utf-8"), encoding="utf-8")
        return target

