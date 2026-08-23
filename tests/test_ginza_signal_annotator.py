import json

import pytest

from chat_history_poc.domain.errors import SignalAnnotationError
from chat_history_poc.services.ginza_signal_annotator import GinzaSignalAnnotator
from chat_history_poc.services.signal_analysis_bundle_service import SignalAnalysisBundleService


def projection():
    return {
        "session_id": "s",
        "projection_version": "3",
        "messages": [
            {
                "evidence_id": "MSG-001",
                "actor": "assistant",
                "source_line": 1,
                "content": "非同期方式と同期方式を比較します。",
            },
            {
                "evidence_id": "MSG-002",
                "actor": "human",
                "source_line": 2,
                "content": "非同期方式は複雑なのでやめよう。同期方式でお願いします。",
            },
        ],
        "attachments": [],
        "constraints": [],
        "implementation_events": [],
    }


class StubAnnotator:
    def annotate_projection(self, value):
        value = json.loads(json.dumps(value))
        value["messages"][0]["signals"] = []
        value["messages"][1]["signals"] = [{"type": "rejection_candidate"}]
        value["signal_annotation"] = {
            "annotation_version": "ginza-signal-v1",
            "model": "stub",
            "candidate_only": True,
            "signal_types": list(GinzaSignalAnnotator.SIGNAL_TYPES),
            "messages_examined": 2,
            "messages_with_signals": 1,
            "signal_count": 1,
            "signal_counts": {name: int(name == "rejection_candidate") for name in GinzaSignalAnnotator.SIGNAL_TYPES},
        }
        return value


def test_exports_separate_signal_bundle_and_preserves_baseline(tmp_path):
    source = tmp_path / "analysis.json"
    base_prompt = tmp_path / "base.md"
    guidance = tmp_path / "guidance.md"
    schema = tmp_path / "decision_analysis_v3.schema.json"
    output = tmp_path / "bundle"
    source.write_text(json.dumps(projection(), ensure_ascii=False), encoding="utf-8")
    baseline = source.read_bytes()
    base_prompt.write_text("BASE", encoding="utf-8")
    guidance.write_text("GUIDANCE", encoding="utf-8")
    schema.write_text("{}", encoding="utf-8")

    SignalAnalysisBundleService(StubAnnotator()).export(
        source,
        output,
        base_prompt_path=base_prompt,
        guidance_path=guidance,
        schema_path=schema,
        baseline_decisions_path=None,
    )

    annotated = json.loads((output / "analysis_session.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "SIGNAL_RUN_MANIFEST.json").read_text(encoding="utf-8"))
    assert source.read_bytes() == baseline
    assert annotated["messages"][1]["signals"][0]["type"] == "rejection_candidate"
    assert annotated["signal_annotation"]["candidate_only"] is True
    assert (output / "analysis_prompt.md").read_text(encoding="utf-8") == "GUIDANCE\n\n---\n\nBASE"
    assert manifest["experiment"]["no_lifecycle_assignment_by_annotator"] is True
    assert manifest["outputs"]["first_ai_output"] == "decisions.raw.json"


def test_rejects_non_projection_v3():
    annotator = GinzaSignalAnnotator(nlp=object())
    with pytest.raises(SignalAnnotationError):
        annotator.annotate_projection({"projection_version": "1", "messages": []})


def test_phrase_rules_cover_six_candidate_types():
    text = (
        "CSV取込を追加してください。それで進めよう。旧方式はやめよう。"
        "複雑なので同期方式にする。まだ決めなくていい。AではなくBにする。"
    )
    types = {
        signal_type
        for signal_type, _, pattern in GinzaSignalAnnotator._PHRASE_RULES
        if pattern.search(text)
    }
    assert types == set(GinzaSignalAnnotator.SIGNAL_TYPES)


def test_refuses_to_overwrite_existing_bundle(tmp_path):
    source = tmp_path / "analysis.json"
    source.write_text(json.dumps(projection()), encoding="utf-8")
    output = tmp_path / "bundle"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")
    file = tmp_path / "input.txt"
    file.write_text("x", encoding="utf-8")
    with pytest.raises(SignalAnnotationError):
        SignalAnalysisBundleService(StubAnnotator()).export(
            source,
            output,
            base_prompt_path=file,
            guidance_path=file,
            schema_path=file,
        )
    assert (output / "keep.txt").read_text(encoding="utf-8") == "keep"
