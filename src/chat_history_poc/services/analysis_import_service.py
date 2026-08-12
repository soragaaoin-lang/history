from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chat_history_poc.domain.errors import DecisionValidationError, EvidenceNotFoundError, SessionNotFoundError
from chat_history_poc.domain.models import DecisionCandidate, RejectedAlternative
from chat_history_poc.repositories.sqlite_repository import SQLiteRepository


class AnalysisImportService:
    REQUIRED = {"decision_id", "title", "decision", "context", "alternatives", "rationale",
                "rejected_alternatives", "risks", "revisit_conditions", "evidence_message_ids",
                "confidence", "missing_information", "status"}
    LIST_FIELDS = {"alternatives", "rationale", "rejected_alternatives", "risks", "revisit_conditions",
                   "evidence_message_ids", "missing_information"}

    def __init__(self, repository: SQLiteRepository):
        self.repository = repository

    def import_file(self, session_id: str, path: Path) -> int:
        if not self.repository.session_exists(session_id):
            raise SessionNotFoundError(session_id)
        raw_text = path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise DecisionValidationError(f"invalid JSON: {exc}") from exc
        decisions = self.validate(data)
        known = self.repository.message_ids(session_id)
        missing = sorted({mid for d in decisions for mid in d.evidence_message_ids if mid not in known})
        if missing:
            raise EvidenceNotFoundError(", ".join(missing))
        return self.repository.save_decisions(session_id, decisions, raw_text)

    @classmethod
    def validate(cls, data: Any) -> list[DecisionCandidate]:
        if not isinstance(data, dict) or set(data) != {"decisions"} or not isinstance(data["decisions"], list):
            raise DecisionValidationError("root must contain only a decisions array")
        result: list[DecisionCandidate] = []
        seen: set[str] = set()
        for index, item in enumerate(data["decisions"]):
            if not isinstance(item, dict) or set(item) != cls.REQUIRED:
                raise DecisionValidationError(f"decision[{index}] has missing or additional fields")
            if any(not isinstance(item[field], list) for field in cls.LIST_FIELDS):
                raise DecisionValidationError(f"decision[{index}] contains a non-list collection")
            for field in cls.LIST_FIELDS - {"rejected_alternatives"}:
                if any(not isinstance(value, str) for value in item[field]):
                    raise DecisionValidationError(f"decision[{index}].{field} must contain strings")
            if not all(isinstance(item.get(field), str) and item[field].strip() for field in ("decision_id", "title", "decision")):
                raise DecisionValidationError(f"decision[{index}] requires non-empty id, title, and decision")
            if item["context"] is not None and not isinstance(item["context"], str):
                raise DecisionValidationError(f"decision[{index}].context must be string or null")
            if item["confidence"] not in {"high", "medium", "low"}:
                raise DecisionValidationError(f"decision[{index}].confidence is invalid")
            if item["status"] not in {"proposed", "accepted", "rejected", "superseded", "reverted", "unknown"}:
                raise DecisionValidationError(f"decision[{index}].status is invalid")
            if not item["evidence_message_ids"]:
                raise DecisionValidationError(f"decision[{index}] has no evidence")
            if item["decision_id"] in seen:
                raise DecisionValidationError(f"duplicate decision id: {item['decision_id']}")
            seen.add(item["decision_id"])
            rejected: list[RejectedAlternative] = []
            for value in item["rejected_alternatives"]:
                if not isinstance(value, dict) or set(value) != {"alternative", "reason"} or not all(isinstance(value[k], str) for k in value):
                    raise DecisionValidationError(f"decision[{index}].rejected_alternatives is invalid")
                rejected.append(RejectedAlternative(**value))
            result.append(DecisionCandidate(
                decision_id=item["decision_id"], title=item["title"], decision=item["decision"], context=item["context"],
                alternatives=item["alternatives"], rationale=item["rationale"], rejected_alternatives=rejected,
                risks=item["risks"], revisit_conditions=item["revisit_conditions"], evidence_message_ids=item["evidence_message_ids"],
                confidence=item["confidence"], missing_information=item["missing_information"], status=item["status"]))
        return result
