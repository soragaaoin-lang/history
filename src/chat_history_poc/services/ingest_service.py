from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from chat_history_poc.adapters.codex_jsonl import CodexJsonlAdapter
from chat_history_poc.domain.models import NormalizedEvent, RawEvent
from chat_history_poc.repositories.sqlite_repository import SQLiteRepository

logger = logging.getLogger(__name__)


class IngestService:
    def __init__(self, repository: SQLiteRepository, adapter: CodexJsonlAdapter | None = None):
        self.repository = repository
        self.adapter = adapter or CodexJsonlAdapter()

    def ingest(self, source: Path) -> tuple[str, dict[str, int], bool]:
        source = source.resolve()
        sha256 = self._sha256(source)
        existing = self.repository.session_by_hash(sha256)
        if existing:
            return existing, self.report(existing), True
        session_id = sha256[:16]
        pairs: list[tuple[RawEvent, NormalizedEvent]] = []
        with source.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                raw_text = line.rstrip("\r\n")
                parsed = None
                try:
                    value = json.loads(raw_text)
                    parsed = value if isinstance(value, dict) else {}
                    parsed_ok = True
                except (json.JSONDecodeError, UnicodeDecodeError):
                    parsed_ok = False
                event_type = parsed.get("type") if parsed_ok and isinstance(parsed.get("type"), str) else None
                timestamp = parsed.get("timestamp") if parsed_ok and isinstance(parsed.get("timestamp"), str) else None
                raw = RawEvent(id=f"{session_id}-raw-{line_number:06d}", session_id=session_id,
                               source_line=line_number, raw_text=raw_text, parsed_ok=parsed_ok,
                               event_type=event_type, timestamp=timestamp)
                event = self.adapter.normalize(raw, parsed if parsed_ok else None)
                pairs.append((raw, event))
        self.repository.save_ingest(session_id, str(source), sha256, pairs)
        report = self.report(session_id)
        if report["silently_dropped"] != 0:
            raise RuntimeError("Loss detection invariant failed")
        logger.info("source=%s sha256=%s total=%s unknown=%s parse_errors=%s",
                    source, sha256, report["total_lines"], report["unknown_events"], report["parse_errors"])
        return session_id, report, False

    def report(self, session_id: str) -> dict[str, int]:
        counts = self.repository.counts(session_id)
        unknown = counts.get("unknown", 0)
        parse_errors = counts.get("parse_error", 0)
        total = counts.get("total", 0)
        recognized = total - unknown - parse_errors
        classified = recognized + unknown + parse_errors
        return {"total_lines": total, "recognized_events": recognized, "unknown_events": unknown,
                "parse_errors": parse_errors, "silently_dropped": total - classified}

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

