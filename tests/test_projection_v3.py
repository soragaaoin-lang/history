import json

import pytest

from chat_history_poc.domain.errors import DecisionValidationError, EvidenceNotFoundError, ProjectionInputError
from chat_history_poc.services.decision_v3_validation_service import DecisionV3ValidationService
from chat_history_poc.services.projection_v3_input_service import ProjectionV3InputService


def write_jsonl(path, values):
    path.write_text("\n".join(json.dumps(value, ensure_ascii=False) for value in values) + "\n", encoding="utf-8")


def test_projection_v3_input_loads_linked_attachment(tmp_path):
    messages = tmp_path / "messages.jsonl"
    attachments = tmp_path / "attachments.jsonl"
    write_jsonl(messages, [{"raw_line": 9, "message_id": "MSG-001", "actor": "human", "section_id": "SEC-001"}])
    write_jsonl(attachments, [{
        "attachment_id": "ATT-001", "parent_message_ids": ["MSG-001"], "section_ids": ["SEC-001"],
        "content": "本文", "sha256": "abc", "authority_note": "過去資料",
    }])
    evidence, projected = ProjectionV3InputService().load(messages, attachments)
    assert evidence[9]["message_id"] == "MSG-001"
    assert projected[0]["parent_message_ids"] == ["MSG-001"]


def test_projection_v3_input_rejects_unknown_parent(tmp_path):
    messages = tmp_path / "messages.jsonl"
    attachments = tmp_path / "attachments.jsonl"
    write_jsonl(messages, [{"raw_line": 9, "message_id": "MSG-001", "actor": "human"}])
    write_jsonl(attachments, [{
        "attachment_id": "ATT-001", "parent_message_ids": ["MSG-999"], "section_ids": [],
        "content": "本文", "sha256": "abc", "authority_note": "過去資料",
    }])
    with pytest.raises(ProjectionInputError):
        ProjectionV3InputService().load(messages, attachments)


def decision(refs):
    return {"decisions": [{
        "decision_id": "D-001", "title": "保存", "decision": "保存する", "context": None,
        "alternatives": [], "rationale": [], "rejected_alternatives": [], "risks": [],
        "revisit_conditions": [], "evidence_refs": refs, "confidence": "high",
        "missing_information": [], "status": "accepted",
    }]}


def test_decision_v3_validates_message_and_attachment_evidence(tmp_path):
    analysis = tmp_path / "analysis.json"
    output = tmp_path / "decisions.json"
    analysis.write_text(json.dumps({
        "projection_version": "3",
        "messages": [{"evidence_id": "MSG-001"}],
        "attachments": [{"attachment_id": "ATT-001"}],
    }), encoding="utf-8")
    output.write_text(json.dumps(decision([
        {"evidence_type": "message", "evidence_id": "MSG-001"},
        {"evidence_type": "attachment", "evidence_id": "ATT-001"},
    ])), encoding="utf-8")
    result = DecisionV3ValidationService().validate_files(analysis, output)
    assert result["attachment_evidence_references"] == 1


def test_decision_v3_rejects_unknown_typed_evidence(tmp_path):
    analysis = tmp_path / "analysis.json"
    output = tmp_path / "decisions.json"
    analysis.write_text(json.dumps({"projection_version": "3", "messages": [], "attachments": []}), encoding="utf-8")
    output.write_text(json.dumps(decision([
        {"evidence_type": "attachment", "evidence_id": "ATT-999"},
    ])), encoding="utf-8")
    with pytest.raises(EvidenceNotFoundError):
        DecisionV3ValidationService().validate_files(analysis, output)


def test_decision_v3_rejects_legacy_evidence_field():
    value = decision([])
    value["decisions"][0]["evidence_message_ids"] = value["decisions"][0].pop("evidence_refs")
    with pytest.raises(DecisionValidationError):
        DecisionV3ValidationService.validate(value)
