from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from chat_history_poc.domain.errors import IntegrationAdjudicationError


class IntegrationAdjudicationValidationService:
    """Validates a raw relation judgment against one isolated cluster input."""

    RELATIONS = {
        "same_decision",
        "lifecycle_relation",
        "parent_child",
        "distinct",
        "not_decision",
        "uncertain",
    }
    LIFECYCLE_DIRECTIONS = {
        "accepts",
        "changes",
        "supersedes",
        "rejects",
        "cancels",
        "reverts",
    }
    CONFIDENCE = {"high", "medium", "low"}
    EVIDENCE_TYPES = {"message", "attachment"}
    ROOT_KEYS = {"cluster_id", "judgments", "unclassified_decision_keys"}
    JUDGMENT_KEYS = {
        "judgment_id",
        "relation",
        "member_decision_keys",
        "direction",
        "rationale",
        "evidence_refs",
        "confidence",
        "missing_information",
    }
    DIRECTION_KEYS = {"from_decision_key", "relation", "to_decision_key"}
    EVIDENCE_KEYS = {"evidence_type", "evidence_id"}

    def validate_files(self, cluster_input_path: Path, adjudication_path: Path) -> dict[str, Any]:
        cluster_input = self._json_object(cluster_input_path)
        adjudication = self._json_object(adjudication_path)
        return self.validate(cluster_input, adjudication)

    def validate(
        self,
        cluster_input: dict[str, Any],
        adjudication: dict[str, Any],
    ) -> dict[str, Any]:
        cluster_id = self._required_string(cluster_input.get("cluster_id"), "input cluster_id")
        if re.fullmatch(r"CLUSTER-[0-9a-f]{12}", cluster_id) is None:
            self._fail("input cluster_id has an invalid format")
        if cluster_input.get("mode") != "isolated_cluster_adjudication":
            self._fail("input mode must be isolated_cluster_adjudication")

        decisions = cluster_input.get("decisions")
        evidence = cluster_input.get("evidence")
        if not isinstance(decisions, list) or not decisions:
            self._fail("input decisions must be a non-empty array")
        if not isinstance(evidence, list):
            self._fail("input evidence must be an array")
        decision_values = self._unique_strings(
            [item.get("source_decision_key") if isinstance(item, dict) else None for item in decisions],
            "input Decision keys",
        )
        if any(re.fullmatch(r"SEC-[0-9]{3}:D-[0-9]{3}", key) is None for key in decision_values):
            self._fail("input Decision key has an invalid format")
        decision_keys = set(decision_values)
        evidence_keys: set[tuple[str, str]] = set()
        for index, item in enumerate(evidence):
            if not isinstance(item, dict):
                self._fail(f"input evidence[{index}] must be an object")
            evidence_type = self._required_string(item.get("evidence_type"), f"input evidence[{index}].evidence_type")
            if evidence_type not in self.EVIDENCE_TYPES:
                self._fail(f"input evidence[{index}].evidence_type is invalid")
            evidence_id = self._required_string(item.get("evidence_id"), f"input evidence[{index}].evidence_id")
            key = (evidence_type, evidence_id)
            if key in evidence_keys:
                self._fail(f"duplicate input Evidence reference: {evidence_type}:{evidence_id}")
            evidence_keys.add(key)

        if set(adjudication) != self.ROOT_KEYS:
            self._fail(f"adjudication root keys must be exactly {sorted(self.ROOT_KEYS)}")
        if adjudication.get("cluster_id") != cluster_id:
            self._fail("adjudication cluster_id does not match the input")
        judgments = adjudication.get("judgments")
        if not isinstance(judgments, list) or not judgments:
            self._fail("judgments must be a non-empty array")

        judgment_ids: set[str] = set()
        classified_keys: set[str] = set()
        relation_counts: Counter[str] = Counter()
        evidence_reference_count = 0
        for index, judgment in enumerate(judgments, start=1):
            if not isinstance(judgment, dict) or set(judgment) != self.JUDGMENT_KEYS:
                self._fail(f"judgment {index} keys must be exactly {sorted(self.JUDGMENT_KEYS)}")
            expected_id = f"J-{index:03d}"
            judgment_id = self._required_string(judgment.get("judgment_id"), f"judgment {index}.judgment_id")
            if judgment_id != expected_id:
                self._fail(f"judgment IDs must be sequential; expected {expected_id}")
            if judgment_id in judgment_ids:
                self._fail(f"duplicate judgment_id: {judgment_id}")
            judgment_ids.add(judgment_id)

            relation = judgment.get("relation")
            if relation not in self.RELATIONS:
                self._fail(f"invalid relation in {judgment_id}: {relation}")
            relation_counts[relation] += 1
            members = self._unique_strings(
                judgment.get("member_decision_keys"),
                f"{judgment_id}.member_decision_keys",
            )
            unknown_members = set(members) - decision_keys
            if unknown_members:
                self._fail(f"unknown Decision keys in {judgment_id}: {sorted(unknown_members)}")
            classified_keys.update(members)
            self._validate_relation_shape(judgment_id, relation, members, judgment.get("direction"))
            self._non_empty_strings(judgment.get("rationale"), f"{judgment_id}.rationale")
            self._string_array(judgment.get("missing_information"), f"{judgment_id}.missing_information")
            if judgment.get("confidence") not in self.CONFIDENCE:
                self._fail(f"invalid confidence in {judgment_id}")

            refs = judgment.get("evidence_refs")
            if not isinstance(refs, list) or not refs:
                self._fail(f"{judgment_id}.evidence_refs must be a non-empty array")
            seen_refs: set[tuple[str, str]] = set()
            for ref_index, ref in enumerate(refs):
                if not isinstance(ref, dict) or set(ref) != self.EVIDENCE_KEYS:
                    self._fail(f"{judgment_id}.evidence_refs[{ref_index}] has invalid keys")
                key = (
                    self._required_string(ref.get("evidence_type"), "evidence_type"),
                    self._required_string(ref.get("evidence_id"), "evidence_id"),
                )
                if key[0] not in self.EVIDENCE_TYPES:
                    self._fail(f"invalid Evidence type in {judgment_id}: {key[0]}")
                if key in seen_refs:
                    self._fail(f"duplicate Evidence reference in {judgment_id}: {key[0]}:{key[1]}")
                if key not in evidence_keys:
                    self._fail(f"unknown Evidence reference in {judgment_id}: {key[0]}:{key[1]}")
                seen_refs.add(key)
            evidence_reference_count += len(refs)

        unclassified = self._string_array(
            adjudication.get("unclassified_decision_keys"),
            "unclassified_decision_keys",
            unique=True,
        )
        unknown_unclassified = set(unclassified) - decision_keys
        if unknown_unclassified:
            self._fail(f"unknown unclassified Decision keys: {sorted(unknown_unclassified)}")
        overlap = classified_keys.intersection(unclassified)
        if overlap:
            self._fail(f"Decision keys cannot be both classified and unclassified: {sorted(overlap)}")
        covered = classified_keys.union(unclassified)
        missing = decision_keys - covered
        if missing:
            self._fail(f"Decision coverage is incomplete: {sorted(missing)}")

        return {
            "status": "valid",
            "cluster_id": cluster_id,
            "decision_count": len(decision_keys),
            "classified_decision_count": len(classified_keys),
            "unclassified_decision_count": len(unclassified),
            "judgment_count": len(judgments),
            "relation_counts": dict(sorted(relation_counts.items())),
            "evidence_reference_count": evidence_reference_count,
            "coverage_complete": True,
        }

    def _validate_relation_shape(
        self,
        judgment_id: str,
        relation: str,
        members: list[str],
        direction: Any,
    ) -> None:
        if relation in {"lifecycle_relation", "parent_child"}:
            if len(members) != 2:
                self._fail(f"{judgment_id} {relation} requires exactly two Decision keys")
            if not isinstance(direction, dict) or set(direction) != self.DIRECTION_KEYS:
                self._fail(f"{judgment_id} {relation} requires a direction object")
            from_key = direction.get("from_decision_key")
            to_key = direction.get("to_decision_key")
            if from_key not in members or to_key not in members or from_key == to_key:
                self._fail(f"{judgment_id} direction endpoints must be distinct members")
            allowed = self.LIFECYCLE_DIRECTIONS if relation == "lifecycle_relation" else {"parent_of"}
            if direction.get("relation") not in allowed:
                self._fail(f"{judgment_id} has an invalid direction relation")
            return
        if direction is not None:
            self._fail(f"{judgment_id} direction must be null for {relation}")
        minimum = 2 if relation in {"same_decision", "distinct"} else 1
        if len(members) < minimum:
            self._fail(f"{judgment_id} {relation} requires at least {minimum} Decision key(s)")

    def _unique_strings(self, value: Any, label: str) -> list[str]:
        values = self._non_empty_strings(value, label)
        if len(values) != len(set(values)):
            self._fail(f"{label} must contain unique values")
        return values

    def _non_empty_strings(self, value: Any, label: str) -> list[str]:
        values = self._string_array(value, label)
        if not values:
            self._fail(f"{label} must be non-empty")
        if any(not item for item in values):
            self._fail(f"{label} must not contain empty strings")
        return values

    def _string_array(self, value: Any, label: str, *, unique: bool = False) -> list[str]:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            self._fail(f"{label} must be an array of strings")
        if unique and len(value) != len(set(value)):
            self._fail(f"{label} must contain unique values")
        return value

    def _required_string(self, value: Any, label: str) -> str:
        if not isinstance(value, str) or not value:
            self._fail(f"{label} must be a non-empty string")
        return value

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
    def _fail(message: str) -> None:
        raise IntegrationAdjudicationError(message)
