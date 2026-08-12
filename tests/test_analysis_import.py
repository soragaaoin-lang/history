import json

import pytest

from chat_history_poc.domain.errors import DecisionValidationError, EvidenceNotFoundError
from chat_history_poc.services.analysis_import_service import AnalysisImportService
from chat_history_poc.services.ingest_service import IngestService


def decision(evidence):
    return {"decisions": [{
        "decision_id": "D-001", "title": "保存形式", "decision": "SQLiteを採用", "context": None,
        "alternatives": ["JSON", "SQLite"], "rationale": ["検索可能"],
        "rejected_alternatives": [{"alternative": "JSON", "reason": "更新が複雑"}],
        "risks": [], "revisit_conditions": [], "evidence_message_ids": evidence,
        "confidence": "high", "missing_information": [], "status": "accepted"
    }]}


def test_schema_validation_rejects_missing_evidence():
    with pytest.raises(DecisionValidationError):
        AnalysisImportService.validate(decision([]))


def test_import_rejects_unknown_evidence(repository, fixture_path, tmp_path):
    session_id, _, _ = IngestService(repository).ingest(fixture_path)
    path = tmp_path / "decisions.json"
    path.write_text(json.dumps(decision(["msg-999999"])), encoding="utf-8")
    with pytest.raises(EvidenceNotFoundError) as error:
        AnalysisImportService(repository).import_file(session_id, path)
    assert "DECISION_EVIDENCE_NOT_FOUND" in str(error.value)


def test_import_and_read_back(repository, fixture_path, tmp_path):
    session_id, _, _ = IngestService(repository).ingest(fixture_path)
    evidence = repository.events(session_id, messages_only=True)[0].id
    path = tmp_path / "decisions.json"
    path.write_text(json.dumps(decision([evidence]), ensure_ascii=False), encoding="utf-8")
    run_id = AnalysisImportService(repository).import_file(session_id, path)
    assert run_id > 0
    assert repository.latest_decisions(session_id)[0].decision == "SQLiteを採用"


def test_cancelled_status_and_prompt_version_are_preserved(repository, fixture_path, tmp_path):
    session_id, _, _ = IngestService(repository).ingest(fixture_path)
    evidence = repository.events(session_id, messages_only=True)[0].id
    data = decision([evidence])
    data["decisions"][0]["status"] = "cancelled"
    path = tmp_path / "decisions.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    run_id = AnalysisImportService(repository).import_file(
        session_id, path, prompt_version="decision_extraction_v1"
    )
    assert repository.latest_decisions(session_id)[0].status == "cancelled"
    with repository.connect() as conn:
        row = conn.execute("SELECT prompt_version FROM analysis_runs WHERE id=?", (run_id,)).fetchone()
    assert row["prompt_version"] == "decision_extraction_v1"
