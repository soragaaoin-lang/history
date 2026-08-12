import json
from pathlib import Path

from chat_history_poc.repositories.sqlite_repository import SQLiteRepository
from chat_history_poc.services.analysis_bundle_service import AnalysisBundleService
from chat_history_poc.services.analysis_import_service import AnalysisImportService
from chat_history_poc.services.ingest_service import IngestService
from chat_history_poc.services.render_service import RenderService


def test_complete_file_exchange_flow(tmp_path, fixture_path):
    repo = SQLiteRepository(tmp_path / "db.sqlite")
    artifacts = tmp_path / "artifacts"
    session_id, _, _ = IngestService(repo).ingest(fixture_path)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("prompt", encoding="utf-8")
    bundle = AnalysisBundleService(repo, artifacts, prompt).export(session_id)
    assert {p.name for p in bundle.iterdir()} == {
        "normalized_session.json", "analysis_session.json", "normalization_report.json", "conversation.md", "analysis_prompt.md"
    }
    evidence = repo.events(session_id, messages_only=True)[1].id
    output = {"decisions": [{"decision_id": "D-001", "title": "DB", "decision": "SQLite",
        "context": "ローカルPoC", "alternatives": [], "rationale": [], "rejected_alternatives": [],
        "risks": [], "revisit_conditions": [], "evidence_message_ids": [evidence],
        "confidence": "medium", "missing_information": ["比較理由"], "status": "accepted"}]}
    result = tmp_path / "decisions.json"
    result.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
    AnalysisImportService(repo).import_file(session_id, result)
    markdown = RenderService(repo, artifacts).decisions(session_id)
    assert evidence in markdown.read_text(encoding="utf-8")


def test_v2_prompt_is_exported_without_modification(tmp_path, fixture_path):
    repo = SQLiteRepository(tmp_path / "db.sqlite")
    session_id, _, _ = IngestService(repo).ingest(fixture_path)
    prompt = tmp_path / "decision_extraction_v2.md"
    prompt.write_text("# Decision Extraction Prompt v2\n", encoding="utf-8")
    bundle = AnalysisBundleService(repo, tmp_path / "artifacts", prompt).export(session_id)
    assert (bundle / "analysis_prompt.md").read_text(encoding="utf-8") == "# Decision Extraction Prompt v2\n"
