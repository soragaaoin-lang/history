import hashlib
import json

from chat_history_poc.services.hybrid_section_run_service import HybridSectionRunService


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_finalizes_valid_first_run(tmp_path):
    bundle = tmp_path / "bundle"
    section = bundle / "sections" / "SEC-001"
    write_json(
        bundle / "HYBRID_RUN_MANIFEST.json",
        {"run_id": "r", "section_runs": [{"section_id": "SEC-001"}]},
    )
    write_json(
        section / "analysis_session.json",
        {
            "projection_version": "3",
            "messages": [{"evidence_id": "MSG-1"}],
            "attachments": [],
        },
    )
    decision = {
        "decision_id": "D-001",
        "title": "t",
        "decision": "d",
        "context": None,
        "alternatives": [],
        "rationale": [],
        "rejected_alternatives": [],
        "risks": [],
        "revisit_conditions": [],
        "evidence_refs": [{"evidence_type": "message", "evidence_id": "MSG-1"}],
        "confidence": "high",
        "missing_information": [],
        "status": "accepted",
    }
    write_json(section / "decisions.raw.json", {"decisions": [decision]})
    digest = hashlib.sha256((section / "decisions.raw.json").read_bytes()).hexdigest()
    write_json(section / "FIRST_RUN_HASH.json", {"sha256": digest})

    output = HybridSectionRunService().finalize(bundle)

    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["state"] == "complete"
    assert summary["decision_count"] == 1
    assert summary["status_distribution"] == {"accepted": 1}
    assert json.loads((section / "RUN_RESULT.json").read_text(encoding="utf-8"))[
        "output_sha256"
    ] == digest
    assert (section / "decisions.validated.json").is_file()


def test_losslessly_repairs_single_string_list_field(tmp_path):
    bundle = tmp_path / "bundle"
    section = bundle / "sections" / "SEC-012"
    write_json(
        bundle / "HYBRID_RUN_MANIFEST.json",
        {"run_id": "r", "section_runs": [{"section_id": "SEC-012"}]},
    )
    write_json(
        section / "analysis_session.json",
        {
            "projection_version": "3",
            "messages": [{"evidence_id": "MSG-1"}],
            "attachments": [],
        },
    )
    decision = {
        "decision_id": "D-001",
        "title": "t",
        "decision": "d",
        "context": None,
        "alternatives": [],
        "rationale": "the exact original rationale",
        "rejected_alternatives": [],
        "risks": [],
        "revisit_conditions": [],
        "evidence_refs": [{"evidence_type": "message", "evidence_id": "MSG-1"}],
        "confidence": "high",
        "missing_information": [],
        "status": "accepted",
    }
    write_json(section / "decisions.raw.json", {"decisions": [decision]})
    digest = hashlib.sha256((section / "decisions.raw.json").read_bytes()).hexdigest()
    write_json(section / "FIRST_RUN_HASH.json", {"sha256": digest})

    output = HybridSectionRunService().finalize(bundle)

    summary = json.loads(output.read_text(encoding="utf-8"))
    result = json.loads((section / "RUN_RESULT.json").read_text(encoding="utf-8"))
    validated = json.loads(
        (section / "decisions.validated.json").read_text(encoding="utf-8")
    )
    assert summary["decision_count"] == 1
    assert summary["repaired_decision_count"] == 1
    assert result["repaired_decision_indices"] == [
        {
            "index": 0,
            "fields": ["rationale"],
            "repair": "wrapped_scalar_string_as_single_item_array",
        }
    ]
    assert validated["decisions"][0]["rationale"] == [
        "the exact original rationale"
    ]
    assert hashlib.sha256((section / "decisions.raw.json").read_bytes()).hexdigest() == digest
