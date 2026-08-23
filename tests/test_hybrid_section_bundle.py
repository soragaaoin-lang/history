import json

from chat_history_poc.services.ginza_signal_annotator import GinzaSignalAnnotator
from chat_history_poc.services.hybrid_section_bundle_service import HybridSectionBundleService


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class StubAnnotator:
    def annotate_projection(self, value):
        value = json.loads(json.dumps(value))
        value["messages"][0]["signals"] = [
            {"type": "request_candidate", "trigger": "してください"}
        ]
        value["signal_annotation"] = {
            "annotation_version": "ginza-signal-v1",
            "model": "stub",
            "candidate_only": True,
            "signal_types": list(GinzaSignalAnnotator.SIGNAL_TYPES),
            "messages_examined": len(value["messages"]),
            "messages_with_signals": 1,
            "signal_count": 1,
            "signal_counts": {
                name: int(name == "request_candidate")
                for name in GinzaSignalAnnotator.SIGNAL_TYPES
            },
        }
        return value


def test_exports_hybrid_inputs_without_excluding_sections(tmp_path):
    analysis = tmp_path / "analysis.json"
    index = tmp_path / "sections.json"
    prompt = tmp_path / "prompt.md"
    guidance = tmp_path / "guidance.md"
    knowledge = tmp_path / "knowledge.md"
    schema = tmp_path / "decision_analysis_v3.schema.json"
    output = tmp_path / "bundle"
    write_json(
        analysis,
        {
            "session_id": "s",
            "projection_version": "3",
            "messages": [
                {
                    "evidence_id": "MSG-001",
                    "section_id": "SEC-001",
                    "source_line": 1,
                    "actor": "human",
                    "content": "Aしてください",
                },
                {
                    "evidence_id": "MSG-002",
                    "section_id": "SEC-002",
                    "source_line": 2,
                    "actor": "assistant",
                    "content": "B",
                },
            ],
            "attachments": [],
            "constraints": [],
            "implementation_events": [],
        },
    )
    write_json(
        index,
        {
            "status": "candidate_pending_human_adjudication",
            "sections": [
                {"section_id": "SEC-001", "source": {"message_ids": ["MSG-001"], "attachment_ids": []}},
                {"section_id": "SEC-002", "source": {"message_ids": ["MSG-002"], "attachment_ids": []}},
            ],
        },
    )
    prompt.write_text("PROMPT", encoding="utf-8")
    guidance.write_text("GUIDANCE", encoding="utf-8")
    knowledge.write_text("NOTEBOOK", encoding="utf-8")
    schema.write_text("{}", encoding="utf-8")

    HybridSectionBundleService(StubAnnotator()).export(
        analysis,
        index,
        output,
        prompt_path=prompt,
        guidance_path=guidance,
        knowledge_path=knowledge,
        schema_path=schema,
    )

    manifest = json.loads((output / "HYBRID_RUN_MANIFEST.json").read_text(encoding="utf-8"))
    first = json.loads((output / "sections/SEC-001/analysis_session.json").read_text(encoding="utf-8"))
    second = json.loads((output / "sections/SEC-002/analysis_session.json").read_text(encoding="utf-8"))
    assert manifest["section_count"] == 2
    assert len(manifest["section_runs"]) == 2
    assert manifest["signal_annotation_summary"]["signal_count"] == 2
    assert first["messages"][0]["signals"][0]["type"] == "request_candidate"
    assert second["interpretation_knowledge"]["content"] == "NOTEBOOK"
    assert second["interpretation_knowledge"]["authority"] == "interpretation_only_not_evidence"
    assert (output / "analysis_prompt.md").read_text(encoding="utf-8") == "GUIDANCE\n\n---\n\nPROMPT"
