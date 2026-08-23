import json

from chat_history_poc.services.integrated_decision_assembly_service import (
    IntegratedDecisionAssemblyService,
)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def source_decision(key, title, evidence_id):
    section_id, decision_id = key.split(":")
    return {
        "source_decision_key": key,
        "section_id": section_id,
        "source_decision_id": decision_id,
        "title": title,
        "decision": title,
        "context": None,
        "alternatives": [],
        "rationale": [title],
        "rejected_alternatives": [],
        "risks": [],
        "revisit_conditions": [],
        "evidence_refs": [{"evidence_type": "message", "evidence_id": evidence_id}],
        "confidence": "high",
        "missing_information": [],
        "status": "accepted",
    }


def test_assembles_valid_same_decision_cluster(tmp_path):
    candidate = tmp_path / "candidate"
    adjudication = tmp_path / "adjudication"
    output = tmp_path / "output"
    cluster_id = "CLUSTER-0123456789ab"
    first = source_decision("SEC-001:D-001", "old", "MSG-1")
    second = source_decision("SEC-002:D-001", "new", "MSG-2")
    write_json(candidate / "decision_inventory.json", {"decisions": [first, second]})
    write_json(candidate / "candidate_clusters.json", {"clusters": [{"cluster_id": cluster_id}]})
    cluster = adjudication / "clusters" / cluster_id
    write_json(
        cluster / "cluster_input.json",
        {
            "mode": "isolated_cluster_adjudication",
            "cluster_id": cluster_id,
            "decisions": [
                {"source_decision_key": first["source_decision_key"]},
                {"source_decision_key": second["source_decision_key"]},
            ],
            "evidence": [
                {"evidence_type": "message", "evidence_id": "MSG-1"},
                {"evidence_type": "message", "evidence_id": "MSG-2"},
            ],
        },
    )
    write_json(
        cluster / "adjudication.raw.json",
        {
            "cluster_id": cluster_id,
            "judgments": [
                {
                    "judgment_id": "J-001",
                    "relation": "same_decision",
                    "member_decision_keys": [
                        first["source_decision_key"],
                        second["source_decision_key"],
                    ],
                    "direction": None,
                    "rationale": ["same"],
                    "evidence_refs": [
                        {"evidence_type": "message", "evidence_id": "MSG-1"}
                    ],
                    "confidence": "high",
                    "missing_information": [],
                }
            ],
            "unclassified_decision_keys": [],
        },
    )

    IntegratedDecisionAssemblyService().assemble(candidate, adjudication, output)

    result = json.loads((output / "decisions.integrated.json").read_text(encoding="utf-8"))
    assert len(result["decisions"]) == 1
    assert result["decisions"][0]["title"] == "new"
    assert result["decisions"][0]["source_decision_keys"] == [
        "SEC-001:D-001",
        "SEC-002:D-001",
    ]
