from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from chat_history_poc.domain.errors import LifecycleAdjudicationError


class LifecycleAdjudicationService:
    """Validate isolated lifecycle judgments and apply only their status updates."""

    VERSION = "lifecycle-adjudication-v1"
    STATUSES = {
        "proposed",
        "accepted",
        "rejected",
        "superseded",
        "cancelled",
        "reverted",
    }
    CONFIDENCE = {"high", "medium", "low"}
    EVIDENCE_TYPES = {"message", "attachment"}
    RESULT_KEYS = {
        "decision_id",
        "final_status",
        "rationale",
        "evidence_refs",
        "confidence",
        "missing_information",
    }

    def apply(
        self,
        integrated_decisions_path: Path,
        review_bundle: Path,
        output_dir: Path,
    ) -> Path:
        integrated_decisions_path = integrated_decisions_path.resolve()
        review_bundle = review_bundle.resolve()
        output_dir = output_dir.resolve()
        if output_dir.exists() and any(output_dir.iterdir()):
            raise LifecycleAdjudicationError(
                f"output directory is not empty: {output_dir}"
            )
        source = self._json(integrated_decisions_path)
        decisions = source.get("decisions")
        if not isinstance(decisions, list):
            raise LifecycleAdjudicationError("integrated decisions array is missing")
        by_id = {item.get("decision_id"): item for item in decisions}
        if len(by_id) != len(decisions) or None in by_id:
            raise LifecycleAdjudicationError("Decision IDs must be unique and non-null")
        manifest = self._json(review_bundle / "RUN_MANIFEST.json")
        results: dict[str, dict[str, Any]] = {}
        validations: list[dict[str, Any]] = []
        for group in manifest.get("groups", []):
            group_id = group["group_id"]
            directory = review_bundle / "groups" / group_id
            input_data = self._json(directory / "lifecycle_input.json")
            output_data = self._json(directory / "lifecycle.raw.json")
            validation = self._validate_group(input_data, output_data)
            validations.append(validation)
            for result in output_data["results"]:
                decision_id = result["decision_id"]
                if decision_id in results:
                    raise LifecycleAdjudicationError(
                        f"duplicate lifecycle result: {decision_id}"
                    )
                results[decision_id] = result

        expected = {
            item["decision_id"] for item in decisions if item.get("status") == "proposed"
        }
        if set(results) != expected:
            raise LifecycleAdjudicationError(
                f"lifecycle coverage mismatch; missing={sorted(expected - set(results))}, "
                f"extra={sorted(set(results) - expected)}"
            )

        updated: list[dict[str, Any]] = []
        changes: list[dict[str, Any]] = []
        for item in decisions:
            record = dict(item)
            decision_id = record["decision_id"]
            result = results.get(decision_id)
            if result is not None:
                old_status = record["status"]
                new_status = result["final_status"]
                record["status"] = new_status
                record["lifecycle_adjudication"] = {
                    "previous_status": old_status,
                    "final_status": new_status,
                    "rationale": result["rationale"],
                    "evidence_refs": result["evidence_refs"],
                    "confidence": result["confidence"],
                    "missing_information": result["missing_information"],
                }
                if old_status != new_status:
                    changes.append(
                        {
                            "decision_id": decision_id,
                            "from_status": old_status,
                            "to_status": new_status,
                            "evidence_refs": result["evidence_refs"],
                        }
                    )
            updated.append(record)

        output_dir.mkdir(parents=True, exist_ok=True)
        decisions_path = output_dir / "decisions.lifecycle.json"
        summary_path = output_dir / "LIFECYCLE_SUMMARY.json"
        self._write(
            decisions_path,
            {"lifecycle_version": self.VERSION, "decisions": updated},
        )
        self._write(
            summary_path,
            {
                "lifecycle_version": self.VERSION,
                "input_decision_count": len(decisions),
                "reviewed_proposed_decision_count": len(results),
                "status_change_count": len(changes),
                "status_before": dict(sorted(Counter(item["status"] for item in decisions).items())),
                "status_after": dict(sorted(Counter(item["status"] for item in updated).items())),
                "changes": changes,
                "group_validations": validations,
                "source_hashes": {
                    "integrated_decisions": self._sha(integrated_decisions_path),
                    "review_manifest": self._sha(review_bundle / "RUN_MANIFEST.json"),
                    "lifecycle_decisions": self._sha(decisions_path),
                },
            },
        )
        return output_dir

    def _validate_group(
        self, input_data: dict[str, Any], output_data: dict[str, Any]
    ) -> dict[str, Any]:
        group_id = input_data.get("group_id")
        if output_data.get("group_id") != group_id:
            raise LifecycleAdjudicationError(f"group_id mismatch: {group_id}")
        if set(output_data) != {"group_id", "results"}:
            raise LifecycleAdjudicationError(
                f"lifecycle output root keys are invalid: {group_id}"
            )
        allowed_ids = [item.get("decision_id") for item in input_data.get("decisions", [])]
        evidence = {
            ("message", item.get("evidence_id"))
            for item in input_data.get("messages", [])
        } | {
            ("attachment", item.get("attachment_id"))
            for item in input_data.get("attachments", [])
        }
        output_results = output_data.get("results")
        if not isinstance(output_results, list):
            raise LifecycleAdjudicationError(f"results must be an array: {group_id}")
        actual_ids: list[str] = []
        evidence_count = 0
        for index, result in enumerate(output_results):
            if not isinstance(result, dict) or set(result) != self.RESULT_KEYS:
                raise LifecycleAdjudicationError(
                    f"result[{index}] keys are invalid: {group_id}"
                )
            decision_id = result.get("decision_id")
            if decision_id not in allowed_ids:
                raise LifecycleAdjudicationError(
                    f"unknown lifecycle Decision ID: {decision_id}"
                )
            actual_ids.append(decision_id)
            if result.get("final_status") not in self.STATUSES:
                raise LifecycleAdjudicationError(
                    f"invalid lifecycle status: {decision_id}"
                )
            self._strings(result.get("rationale"), f"{decision_id}.rationale", non_empty=True)
            self._strings(result.get("missing_information"), f"{decision_id}.missing_information")
            if result.get("confidence") not in self.CONFIDENCE:
                raise LifecycleAdjudicationError(
                    f"invalid lifecycle confidence: {decision_id}"
                )
            refs = result.get("evidence_refs")
            if not isinstance(refs, list) or not refs:
                raise LifecycleAdjudicationError(
                    f"Evidence is required for lifecycle result: {decision_id}"
                )
            seen: set[tuple[str, str]] = set()
            for ref in refs:
                if not isinstance(ref, dict) or set(ref) != {"evidence_type", "evidence_id"}:
                    raise LifecycleAdjudicationError(
                        f"invalid lifecycle Evidence shape: {decision_id}"
                    )
                key = (ref.get("evidence_type"), ref.get("evidence_id"))
                if key[0] not in self.EVIDENCE_TYPES or key not in evidence:
                    raise LifecycleAdjudicationError(
                        f"unknown lifecycle Evidence: {key[0]}:{key[1]}"
                    )
                if key in seen:
                    raise LifecycleAdjudicationError(
                        f"duplicate lifecycle Evidence: {key[0]}:{key[1]}"
                    )
                seen.add(key)
            evidence_count += len(refs)
        if actual_ids != allowed_ids:
            raise LifecycleAdjudicationError(
                f"lifecycle result order/coverage mismatch: {group_id}"
            )
        return {
            "group_id": group_id,
            "status": "valid",
            "decision_count": len(actual_ids),
            "evidence_reference_count": evidence_count,
        }

    @staticmethod
    def _strings(value: Any, label: str, *, non_empty: bool = False) -> list[str]:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise LifecycleAdjudicationError(f"{label} must be an array of strings")
        if non_empty and (not value or any(not item for item in value)):
            raise LifecycleAdjudicationError(f"{label} must be non-empty")
        return value

    @staticmethod
    def _json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LifecycleAdjudicationError(f"cannot read JSON {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise LifecycleAdjudicationError(f"JSON object required in {path}")
        return value

    @staticmethod
    def _write(path: Path, value: Any) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
