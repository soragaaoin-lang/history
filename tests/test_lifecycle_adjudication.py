import json

import pytest

from chat_history_poc.domain.errors import LifecycleAdjudicationError
from chat_history_poc.services.lifecycle_adjudication_service import (
    LifecycleAdjudicationService,
)
from chat_history_poc.services.lifecycle_review_bundle_service import (
    LifecycleReviewBundleService,
)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def integrated_decisions():
    return {
        "decisions": [
            {
                "decision_id": "ID-001",
                "title": "proposal",
                "decision": "use B",
                "status": "proposed",
                "source_decision_keys": ["SEC-001:D-001"],
            },
            {
                "decision_id": "ID-002",
                "title": "already accepted",
                "decision": "use C",
                "status": "accepted",
                "source_decision_keys": ["SEC-002:D-001"],
            },
        ]
    }


def make_section_bundle(tmp_path):
    bundle = tmp_path / "sections"
    write_json(
        bundle / "sections" / "SEC-001" / "analysis_session.json",
        {
            "messages": [
                {
                    "evidence_id": "MSG-1",
                    "actor": "assistant",
                    "source_line": 10,
                    "content": "B is proposed",
                }
            ],
            "attachments": [],
        },
    )
    write_json(
        bundle / "sections" / "SEC-002" / "analysis_session.json",
        {
            "messages": [
                {
                    "evidence_id": "MSG-2",
                    "actor": "human",
                    "source_line": 20,
                    "content": "Proceed with B",
                }
            ],
            "attachments": [],
        },
    )
    return bundle


def test_exports_review_and_applies_evidence_backed_status(tmp_path):
    source = tmp_path / "integrated.json"
    section_bundle = make_section_bundle(tmp_path)
    review = tmp_path / "review"
    output = tmp_path / "output"
    prompt = tmp_path / "prompt.md"
    schema = tmp_path / "schema.json"
    write_json(source, integrated_decisions())
    prompt.write_text("prompt", encoding="utf-8")
    write_json(schema, {"type": "object"})

    LifecycleReviewBundleService().export(
        source,
        section_bundle,
        review,
        prompt_path=prompt,
        schema_path=schema,
    )

    group = review / "groups" / "LIFECYCLE-SEC-001"
    review_input = json.loads(
        (group / "lifecycle_input.json").read_text(encoding="utf-8")
    )
    assert review_input["context_section_ids"] == ["SEC-001", "SEC-002"]
    assert [item["decision_id"] for item in review_input["decisions"]] == ["ID-001"]
    write_json(
        group / "lifecycle.raw.json",
        {
            "group_id": "LIFECYCLE-SEC-001",
            "results": [
                {
                    "decision_id": "ID-001",
                    "final_status": "accepted",
                    "rationale": ["The human instructed implementation."],
                    "evidence_refs": [
                        {"evidence_type": "message", "evidence_id": "MSG-2"}
                    ],
                    "confidence": "high",
                    "missing_information": [],
                }
            ],
        },
    )

    LifecycleAdjudicationService().apply(source, review, output)

    result = json.loads(
        (output / "decisions.lifecycle.json").read_text(encoding="utf-8")
    )
    assert [item["status"] for item in result["decisions"]] == [
        "accepted",
        "accepted",
    ]
    assert result["decisions"][0]["lifecycle_adjudication"]["previous_status"] == "proposed"
    summary = json.loads(
        (output / "LIFECYCLE_SUMMARY.json").read_text(encoding="utf-8")
    )
    assert summary["status_change_count"] == 1
    assert summary["status_after"] == {"accepted": 2}


def test_rejects_unknown_lifecycle_evidence(tmp_path):
    source = tmp_path / "integrated.json"
    section_bundle = make_section_bundle(tmp_path)
    review = tmp_path / "review"
    prompt = tmp_path / "prompt.md"
    schema = tmp_path / "schema.json"
    write_json(source, integrated_decisions())
    prompt.write_text("prompt", encoding="utf-8")
    write_json(schema, {"type": "object"})
    LifecycleReviewBundleService().export(
        source,
        section_bundle,
        review,
        prompt_path=prompt,
        schema_path=schema,
    )
    group = review / "groups" / "LIFECYCLE-SEC-001"
    write_json(
        group / "lifecycle.raw.json",
        {
            "group_id": "LIFECYCLE-SEC-001",
            "results": [
                {
                    "decision_id": "ID-001",
                    "final_status": "accepted",
                    "rationale": ["unsupported"],
                    "evidence_refs": [
                        {"evidence_type": "message", "evidence_id": "MSG-NOT-FOUND"}
                    ],
                    "confidence": "high",
                    "missing_information": [],
                }
            ],
        },
    )

    with pytest.raises(LifecycleAdjudicationError):
        LifecycleAdjudicationService().apply(source, review, tmp_path / "output")
