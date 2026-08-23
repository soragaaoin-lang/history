from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chat_history_poc.domain.errors import DecisionValidationError, EvidenceNotFoundError


class DecisionV3ValidationService:
    REQUIRED = {
        "decision_id", "title", "decision", "context", "alternatives", "rationale",
        "rejected_alternatives", "risks", "revisit_conditions", "evidence_refs",
        "confidence", "missing_information", "status",
    }
    STRING_LIST_FIELDS = {"alternatives", "rationale", "risks", "revisit_conditions", "missing_information"}
    STATUSES = {"proposed", "accepted", "rejected", "superseded", "reverted", "cancelled", "unknown"}

    def validate_files(self, analysis_session_path: Path, decisions_path: Path) -> dict[str, Any]:
        analysis = self._json(analysis_session_path)
        decisions = self._json(decisions_path)
        if analysis.get("projection_version") != "3" or not isinstance(analysis.get("attachments"), list):
            raise DecisionValidationError("Projection v3 analysis_session with attachments is required")

        message_ids = {item.get("evidence_id") for item in analysis.get("messages", [])}
        attachment_ids = {item.get("attachment_id") for item in analysis["attachments"]}
        if None in message_ids or None in attachment_ids:
            raise DecisionValidationError("analysis_session contains Evidence without an id")

        refs = self.validate(decisions)
        missing = sorted(
            f"{ref['evidence_type']}:{ref['evidence_id']}"
            for ref in refs
            if ref["evidence_id"] not in (message_ids if ref["evidence_type"] == "message" else attachment_ids)
        )
        if missing:
            raise EvidenceNotFoundError(", ".join(missing))
        return {
            "status": "valid",
            "decisions": len(decisions["decisions"]),
            "evidence_references": len(refs),
            "message_evidence_references": sum(ref["evidence_type"] == "message" for ref in refs),
            "attachment_evidence_references": sum(ref["evidence_type"] == "attachment" for ref in refs),
        }

    @classmethod
    def validate(cls, data: Any) -> list[dict[str, str]]:
        if not isinstance(data, dict) or set(data) != {"decisions"} or not isinstance(data["decisions"], list):
            raise DecisionValidationError("root must contain only a decisions array")
        refs: list[dict[str, str]] = []
        seen: set[str] = set()
        for index, item in enumerate(data["decisions"]):
            if not isinstance(item, dict) or set(item) != cls.REQUIRED:
                raise DecisionValidationError(f"decision[{index}] has missing or additional fields")
            for field in cls.STRING_LIST_FIELDS:
                if not isinstance(item[field], list) or any(not isinstance(value, str) for value in item[field]):
                    raise DecisionValidationError(f"decision[{index}].{field} must contain strings")
            if not all(isinstance(item.get(field), str) and item[field].strip() for field in ("decision_id", "title", "decision")):
                raise DecisionValidationError(f"decision[{index}] requires non-empty id, title, and decision")
            if item["decision_id"] in seen:
                raise DecisionValidationError(f"duplicate decision id: {item['decision_id']}")
            seen.add(item["decision_id"])
            if item["context"] is not None and not isinstance(item["context"], str):
                raise DecisionValidationError(f"decision[{index}].context must be string or null")
            if item["confidence"] not in {"high", "medium", "low"} or item["status"] not in cls.STATUSES:
                raise DecisionValidationError(f"decision[{index}] has invalid confidence or status")
            rejected = item["rejected_alternatives"]
            if not isinstance(rejected, list) or any(
                not isinstance(value, dict)
                or set(value) != {"alternative", "reason"}
                or any(not isinstance(value[key], str) for key in value)
                for value in rejected
            ):
                raise DecisionValidationError(f"decision[{index}].rejected_alternatives is invalid")
            evidence = item["evidence_refs"]
            if not isinstance(evidence, list) or not evidence:
                raise DecisionValidationError(f"decision[{index}] has no evidence")
            for ref in evidence:
                if (
                    not isinstance(ref, dict)
                    or set(ref) != {"evidence_type", "evidence_id"}
                    or ref.get("evidence_type") not in {"message", "attachment"}
                    or not isinstance(ref.get("evidence_id"), str)
                    or not ref["evidence_id"]
                ):
                    raise DecisionValidationError(f"decision[{index}].evidence_refs is invalid")
                refs.append(ref)
        return refs

    @staticmethod
    def _json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DecisionValidationError(f"invalid JSON in {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise DecisionValidationError(f"JSON object required in {path}")
        return value
