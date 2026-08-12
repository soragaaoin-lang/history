from pathlib import Path

from chat_history_poc.domain.errors import SessionNotFoundError
from chat_history_poc.renderers.markdown_renderer import render_conversation, render_decisions
from chat_history_poc.repositories.sqlite_repository import SQLiteRepository


class RenderService:
    def __init__(self, repository: SQLiteRepository, artifacts_dir: Path):
        self.repository = repository
        self.artifacts_dir = artifacts_dir

    def conversation(self, session_id: str) -> Path:
        self._require(session_id)
        path = self._dir(session_id) / "conversation.md"
        path.write_text(render_conversation(self.repository.events(session_id, messages_only=True)), encoding="utf-8")
        return path

    def decisions(self, session_id: str) -> Path:
        self._require(session_id)
        path = self._dir(session_id) / "decisions.md"
        path.write_text(render_decisions(self.repository.latest_decisions(session_id)), encoding="utf-8")
        return path

    def _dir(self, session_id: str) -> Path:
        path = self.artifacts_dir / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _require(self, session_id: str) -> None:
        if not self.repository.session_exists(session_id):
            raise SessionNotFoundError(session_id)

