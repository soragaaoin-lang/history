import hashlib
import json

import pytest

from chat_history_poc.domain.errors import SectionBundleError
from chat_history_poc.services.section_analysis_bundle_service import SectionAnalysisBundleService


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def projection():
    return {
        "session_id": "s",
        "projection_version": "3",
        "messages": [
            {"evidence_id": "MSG-001", "section_id": "SEC-001", "source_line": 10, "actor": "human", "content": "A"},
            {"evidence_id": "MSG-002", "section_id": "SEC-002", "source_line": 30, "actor": "human", "content": "B"},
        ],
        "attachments": [{
            "attachment_id": "ATT-001",
            "parent_message_ids": ["MSG-001"],
            "section_ids": ["SEC-001"],
            "content": "資料",
            "sha256": "abc",
            "authority_note": "過去資料",
        }],
        "constraints": [{"id": "C-001", "content": "制約"}],
        "implementation_events": [
            {"id": "E-001", "source_line": 20, "kind": "command"},
            {"id": "E-002", "source_line": 40, "kind": "file_change"},
        ],
    }


def section_index():
    return {
        "status": "candidate_pending_human_adjudication",
        "sections": [
            {"section_id": "SEC-001", "source": {"message_ids": ["MSG-001"], "attachment_ids": ["ATT-001"]}},
            {"section_id": "SEC-002", "source": {"message_ids": ["MSG-002"], "attachment_ids": []}},
        ],
    }


def test_exports_candidate_section_scoped_inputs_without_labels(tmp_path):
    analysis = tmp_path / "analysis.json"
    index = tmp_path / "sections.json"
    prompt = tmp_path / "prompt.md"
    schema = tmp_path / "schema.json"
    output = tmp_path / "bundle"
    write_json(analysis, projection())
    write_json(index, section_index())
    prompt.write_text("prompt", encoding="utf-8")
    schema.write_text("{}", encoding="utf-8")

    SectionAnalysisBundleService().export(
        analysis, index, output, prompt_path=prompt, schema_path=schema
    )

    first = json.loads((output / "sections/SEC-001/analysis_session.json").read_text(encoding="utf-8"))
    second = json.loads((output / "sections/SEC-002/analysis_session.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "SECTION_RUN_MANIFEST.json").read_text(encoding="utf-8"))
    assert [item["evidence_id"] for item in first["messages"]] == ["MSG-001"]
    assert [item["attachment_id"] for item in first["attachments"]] == ["ATT-001"]
    assert first["section_scope"] == {
        "mode": "candidate_section_assisted", "section_id": "SEC-001", "section_gold": False
    }
    assert "title" not in first["section_scope"]
    assert [item["id"] for item in first["implementation_events"]] == ["E-001"]
    assert [item["id"] for item in second["implementation_events"]] == ["E-002"]
    assert manifest["section_count"] == 2
    assert manifest["experiment"]["formal_oracle_experiment"] is False
    assert manifest["section_runs"][0]["input_sha256"] == hashlib.sha256(
        (output / "sections/SEC-001/analysis_session.json").read_bytes()
    ).hexdigest()


def test_rejects_message_not_listed_in_its_section(tmp_path):
    analysis = tmp_path / "analysis.json"
    index = tmp_path / "sections.json"
    prompt = tmp_path / "prompt.md"
    schema = tmp_path / "schema.json"
    value = section_index()
    value["sections"][0]["source"]["message_ids"] = []
    write_json(analysis, projection())
    write_json(index, value)
    prompt.write_text("prompt", encoding="utf-8")
    schema.write_text("{}", encoding="utf-8")
    with pytest.raises(SectionBundleError):
        SectionAnalysisBundleService().export(
            analysis, index, tmp_path / "bundle", prompt_path=prompt, schema_path=schema
        )


def test_rejects_attachment_not_listed_in_section_index(tmp_path):
    analysis = tmp_path / "analysis.json"
    index = tmp_path / "sections.json"
    prompt = tmp_path / "prompt.md"
    schema = tmp_path / "schema.json"
    value = section_index()
    value["sections"][0]["source"]["attachment_ids"] = []
    write_json(analysis, projection())
    write_json(index, value)
    prompt.write_text("prompt", encoding="utf-8")
    schema.write_text("{}", encoding="utf-8")
    with pytest.raises(SectionBundleError):
        SectionAnalysisBundleService().export(
            analysis, index, tmp_path / "bundle", prompt_path=prompt, schema_path=schema
        )


def test_refuses_to_overwrite_existing_bundle(tmp_path):
    analysis = tmp_path / "analysis.json"
    index = tmp_path / "sections.json"
    prompt = tmp_path / "prompt.md"
    schema = tmp_path / "schema.json"
    output = tmp_path / "bundle"
    output.mkdir()
    (output / "existing.txt").write_text("keep", encoding="utf-8")
    write_json(analysis, projection())
    write_json(index, section_index())
    prompt.write_text("prompt", encoding="utf-8")
    schema.write_text("{}", encoding="utf-8")
    with pytest.raises(SectionBundleError):
        SectionAnalysisBundleService().export(
            analysis, index, output, prompt_path=prompt, schema_path=schema
        )
    assert (output / "existing.txt").read_text(encoding="utf-8") == "keep"
