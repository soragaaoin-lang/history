from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from chat_history_poc.domain.errors import IntegrationCandidateError
from chat_history_poc.services.integration_candidate_service import IntegrationCandidateService


def decision(decision_id: str, title: str, text: str, evidence_id: str, status: str = "accepted"):
    return {
        "decision_id": decision_id,
        "title": title,
        "decision": text,
        "context": None,
        "alternatives": [],
        "rationale": [],
        "rejected_alternatives": [],
        "risks": [],
        "revisit_conditions": [],
        "evidence_refs": [{"evidence_type": "message", "evidence_id": evidence_id}],
        "confidence": "high",
        "missing_information": [],
        "status": status,
    }


class IntegrationCandidateServiceTest(unittest.TestCase):
    def make_bundle(self, root: Path) -> Path:
        bundle = root / "source"
        inputs = [
            ("SEC-001", "MSG-001", decision("D-001", "マイグレーションをSHA-256で検証", "適用済みマイグレーションのSHA-256を保存して変更を検出する。", "MSG-001")),
            ("SEC-002", "MSG-002", decision("D-001", "マイグレーションのSHA-256検証", "マイグレーションのSHA-256を履歴へ保存し、適用後の変更を検出する。", "MSG-002")),
            ("SEC-003", "MSG-003", decision("D-001", "Gmailの差分同期", "Gmail APIのhistoryIdを使って差分同期する。", "MSG-003")),
            ("SEC-004", "MSG-004", decision("D-001", "マイグレーションSHA-256方式を置き換え", "SHA-256履歴方式を新しい署名方式へ置き換える。", "MSG-004", "superseded")),
        ]
        for number, (section_id, message_id, item) in enumerate(inputs, start=1):
            directory = bundle / "sections" / section_id
            directory.mkdir(parents=True)
            analysis = {
                "session_id": "session-1",
                "projection_version": "3",
                "section_scope": {
                    "mode": "candidate_section_assisted",
                    "section_id": section_id,
                    "section_gold": False,
                },
                "messages": [{
                    "evidence_id": message_id,
                    "section_id": section_id,
                    "source_line": number * 10,
                    "actor": "human",
                    "content": item["decision"],
                }],
                "attachments": [],
                "constraints": [],
                "implementation_events": [],
            }
            decisions = {"decisions": [item]}
            self.write_json(directory / "analysis_session.json", analysis)
            self.write_json(directory / "decisions.raw.json", decisions)
            digest = hashlib.sha256((directory / "decisions.raw.json").read_bytes()).hexdigest()
            self.write_json(directory / "RUN_RESULT.json", {"output_sha256": digest, "state": "valid"})
        return bundle

    @staticmethod
    def write_json(path: Path, value) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def tree_hashes(path: Path) -> dict[str, str]:
        return {
            file.relative_to(path).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
            for file in sorted(path.rglob("*")) if file.is_file()
        }

    def test_exports_deterministic_review_candidates_without_merging(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.make_bundle(root)
            before = self.tree_hashes(source)
            first = root / "first"
            second = root / "second"
            service = IntegrationCandidateService()
            service.export(source, first)
            service.export(source, second)

            inventory = json.loads((first / "decision_inventory.json").read_text(encoding="utf-8"))
            clusters = json.loads((first / "candidate_clusters.json").read_text(encoding="utf-8"))
            evaluation = json.loads((first / "INTEGRATION_CANDIDATE_EVALUATION.json").read_text(encoding="utf-8"))
            self.assertEqual(4, inventory["decision_count"])
            self.assertGreaterEqual(clusters["cluster_count"], 1)
            self.assertFalse(clusters["automatic_merge_performed"])
            self.assertEqual(0, evaluation["evidence_missing_count"])
            self.assertEqual(0, evaluation["pair_only_review_decision_count"])
            self.assertEqual(
                sum(len(cluster["member_decision_keys"]) - 1 for cluster in clusters["clusters"]),
                evaluation["selected_cluster_edge_count"],
            )
            self.assertEqual(before, self.tree_hashes(source))
            self.assertEqual(self.tree_hashes(first), self.tree_hashes(second))
            for cluster in clusters["clusters"]:
                self.assertFalse(cluster["automatic_merge_allowed"])
                cluster_input = json.loads(
                    (first / "clusters" / cluster["cluster_id"] / "integration_input.json").read_text(encoding="utf-8")
                )
                self.assertFalse(cluster_input["automatic_merge_allowed"])

    def test_rejects_frozen_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.make_bundle(root)
            result_path = source / "sections" / "SEC-001" / "RUN_RESULT.json"
            self.write_json(result_path, {"output_sha256": "wrong", "state": "valid"})
            with self.assertRaises(IntegrationCandidateError):
                IntegrationCandidateService().export(source, root / "output")

    def test_refuses_nonempty_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.make_bundle(root)
            output = root / "output"
            output.mkdir()
            (output / "keep.txt").write_text("keep", encoding="utf-8")
            with self.assertRaises(IntegrationCandidateError):
                IntegrationCandidateService().export(source, output)
            self.assertEqual("keep", (output / "keep.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
