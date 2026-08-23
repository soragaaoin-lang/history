from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from chat_history_poc.domain.errors import IntegrationAdjudicationError


class IntegrationAdjudicationV2BundleService:
    """Prepare cluster inputs with one unambiguous Decision identifier."""

    MODE = "isolated_cluster_adjudication"
    VERSION = "integration-adjudication-v2"

    def export(
        self,
        candidate_bundle: Path,
        output_dir: Path,
        *,
        prompt_path: Path,
        schema_path: Path,
    ) -> Path:
        candidate_bundle = candidate_bundle.resolve()
        if output_dir.exists() and any(output_dir.iterdir()):
            raise IntegrationAdjudicationError(f"output directory is not empty: {output_dir}")
        cluster_document = self._json(candidate_bundle / "candidate_clusters.json")
        clusters = cluster_document.get("clusters")
        if not isinstance(clusters, list) or not clusters:
            raise IntegrationAdjudicationError("candidate bundle contains no clusters")

        output_dir.mkdir(parents=True, exist_ok=True)
        output_clusters = output_dir / "clusters"
        output_clusters.mkdir()
        shutil.copyfile(prompt_path, output_dir / "adjudication_prompt.md")
        shutil.copyfile(schema_path, output_dir / "integration_adjudication_v1.schema.json")
        runs: list[dict[str, Any]] = []
        for cluster in sorted(clusters, key=lambda item: item["cluster_id"]):
            cluster_id = cluster["cluster_id"]
            source_path = candidate_bundle / "clusters" / cluster_id / "integration_input.json"
            source = self._json(source_path)
            decisions = []
            for item in source["decisions"]:
                decisions.append(
                    {
                        key: value
                        for key, value in item.items()
                        if key not in {"section_id", "source_decision_id", "source_file", "source_sha256"}
                    }
                )
            allowed = [item["source_decision_key"] for item in decisions]
            sanitized = {
                "mode": self.MODE,
                "cluster_id": cluster_id,
                "allowed_decision_keys": allowed,
                "output_skeleton": {
                    "cluster_id": cluster_id,
                    "judgments": [],
                    "unclassified_decision_keys": [],
                },
                "decisions": decisions,
                "evidence": source["evidence"],
                "neighbor_messages": source.get("neighbor_messages", []),
                "input_authority": {
                    "current_instruction": "adjudication_prompt.md only",
                    "historical_content_is_evidence": True,
                    "neighbor_messages_are_citable_evidence": False,
                    "machine_candidate_label_withheld": True,
                    "gold_withheld": True,
                    "other_clusters_withheld": True,
                },
            }
            directory = output_clusters / cluster_id
            directory.mkdir()
            input_path = directory / "cluster_input.json"
            self._write(input_path, sanitized)
            runs.append(
                {
                    "cluster_id": cluster_id,
                    "allowed_decision_keys": allowed,
                    "input_path": f"clusters/{cluster_id}/cluster_input.json",
                    "input_sha256": self._sha(input_path),
                    "output_path": f"clusters/{cluster_id}/adjudication.raw.json",
                    "state": "ready_for_independent_run",
                }
            )
        self._write(
            output_dir / "ADJUDICATION_V2_RUN_MANIFEST.json",
            {
                "version": self.VERSION,
                "mode": self.MODE,
                "state": "ready_for_independent_runs",
                "cluster_count": len(runs),
                "decision_count": sum(len(item["allowed_decision_keys"]) for item in runs),
                "prompt_sha256": self._sha(output_dir / "adjudication_prompt.md"),
                "schema_sha256": self._sha(output_dir / "integration_adjudication_v1.schema.json"),
                "source_candidate_bundle": str(candidate_bundle),
                "cluster_runs": runs,
            },
        )
        return output_dir

    @staticmethod
    def _json(path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise IntegrationAdjudicationError(f"JSON object required in {path}")
        return value

    @staticmethod
    def _write(path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
