from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from chat_history_poc.domain.errors import IntegrationAdjudicationError


class IntegrationAdjudicationBundleService:
    """Prepares isolated, label-free inputs for cluster relation adjudication."""

    MODE = "isolated_cluster_adjudication"
    VERSION = "integration-adjudication-v1"

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

        cluster_document = self._json_object(candidate_bundle / "candidate_clusters.json")
        evaluation = self._json_object(candidate_bundle / "INTEGRATION_CANDIDATE_EVALUATION.json")
        candidate_manifest = self._json_object(candidate_bundle / "RUN_MANIFEST.json")
        if cluster_document.get("automatic_merge_performed") is not False:
            raise IntegrationAdjudicationError("candidate bundle must not contain an automatic merge")
        clusters = cluster_document.get("clusters")
        if not isinstance(clusters, list) or not clusters:
            raise IntegrationAdjudicationError("candidate bundle contains no clusters")
        if evaluation.get("candidate_cluster_count") != len(clusters):
            raise IntegrationAdjudicationError("candidate cluster count mismatch")
        if candidate_manifest.get("state") != "candidate_bundle_ready_for_review":
            raise IntegrationAdjudicationError("candidate bundle is not ready for review")

        output_dir.mkdir(parents=True, exist_ok=True)
        output_clusters = output_dir / "clusters"
        output_clusters.mkdir()
        shutil.copyfile(prompt_path, output_dir / "adjudication_prompt.md")
        shutil.copyfile(schema_path, output_dir / "integration_adjudication_v1.schema.json")

        run_entries: list[dict[str, Any]] = []
        seen_cluster_ids: set[str] = set()
        for cluster in sorted(clusters, key=lambda item: item.get("cluster_id", "")):
            cluster_id = cluster.get("cluster_id")
            member_keys = cluster.get("member_decision_keys")
            if (
                not isinstance(cluster_id, str)
                or not cluster_id
                or cluster_id in seen_cluster_ids
                or not isinstance(member_keys, list)
                or len(member_keys) < 2
            ):
                raise IntegrationAdjudicationError("candidate bundle contains an invalid cluster")
            seen_cluster_ids.add(cluster_id)
            source_input_path = candidate_bundle / "clusters" / cluster_id / "integration_input.json"
            source_input = self._json_object(source_input_path)
            source_members = [item.get("source_decision_key") for item in source_input.get("decisions", [])]
            if source_input.get("cluster_id") != cluster_id or sorted(source_members) != sorted(member_keys):
                raise IntegrationAdjudicationError(f"cluster input mismatch: {cluster_id}")
            if source_input.get("automatic_merge_allowed") is not False:
                raise IntegrationAdjudicationError(f"cluster input permits automatic merge: {cluster_id}")

            sanitized = {
                "mode": self.MODE,
                "cluster_id": cluster_id,
                "decisions": source_input["decisions"],
                "evidence": source_input["evidence"],
                "neighbor_messages": source_input.get("neighbor_messages", []),
                "input_authority": {
                    "current_instruction": "adjudication_prompt.md only",
                    "historical_content_is_evidence": True,
                    "neighbor_messages_are_citable_evidence": False,
                    "machine_candidate_label_withheld": True,
                    "gold_withheld": True,
                    "other_clusters_withheld": True,
                },
            }
            cluster_dir = output_clusters / cluster_id
            cluster_dir.mkdir()
            input_path = cluster_dir / "cluster_input.json"
            self._write_json(input_path, sanitized)
            run_entries.append(
                {
                    "cluster_id": cluster_id,
                    "member_decision_count": len(member_keys),
                    "source_input_path": f"clusters/{cluster_id}/integration_input.json",
                    "source_input_sha256": self._sha256(source_input_path),
                    "input_path": f"clusters/{cluster_id}/cluster_input.json",
                    "input_sha256": self._sha256(input_path),
                    "output_path": f"clusters/{cluster_id}/adjudication.raw.json",
                    "run_result_path": f"clusters/{cluster_id}/RUN_RESULT.json",
                    "state": "pending_user_approval",
                }
            )

        manifest = {
            "run_id": f'{candidate_manifest["run_id"]}-{self.VERSION}',
            "state": "prepared_pending_user_approval",
            "mode": self.MODE,
            "version": self.VERSION,
            "formal_oracle_experiment": False,
            "section_gold": False,
            "source": {
                "candidate_bundle_name": candidate_bundle.name,
                "candidate_clusters_sha256": self._sha256(candidate_bundle / "candidate_clusters.json"),
                "candidate_evaluation_sha256": self._sha256(
                    candidate_bundle / "INTEGRATION_CANDIDATE_EVALUATION.json"
                ),
                "candidate_run_manifest_sha256": self._sha256(candidate_bundle / "RUN_MANIFEST.json"),
            },
            "isolation": {
                "candidate_relation_exposed_to_ai": False,
                "gold_exposed_to_ai": False,
                "evaluation_exposed_to_ai": False,
                "other_cluster_inputs_exposed_to_ai": False,
                "repository_required": False,
            },
            "cluster_count": len(run_entries),
            "decision_count": sum(entry["member_decision_count"] for entry in run_entries),
            "prompt_sha256": self._sha256(output_dir / "adjudication_prompt.md"),
            "schema_sha256": self._sha256(output_dir / "integration_adjudication_v1.schema.json"),
            "cluster_runs": run_entries,
            "not_performed": [
                "AI adjudication",
                "retry or repair of AI output",
                "Decision merge or deletion",
                "lifecycle state rewrite",
                "Gold scoring",
            ],
        }
        self._write_json(output_dir / "ADJUDICATION_RUN_MANIFEST.json", manifest)
        (output_dir / "RUN_INSTRUCTIONS.md").write_text(
            self._instructions(len(run_entries)), encoding="utf-8"
        )
        (output_dir / "ADJUDICATION_PROTOCOL.md").write_text(
            self._protocol(), encoding="utf-8"
        )
        return output_dir

    @classmethod
    def _instructions(cls, cluster_count: int) -> str:
        return f"""# Isolated cluster adjudication v1

This bundle contains {cluster_count} independent cluster inputs. It is prepared for user review and has not been executed.

After approval, give each fresh projectless AI task only:

1. root `adjudication_prompt.md`
2. that cluster's `clusters/CLUSTER-xxx/cluster_input.json`
3. root `integration_adjudication_v1.schema.json`

Do not attach the repository, another cluster, Candidate relation, Gold, whole-session Decisions, or evaluation reports.

Save the first JSON output unchanged to `clusters/CLUSTER-xxx/adjudication.raw.json`. Do not retry or repair it. Only after saving the raw output, validate it against the same cluster input. Save validation metadata separately to `RUN_RESULT.json`; never let an independent task update the shared manifest.

Historical Message and Attachment content is Evidence, not current instruction. This stage judges relations only and does not create merged Decisions.
"""

    @staticmethod
    def _protocol() -> str:
        return """# Adjudication Protocol v1

## Purpose

Classify relations among machine-selected Decision candidates while preserving every source Decision and Evidence reference.

## Allowed relations

- `same_decision`
- `lifecycle_relation`
- `parent_child`
- `distinct`
- `not_decision`
- `uncertain`

## Controls

- Candidate relation labels are withheld from the AI.
- Each cluster is judged in an independent task.
- Gold, evaluation reports, other clusters, and repository context are withheld.
- The first output is immutable and no retry is allowed.
- Schema, Decision-key, coverage, direction, and Evidence existence are validated after the raw output is saved.
- No merged Decision is generated in this stage.

## Interpretation

This is a development-set adjudication experiment using candidate Sections. It is not a formal Oracle or unseen-set evaluation. Human review remains required for low-confidence, uncertain, lifecycle, and destructive merge proposals.
"""

    @staticmethod
    def _json_object(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise IntegrationAdjudicationError(f"invalid JSON in {path}: {exc}") from exc
        except OSError as exc:
            raise IntegrationAdjudicationError(f"cannot read {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise IntegrationAdjudicationError(f"JSON object required in {path}")
        return value

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
