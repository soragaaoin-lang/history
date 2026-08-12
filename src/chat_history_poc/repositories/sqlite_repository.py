from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

from chat_history_poc.domain.models import DecisionCandidate, NormalizedEvent, RawEvent, RejectedAlternative


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS sessions (
 id TEXT PRIMARY KEY, source_type TEXT NOT NULL, source_file TEXT NOT NULL,
 source_sha256 TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 normalized_at TEXT
);
CREATE TABLE IF NOT EXISTS raw_events (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), source_line INTEGER NOT NULL,
 raw_text TEXT NOT NULL, parsed_ok INTEGER NOT NULL, event_type TEXT, timestamp TEXT,
 UNIQUE(session_id, source_line)
);
CREATE TABLE IF NOT EXISTS messages (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), raw_event_id TEXT NOT NULL REFERENCES raw_events(id),
 source_line INTEGER NOT NULL, source_event_type TEXT, role TEXT, kind TEXT NOT NULL, content TEXT, timestamp TEXT
);
CREATE TABLE IF NOT EXISTS analysis_runs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id),
 prompt_version TEXT NOT NULL, runner_type TEXT NOT NULL, status TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
 id TEXT NOT NULL, analysis_run_id INTEGER NOT NULL REFERENCES analysis_runs(id), session_id TEXT NOT NULL REFERENCES sessions(id),
 title TEXT NOT NULL, decision TEXT NOT NULL, context TEXT, confidence TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'candidate', raw_analysis_json TEXT NOT NULL,
 PRIMARY KEY(analysis_run_id, id)
);
CREATE TABLE IF NOT EXISTS decision_evidence (
 analysis_run_id INTEGER NOT NULL, decision_id TEXT NOT NULL, message_id TEXT NOT NULL REFERENCES messages(id),
 PRIMARY KEY(analysis_run_id, decision_id, message_id),
 FOREIGN KEY(analysis_run_id, decision_id) REFERENCES decisions(analysis_run_id, id)
);
"""


class SQLiteRepository:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def session_by_hash(self, sha256: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM sessions WHERE source_sha256=?", (sha256,)).fetchone()
        return str(row["id"]) if row else None

    def session_exists(self, session_id: str) -> bool:
        with self.connect() as conn:
            return conn.execute("SELECT 1 FROM sessions WHERE id=?", (session_id,)).fetchone() is not None

    def save_ingest(self, session_id: str, source_file: str, sha256: str,
                    pairs: Iterable[tuple[RawEvent, NormalizedEvent]]) -> None:
        with self.connect() as conn:
            conn.execute("INSERT INTO sessions(id,source_type,source_file,source_sha256,normalized_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP)",
                         (session_id, "codex", source_file, sha256))
            for raw, event in pairs:
                conn.execute("INSERT INTO raw_events VALUES(?,?,?,?,?,?,?)",
                             (raw.id, raw.session_id, raw.source_line, raw.raw_text, raw.parsed_ok, raw.event_type, raw.timestamp))
                conn.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?)",
                             (event.id, event.session_id, event.raw_event_id, event.source_line, event.source_event_type,
                              event.role, event.kind, event.content, event.timestamp))

    def events(self, session_id: str, messages_only: bool = False) -> list[NormalizedEvent]:
        query = "SELECT * FROM messages WHERE session_id=?"
        if messages_only:
            query += " AND kind='message'"
        query += " ORDER BY source_line"
        with self.connect() as conn:
            rows = conn.execute(query, (session_id,)).fetchall()
        return [NormalizedEvent(id=r["id"], session_id=r["session_id"], raw_event_id=r["raw_event_id"],
             source_line=r["source_line"], source_event_type=r["source_event_type"], kind=r["kind"], role=r["role"],
             timestamp=r["timestamp"], content=r["content"]) for r in rows]

    def counts(self, session_id: str) -> dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute("SELECT kind,COUNT(*) n FROM messages WHERE session_id=? GROUP BY kind", (session_id,)).fetchall()
            total = conn.execute("SELECT COUNT(*) n FROM raw_events WHERE session_id=?", (session_id,)).fetchone()["n"]
        result = {r["kind"]: r["n"] for r in rows}
        result["total"] = total
        return result

    def message_ids(self, session_id: str) -> set[str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT id FROM messages WHERE session_id=? AND kind='message'", (session_id,)).fetchall()
        return {str(r["id"]) for r in rows}

    def save_decisions(self, session_id: str, decisions: list[DecisionCandidate], raw_json: str,
                       prompt_version: str = "decision_extraction_v2") -> int:
        with self.connect() as conn:
            cur = conn.execute("INSERT INTO analysis_runs(session_id,prompt_version,runner_type,status,completed_at) VALUES(?,?,'file_exchange','completed',CURRENT_TIMESTAMP)",
                               (session_id, prompt_version))
            run_id = int(cur.lastrowid)
            for decision in decisions:
                conn.execute("INSERT INTO decisions(id,analysis_run_id,session_id,title,decision,context,confidence,raw_analysis_json) VALUES(?,?,?,?,?,?,?,?)",
                             (decision.decision_id, run_id, session_id, decision.title, decision.decision,
                              decision.context, decision.confidence, json.dumps(decision.to_dict(), ensure_ascii=False)))
                for message_id in decision.evidence_message_ids:
                    conn.execute("INSERT INTO decision_evidence VALUES(?,?,?)", (run_id, decision.decision_id, message_id))
        return run_id

    def latest_decisions(self, session_id: str) -> list[DecisionCandidate]:
        with self.connect() as conn:
            row = conn.execute("SELECT MAX(id) id FROM analysis_runs WHERE session_id=? AND status='completed'", (session_id,)).fetchone()
            if not row or row["id"] is None:
                return []
            rows = conn.execute("SELECT raw_analysis_json FROM decisions WHERE analysis_run_id=? ORDER BY id", (row["id"],)).fetchall()
        return [_decision_from_dict(json.loads(r["raw_analysis_json"])) for r in rows]


def _decision_from_dict(data: dict) -> DecisionCandidate:
    return DecisionCandidate(
        decision_id=data["decision_id"], title=data["title"], decision=data["decision"], context=data.get("context"),
        alternatives=data.get("alternatives", []), rationale=data.get("rationale", []),
        rejected_alternatives=[RejectedAlternative(**item) for item in data.get("rejected_alternatives", [])],
        risks=data.get("risks", []), revisit_conditions=data.get("revisit_conditions", []),
        evidence_message_ids=data.get("evidence_message_ids", []), confidence=data["confidence"],
        missing_information=data.get("missing_information", []), status=data.get("status", "unknown"),
    )
