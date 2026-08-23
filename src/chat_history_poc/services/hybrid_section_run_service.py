from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chat_history_poc.services.decision_v3_validation_service import (
    DecisionV3ValidationService,
)


class HybridSectionRunService:
    """Freeze and validate already-written first-run Section outputs."""

    def finalize(self, bundle_dir: Path) -> Path:
        bundle_dir = bundle_dir.resolve()
        manifest_path = bundle_dir / "HYBRID_RUN_MANIFEST.json"
        manifest = self._json_object(manifest_path)
        results: list[dict[str, Any]] = []
        status_counts: Counter[str] = Counter()
        validator = DecisionV3ValidationService()

        for run in manifest.get("section_runs", []):
            section_id = run["section_id"]
            section_dir = bundle_dir / "sections" / section_id
            analysis_path = section_dir / "analysis_session.json"
            decisions_path = section_dir / "decisions.raw.json"
            first_hash_path = section_dir / "FIRST_RUN_HASH.json"
            result_path = section_dir / "RUN_RESULT.json"
            result: dict[str, Any] = {
                "section_id": section_id,
                "state": "missing",
                "decision_count": 0,
                "status_distribution": {},
                "message_evidence_ref_count": 0,
                "attachment_evidence_ref_count": 0,
                "output_sha256": None,
                "validated_output_path": None,
                "validated_output_sha256": None,
                "rejected_decision_indices": [],
                "repaired_decision_indices": [],
                "first_run_hash_matches": False,
                "validation_error": None,
            }
            try:
                if not decisions_path.is_file() or not first_hash_path.is_file():
                    raise ValueError("first-run output or hash record is missing")
                actual_hash = self._sha256(decisions_path)
                hash_record = self._json_object(first_hash_path)
                recorded_hash = hash_record.get("output_sha256", hash_record.get("sha256"))
                result["output_sha256"] = actual_hash
                result["first_run_hash_matches"] = actual_hash == recorded_hash
                if not result["first_run_hash_matches"]:
                    raise ValueError(
                        f"first-run hash mismatch: {actual_hash} != {recorded_hash}"
                    )
                raw = self._json_object(decisions_path)
                decisions = raw.get("decisions")
                if not isinstance(decisions, list):
                    raise ValueError("root decisions array is missing")
                valid_decisions, rejected, repaired = self._select_valid_decisions(
                    validator,
                    self._json_object(analysis_path),
                    decisions,
                )
                validated_path = section_dir / "decisions.validated.json"
                self._write_json(validated_path, {"decisions": valid_decisions})
                validated = validator.validate_files(analysis_path, validated_path)
                distribution = Counter(item["status"] for item in valid_decisions)
                status_counts.update(distribution)
                result.update(
                    {
                        "state": "valid" if not rejected else "partially_valid",
                        "decision_count": validated["decisions"],
                        "status_distribution": dict(sorted(distribution.items())),
                        "message_evidence_ref_count": validated[
                            "message_evidence_references"
                        ],
                        "attachment_evidence_ref_count": validated[
                            "attachment_evidence_references"
                        ],
                        "validated_output_path": "decisions.validated.json",
                        "validated_output_sha256": self._sha256(validated_path),
                        "rejected_decision_indices": rejected,
                        "repaired_decision_indices": repaired,
                    }
                )
            except Exception as exc:  # Preserve the raw first output and report failure.
                result["state"] = "invalid" if decisions_path.is_file() else "missing"
                result["validation_error"] = str(exc)
            self._write_json(result_path, result)
            results.append(result)

        usable = [item for item in results if item["state"] in {"valid", "partially_valid"}]
        summary = {
            "run_id": manifest.get("run_id"),
            "state": "complete" if len(usable) == len(results) else "incomplete",
            "finalized_at_utc": datetime.now(timezone.utc).isoformat(),
            "section_count": len(results),
            "valid_section_count": sum(item["state"] == "valid" for item in results),
            "partially_valid_section_count": sum(
                item["state"] == "partially_valid" for item in results
            ),
            "invalid_section_count": sum(item["state"] == "invalid" for item in results),
            "missing_section_count": sum(item["state"] == "missing" for item in results),
            "decision_count": sum(item["decision_count"] for item in usable),
            "repaired_decision_count": sum(
                len(item["repaired_decision_indices"]) for item in usable
            ),
            "status_distribution": dict(sorted(status_counts.items())),
            "message_evidence_ref_count": sum(
                item["message_evidence_ref_count"] for item in usable
            ),
            "attachment_evidence_ref_count": sum(
                item["attachment_evidence_ref_count"] for item in usable
            ),
            "all_first_run_hashes_match": all(
                item["first_run_hash_matches"] for item in usable
            ) and len(usable) == len(results),
            "sections": results,
        }
        output_path = bundle_dir / "HYBRID_EXECUTION_SUMMARY.json"
        self._write_json(output_path, summary)
        return output_path

    @staticmethod
    def _select_valid_decisions(
        validator: DecisionV3ValidationService,
        analysis: dict[str, Any],
        decisions: list[Any],
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        message_ids = {item.get("evidence_id") for item in analysis.get("messages", [])}
        attachment_ids = {
            item.get("attachment_id") for item in analysis.get("attachments", [])
        }
        valid: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        repaired: list[dict[str, Any]] = []
        for index, decision in enumerate(decisions):
            try:
                normalized, repaired_fields = HybridSectionRunService._repair_shape(
                    decision
                )
                refs = validator.validate({"decisions": [normalized]})
                for ref in refs:
                    allowed = (
                        message_ids
                        if ref["evidence_type"] == "message"
                        else attachment_ids
                    )
                    if ref["evidence_id"] not in allowed:
                        raise ValueError(
                            f'unknown {ref["evidence_type"]} Evidence: {ref["evidence_id"]}'
                        )
                valid.append(normalized)
                if repaired_fields:
                    repaired.append(
                        {
                            "index": index,
                            "fields": repaired_fields,
                            "repair": "wrapped_scalar_string_as_single_item_array",
                        }
                    )
            except Exception as exc:
                rejected.append({"index": index, "error": str(exc)})
        return valid, rejected, repaired

    @staticmethod
    def _repair_shape(decision: Any) -> tuple[Any, list[str]]:
        """Apply only lossless, schema-shape repairs and record every changed field.

        A model occasionally returns a single string for a field whose schema requires
        an array of strings. Wrapping that exact scalar preserves its text and meaning.
        No Evidence, status, identifier, or semantic content is invented or removed.
        """
        if not isinstance(decision, dict):
            return decision, []
        normalized = dict(decision)
        repaired_fields: list[str] = []
        for field in (
            "alternatives",
            "rationale",
            "risks",
            "revisit_conditions",
            "missing_information",
        ):
            value = normalized.get(field)
            if isinstance(value, str):
                normalized[field] = [value]
                repaired_fields.append(field)
        return normalized, repaired_fields

    @staticmethod
    def _json_object(path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict):
            raise ValueError(f"JSON object required in {path}")
        return value

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
