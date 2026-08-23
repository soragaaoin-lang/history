from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from chat_history_poc.domain.errors import IntegrationAdjudicationError
from chat_history_poc.services.integration_adjudication_bundle_service import (
    IntegrationAdjudicationBundleService,
)
from chat_history_poc.services.integration_adjudication_validation_service import (
    IntegrationAdjudicationValidationService,
)


class IntegrationAdjudicationTest(unittest.TestCase):
    CLUSTER_ID = "CLUSTER-123456789abc"

    def test_bundle_is_label_free_and_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = self._candidate_bundle(root)
            prompt = root / "prompt.md"
            schema = root / "schema.json"
            prompt.write_text("judge relations\n", encoding="utf-8")
            schema.write_text('{"type":"object"}\n', encoding="utf-8")
            source_hashes = self._tree_hashes(candidate)

            first = root / "first"
            second = root / "second"
            service = IntegrationAdjudicationBundleService()
            service.export(candidate, first, prompt_path=prompt, schema_path=schema)
            service.export(candidate, second, prompt_path=prompt, schema_path=schema)

            self.assertEqual(self._tree_hashes(first), self._tree_hashes(second))
            self.assertEqual(source_hashes, self._tree_hashes(candidate))
            cluster_input = json.loads(
                (first / "clusters" / self.CLUSTER_ID / "cluster_input.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("candidate_relation", cluster_input)
            self.assertNotIn("candidate_relation", json.dumps(cluster_input))
            self.assertEqual(cluster_input["mode"], "isolated_cluster_adjudication")
            manifest = json.loads((first / "ADJUDICATION_RUN_MANIFEST.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["state"], "prepared_pending_user_approval")
            self.assertFalse(manifest["isolation"]["candidate_relation_exposed_to_ai"])
            self.assertIn("AI adjudication", manifest["not_performed"])

    def test_validator_accepts_complete_lifecycle_judgment(self) -> None:
        result = IntegrationAdjudicationValidationService().validate(
            self._cluster_input(),
            self._valid_adjudication(),
        )
        self.assertEqual(result["status"], "valid")
        self.assertTrue(result["coverage_complete"])
        self.assertEqual(result["relation_counts"], {"lifecycle_relation": 1})

    def test_validator_rejects_unknown_evidence(self) -> None:
        adjudication = self._valid_adjudication()
        adjudication["judgments"][0]["evidence_refs"][0]["evidence_id"] = "unknown"
        with self.assertRaisesRegex(IntegrationAdjudicationError, "unknown Evidence"):
            IntegrationAdjudicationValidationService().validate(self._cluster_input(), adjudication)

    def test_validator_rejects_invalid_direction(self) -> None:
        adjudication = self._valid_adjudication()
        adjudication["judgments"][0]["direction"]["relation"] = "parent_of"
        with self.assertRaisesRegex(IntegrationAdjudicationError, "invalid direction"):
            IntegrationAdjudicationValidationService().validate(self._cluster_input(), adjudication)

    def test_validator_rejects_incomplete_coverage(self) -> None:
        adjudication = self._valid_adjudication()
        adjudication["judgments"][0]["member_decision_keys"] = ["SEC-001:D-001"]
        adjudication["judgments"][0]["relation"] = "not_decision"
        adjudication["judgments"][0]["direction"] = None
        with self.assertRaisesRegex(IntegrationAdjudicationError, "coverage is incomplete"):
            IntegrationAdjudicationValidationService().validate(self._cluster_input(), adjudication)

    def _candidate_bundle(self, root: Path) -> Path:
        candidate = root / "candidate"
        cluster_dir = candidate / "clusters" / self.CLUSTER_ID
        cluster_dir.mkdir(parents=True)
        self._write_json(
            candidate / "candidate_clusters.json",
            {
                "automatic_merge_performed": False,
                "clusters": [
                    {
                        "cluster_id": self.CLUSTER_ID,
                        "member_decision_keys": ["SEC-001:D-001", "SEC-002:D-001"],
                        "candidate_relation": "possible_lifecycle_relation",
                    }
                ],
            },
        )
        self._write_json(
            candidate / "INTEGRATION_CANDIDATE_EVALUATION.json",
            {"candidate_cluster_count": 1},
        )
        self._write_json(
            candidate / "RUN_MANIFEST.json",
            {"run_id": "fixture", "state": "candidate_bundle_ready_for_review"},
        )
        source_input = self._cluster_input()
        source_input.update(
            {
                "algorithm_version": "integration-candidate-v1",
                "automatic_merge_allowed": False,
                "candidate_relation": "possible_lifecycle_relation",
                "mode": "candidate_cluster_review_input",
            }
        )
        self._write_json(cluster_dir / "integration_input.json", source_input)
        return candidate

    def _cluster_input(self) -> dict:
        return {
            "mode": "isolated_cluster_adjudication",
            "cluster_id": self.CLUSTER_ID,
            "decisions": [
                {"source_decision_key": "SEC-001:D-001", "title": "old"},
                {"source_decision_key": "SEC-002:D-001", "title": "new"},
            ],
            "evidence": [
                {"evidence_type": "message", "evidence_id": "msg-1", "content": "change it"},
                {"evidence_type": "message", "evidence_id": "msg-2", "content": "approved"},
            ],
            "neighbor_messages": [],
        }

    def _valid_adjudication(self) -> dict:
        return {
            "cluster_id": self.CLUSTER_ID,
            "judgments": [
                {
                    "judgment_id": "J-001",
                    "relation": "lifecycle_relation",
                    "member_decision_keys": ["SEC-001:D-001", "SEC-002:D-001"],
                    "direction": {
                        "from_decision_key": "SEC-002:D-001",
                        "relation": "supersedes",
                        "to_decision_key": "SEC-001:D-001",
                    },
                    "rationale": ["The later instruction replaces the earlier one."],
                    "evidence_refs": [
                        {"evidence_type": "message", "evidence_id": "msg-1"},
                        {"evidence_type": "message", "evidence_id": "msg-2"},
                    ],
                    "confidence": "high",
                    "missing_information": [],
                }
            ],
            "unclassified_decision_keys": [],
        }

    @staticmethod
    def _write_json(path: Path, value: object) -> None:
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def _tree_hashes(root: Path) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }


if __name__ == "__main__":
    unittest.main()
