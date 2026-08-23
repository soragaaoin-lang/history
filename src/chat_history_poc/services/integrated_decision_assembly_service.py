from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from chat_history_poc.domain.errors import IntegrationAdjudicationError
from chat_history_poc.services.integration_adjudication_validation_service import (
    IntegrationAdjudicationValidationService,
)


class IntegratedDecisionAssemblyService:
    """Deterministically applies validated cross-Section relation judgments."""

    VERSION = "integrated-decision-v1"

    def assemble(
        self,
        candidate_bundle: Path,
        adjudication_bundle: Path,
        output_dir: Path,
    ) -> Path:
        if output_dir.exists() and any(output_dir.iterdir()):
            raise IntegrationAdjudicationError(f"output directory is not empty: {output_dir}")
        inventory_doc = self._json(candidate_bundle / "decision_inventory.json")
        clusters_doc = self._json(candidate_bundle / "candidate_clusters.json")
        inventory = inventory_doc.get("decisions")
        if not isinstance(inventory, list):
            raise IntegrationAdjudicationError("decision inventory is invalid")
        by_key = {item["source_decision_key"]: item for item in inventory}
        if len(by_key) != len(inventory):
            raise IntegrationAdjudicationError("decision inventory contains duplicate keys")

        relations: list[dict[str, Any]] = []
        validator = IntegrationAdjudicationValidationService()
        validation_results: list[dict[str, Any]] = []
        for cluster in clusters_doc.get("clusters", []):
            cluster_id = cluster["cluster_id"]
            cluster_dir = adjudication_bundle / "clusters" / cluster_id
            input_path = cluster_dir / "cluster_input.json"
            output_path = cluster_dir / "adjudication.raw.json"
            validation = validator.validate_files(input_path, output_path)
            validation_results.append(validation)
            data = self._json(output_path)
            relations.extend(data["judgments"])
            for key in data["unclassified_decision_keys"]:
                relations.append(
                    {
                        "judgment_id": f"{cluster_id}:unclassified:{key}",
                        "relation": "uncertain",
                        "member_decision_keys": [key],
                        "direction": None,
                        "rationale": ["AI adjudication left this Decision unclassified."],
                        "evidence_refs": by_key[key]["evidence_refs"],
                        "confidence": "low",
                        "missing_information": ["Cross-Section relation was not classified."],
                    }
                )

        dropped: set[str] = set()
        merged_groups: list[list[str]] = []
        status_updates: dict[str, str] = {}
        relation_counts: Counter[str] = Counter()
        relation_by_key: dict[str, list[str]] = {}
        for judgment in relations:
            relation = judgment["relation"]
            keys = judgment["member_decision_keys"]
            relation_counts[relation] += 1
            for key in keys:
                relation_by_key.setdefault(key, []).append(relation)
            if relation == "not_decision":
                dropped.update(keys)
            elif relation == "same_decision":
                merged_groups.append(keys)
            elif relation == "lifecycle_relation":
                direction = judgment["direction"]
                source = direction["from_decision_key"]
                target = direction["to_decision_key"]
                mapping = {
                    "accepts": "accepted",
                    "changes": "superseded",
                    "supersedes": "superseded",
                    "rejects": "rejected",
                    "cancels": "cancelled",
                    "reverts": "reverted",
                }
                status_updates[target] = mapping[direction["relation"]]
                status_updates[source] = "accepted"

        key_to_group: dict[str, tuple[str, ...]] = {}
        for members in merged_groups:
            group = tuple(sorted(set(members)))
            for key in group:
                if key in key_to_group and key_to_group[key] != group:
                    raise IntegrationAdjudicationError(f"overlapping same_decision groups: {key}")
                key_to_group[key] = group

        assembled: list[dict[str, Any]] = []
        consumed: set[str] = set()
        for key in sorted(by_key, key=self._key_order):
            if key in consumed or key in dropped:
                continue
            group = key_to_group.get(key, (key,))
            members = [item for item in group if item not in dropped]
            consumed.update(group)
            if not members:
                continue
            canonical_key = max(members, key=self._key_order)
            record = self._merge([by_key[item] for item in members], canonical_key)
            for member in members:
                if member in status_updates:
                    record["status"] = status_updates[member]
            if len(members) == 1 and canonical_key in status_updates:
                record["status"] = status_updates[canonical_key]
            record["source_decision_keys"] = members
            record["integration_relations"] = sorted(
                {relation for member in members for relation in relation_by_key.get(member, [])}
            )
            record["original_statuses"] = {
                member: by_key[member]["status"] for member in members
            }
            assembled.append(record)

        for index, item in enumerate(assembled, start=1):
            item["decision_id"] = f"ID-{index:03d}"

        before_status = Counter(item["status"] for item in inventory)
        after_status = Counter(item["status"] for item in assembled)
        output_dir.mkdir(parents=True, exist_ok=True)
        decisions_path = output_dir / "decisions.integrated.json"
        summary_path = output_dir / "INTEGRATION_SUMMARY.json"
        self._write(
            decisions_path,
            {
                "integration_version": self.VERSION,
                "decisions": assembled,
            },
        )
        self._write(
            summary_path,
            {
                "integration_version": self.VERSION,
                "input_decision_count": len(inventory),
                "output_decision_count": len(assembled),
                "dropped_not_decision_count": len(dropped),
                "merged_group_count": len(merged_groups),
                "merged_source_decision_count": sum(len(group) for group in merged_groups),
                "status_update_count": len(status_updates),
                "relation_distribution": dict(sorted(relation_counts.items())),
                "status_before": dict(sorted(before_status.items())),
                "status_after": dict(sorted(after_status.items())),
                "cluster_validation": validation_results,
                "source_hashes": {
                    "decision_inventory": self._sha(candidate_bundle / "decision_inventory.json"),
                    "candidate_clusters": self._sha(candidate_bundle / "candidate_clusters.json"),
                    "integrated_decisions": self._sha(decisions_path),
                },
            },
        )
        return output_dir

    def _merge(self, records: list[dict[str, Any]], canonical_key: str) -> dict[str, Any]:
        canonical = next(item for item in records if item["source_decision_key"] == canonical_key)
        result = {
            key: canonical[key]
            for key in (
                "title", "decision", "context", "alternatives", "rationale",
                "rejected_alternatives", "risks", "revisit_conditions", "evidence_refs",
                "confidence", "missing_information", "status",
            )
        }
        result["decision_id"] = canonical["source_decision_id"]
        for field in (
            "alternatives", "rationale", "risks", "revisit_conditions", "missing_information"
        ):
            result[field] = self._unique(
                value for record in records for value in record[field]
            )
        result["evidence_refs"] = self._unique_objects(
            ref for record in records for ref in record["evidence_refs"]
        )
        result["rejected_alternatives"] = self._unique_objects(
            ref for record in records for ref in record["rejected_alternatives"]
        )
        confidence_rank = {"high": 2, "medium": 1, "low": 0}
        result["confidence"] = min(
            (record["confidence"] for record in records), key=confidence_rank.get
        )
        return result

    @staticmethod
    def _unique(values: Any) -> list[Any]:
        seen: set[Any] = set()
        result: list[Any] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result

    @staticmethod
    def _unique_objects(values: Any) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for value in values:
            key = json.dumps(value, ensure_ascii=False, sort_keys=True)
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result

    @staticmethod
    def _key_order(value: str) -> tuple[int, int]:
        section, decision = value.split(":")
        return int(section.removeprefix("SEC-")), int(decision.removeprefix("D-"))

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
