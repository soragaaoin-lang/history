import json

import pytest

from chat_history_poc.domain.errors import KnowledgeExperimentError
from chat_history_poc.services.knowledge_experiment_bundle_service import (
    KnowledgeExperimentBundleService,
)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def projection():
    return {
        "session_id": "s",
        "projection_version": "3",
        "messages": [
            {
                "evidence_id": "MSG-001",
                "actor": "human",
                "source_line": 1,
                "content": "Bで進めてください",
            }
        ],
        "attachments": [],
        "constraints": [],
        "implementation_events": [],
    }


def test_exports_prompt_only_and_knowledge_arms(tmp_path):
    source = tmp_path / "analysis.json"
    prompt = tmp_path / "prompt.md"
    knowledge = tmp_path / "knowledge.md"
    schema = tmp_path / "schema.json"
    control = tmp_path / "control.json"
    output = tmp_path / "bundle"
    write_json(source, projection())
    original = source.read_bytes()
    prompt.write_text("PROMPT", encoding="utf-8")
    knowledge.write_text("NOTEBOOK", encoding="utf-8")
    schema.write_text("{}", encoding="utf-8")
    control.write_text('{"decisions": []}', encoding="utf-8")

    KnowledgeExperimentBundleService().export(
        source,
        output,
        prompt_path=prompt,
        knowledge_path=knowledge,
        schema_path=schema,
        control_decisions_path=control,
    )

    prompt_only = output / "prompt_only/analysis_session.json"
    knowledge_input = json.loads(
        (output / "prompt_plus_knowledge/analysis_session.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((output / "EXPERIMENT_MANIFEST.json").read_text(encoding="utf-8"))
    assert prompt_only.read_bytes() == original
    assert "interpretation_knowledge" not in json.loads(prompt_only.read_text(encoding="utf-8"))
    assert knowledge_input["interpretation_knowledge"]["content"] == "NOTEBOOK"
    assert knowledge_input["interpretation_knowledge"]["authority"] == "interpretation_only_not_evidence"
    assert knowledge_input["interpretation_knowledge"]["source_specific_answers"] is False
    assert manifest["arms"][0]["analysis_session_sha256"] == manifest["source"]["analysis_session_sha256"]
    assert manifest["arms"][0]["prompt_sha256"] == manifest["arms"][1]["prompt_sha256"]
    assert manifest["arms"][0]["schema_sha256"] == manifest["arms"][1]["schema_sha256"]


def test_rejects_signal_annotated_input(tmp_path):
    source = tmp_path / "analysis.json"
    value = projection()
    value["signal_annotation"] = {"candidate_only": True}
    write_json(source, value)
    other = tmp_path / "other"
    other.write_text("x", encoding="utf-8")
    with pytest.raises(KnowledgeExperimentError):
        KnowledgeExperimentBundleService().export(
            source,
            tmp_path / "output",
            prompt_path=other,
            knowledge_path=other,
            schema_path=other,
            control_decisions_path=other,
        )


def test_refuses_to_overwrite_existing_output(tmp_path):
    source = tmp_path / "analysis.json"
    write_json(source, projection())
    output = tmp_path / "output"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")
    other = tmp_path / "other"
    other.write_text("x", encoding="utf-8")
    with pytest.raises(KnowledgeExperimentError):
        KnowledgeExperimentBundleService().export(
            source,
            output,
            prompt_path=other,
            knowledge_path=other,
            schema_path=other,
            control_decisions_path=other,
        )
    assert (output / "keep.txt").read_text(encoding="utf-8") == "keep"
