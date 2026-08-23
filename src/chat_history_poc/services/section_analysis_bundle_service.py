from __future__ import annotations

import bisect
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from chat_history_poc.domain.errors import SectionBundleError


class SectionAnalysisBundleService:
    """Splits Projection v3 into candidate-Section scoped AI inputs."""

    MODE = "candidate_section_assisted"

    def export(
        self,
        analysis_session_path: Path,
        section_index_path: Path,
        output_dir: Path,
        *,
        prompt_path: Path,
        schema_path: Path,
    ) -> Path:
        analysis = self._json_object(analysis_session_path)
        section_document = self._json_object(section_index_path)
        sections = self._validate_inputs(analysis, section_document)

        if output_dir.exists() and any(output_dir.iterdir()):
            raise SectionBundleError(f"output directory is not empty: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        sections_dir = output_dir / "sections"
        sections_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(prompt_path, output_dir / "analysis_prompt.md")
        shutil.copyfile(schema_path, output_dir / "decision_analysis_v3.schema.json")

        messages_by_section: dict[str, list[dict[str, Any]]] = {section_id: [] for section_id in sections}
        ordered_messages = sorted(analysis["messages"], key=lambda item: item["source_line"])
        for message in ordered_messages:
            section_id = message["section_id"]
            messages_by_section[section_id].append(message)

        attachments_by_section: dict[str, list[dict[str, Any]]] = {section_id: [] for section_id in sections}
        for attachment in analysis["attachments"]:
            for section_id in attachment["section_ids"]:
                attachments_by_section[section_id].append(attachment)

        events_by_section, unassigned_events = self._implementation_events_by_section(
            ordered_messages, analysis.get("implementation_events", [])
        )

        run_entries: list[dict[str, Any]] = []
        for section_id in sections:
            section_dir = sections_dir / section_id
            section_dir.mkdir(parents=True, exist_ok=True)
            section_projection = {
                "session_id": analysis["session_id"],
                "projection_version": "3",
                "section_scope": {
                    "mode": self.MODE,
                    "section_id": section_id,
                    "section_gold": False,
                },
                "messages": messages_by_section[section_id],
                "attachments": attachments_by_section[section_id],
                "constraints": analysis.get("constraints", []),
                "implementation_events": events_by_section.get(section_id, []),
                "projection_report": {
                    "analysis_messages": len(messages_by_section[section_id]),
                    "attachments": len(attachments_by_section[section_id]),
                    "constraints": len(analysis.get("constraints", [])),
                    "implementation_events": len(events_by_section.get(section_id, [])),
                },
            }
            input_path = section_dir / "analysis_session.json"
            input_path.write_text(
                json.dumps(section_projection, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            run_entries.append({
                "section_id": section_id,
                "input_path": f"sections/{section_id}/analysis_session.json",
                "input_sha256": self._sha256(input_path),
                "output_path": f"sections/{section_id}/decisions.raw.json",
                "state": "pending",
            })

        manifest = {
            "run_id": f'{analysis["session_id"]}-candidate-section-assisted-v1',
            "state": "ready_for_section_runs",
            "experiment": {
                "independent_variable": "candidate Section scoped input",
                "held_constant": [
                    "Projection v3 Message and Attachment evidence",
                    "Decision extraction criteria",
                    "Decision Schema v3",
                    "no decision_type prompt",
                    "no cross-Section deduplication",
                    "no lifecycle integration",
                ],
                "section_gold": False,
                "formal_oracle_experiment": False,
            },
            "source": {
                "analysis_session_path": str(analysis_session_path.resolve()),
                "analysis_session_sha256": self._sha256(analysis_session_path),
                "section_index_path": str(section_index_path.resolve()),
                "section_index_sha256": self._sha256(section_index_path),
                "section_index_status": section_document.get("status"),
            },
            "section_count": len(sections),
            "message_count": len(analysis["messages"]),
            "attachment_count": len(analysis["attachments"]),
            "unassigned_implementation_events": unassigned_events,
            "prompt_sha256": self._sha256(output_dir / "analysis_prompt.md"),
            "schema_sha256": self._sha256(output_dir / "decision_analysis_v3.schema.json"),
            "section_runs": run_entries,
        }
        (output_dir / "SECTION_RUN_MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (output_dir / "RUN_INSTRUCTIONS.md").write_text(
            self._instructions(analysis["session_id"], len(sections)), encoding="utf-8"
        )
        return output_dir

    def _validate_inputs(
        self, analysis: dict[str, Any], section_document: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        if analysis.get("projection_version") != "3":
            raise SectionBundleError("Projection v3 analysis_session is required")
        if not isinstance(analysis.get("messages"), list) or not isinstance(analysis.get("attachments"), list):
            raise SectionBundleError("Projection v3 Message and Attachment arrays are required")
        raw_sections = section_document.get("sections")
        if not isinstance(raw_sections, list) or not raw_sections:
            raise SectionBundleError("Section index requires a non-empty sections array")

        sections: dict[str, dict[str, Any]] = {}
        section_message_ids: dict[str, set[str]] = {}
        for section in raw_sections:
            if not isinstance(section, dict) or not isinstance(section.get("section_id"), str):
                raise SectionBundleError("Section index contains an invalid Section")
            section_id = section["section_id"]
            if section_id in sections:
                raise SectionBundleError(f"duplicate Section id: {section_id}")
            source = section.get("source")
            if not isinstance(source, dict) or not isinstance(source.get("message_ids"), list):
                raise SectionBundleError(f"Section {section_id} has no source Message ids")
            sections[section_id] = section
            section_message_ids[section_id] = set(source["message_ids"])

        message_ids: set[str] = set()
        for message in analysis["messages"]:
            if not isinstance(message, dict):
                raise SectionBundleError("analysis_session contains an invalid Message")
            evidence_id = message.get("evidence_id")
            section_id = message.get("section_id")
            if not isinstance(evidence_id, str) or not evidence_id or evidence_id in message_ids:
                raise SectionBundleError("analysis_session contains a missing or duplicate Message Evidence id")
            if section_id not in sections:
                raise SectionBundleError(f"Message {evidence_id} has an unknown Section")
            if evidence_id not in section_message_ids[section_id]:
                raise SectionBundleError(f"Message {evidence_id} is absent from Section index {section_id}")
            if not isinstance(message.get("source_line"), int):
                raise SectionBundleError(f"Message {evidence_id} has no source line")
            message_ids.add(evidence_id)

        attachment_ids: set[str] = set()
        for attachment in analysis["attachments"]:
            if not isinstance(attachment, dict):
                raise SectionBundleError("analysis_session contains an invalid Attachment")
            attachment_id = attachment.get("attachment_id")
            section_ids = attachment.get("section_ids")
            parents = attachment.get("parent_message_ids")
            if not isinstance(attachment_id, str) or not attachment_id or attachment_id in attachment_ids:
                raise SectionBundleError("analysis_session contains a missing or duplicate Attachment id")
            if not isinstance(section_ids, list) or not section_ids or any(value not in sections for value in section_ids):
                raise SectionBundleError(f"Attachment {attachment_id} has an unknown Section")
            if not isinstance(parents, list) or not parents or any(value not in message_ids for value in parents):
                raise SectionBundleError(f"Attachment {attachment_id} has an unknown parent Message")
            for section_id in section_ids:
                expected_ids = set(sections[section_id].get("source", {}).get("attachment_ids", []))
                if attachment_id not in expected_ids:
                    raise SectionBundleError(f"Attachment {attachment_id} is absent from Section index {section_id}")
            attachment_ids.add(attachment_id)
        return sections

    @staticmethod
    def _implementation_events_by_section(
        ordered_messages: list[dict[str, Any]], implementation_events: list[dict[str, Any]]
    ) -> tuple[dict[str, list[dict[str, Any]]], int]:
        lines = [message["source_line"] for message in ordered_messages]
        result: dict[str, list[dict[str, Any]]] = {}
        unassigned = 0
        for event in sorted(implementation_events, key=lambda item: item.get("source_line", -1)):
            source_line = event.get("source_line")
            if not isinstance(source_line, int):
                unassigned += 1
                continue
            index = bisect.bisect_right(lines, source_line) - 1
            if index < 0:
                unassigned += 1
                continue
            section_id = ordered_messages[index]["section_id"]
            result.setdefault(section_id, []).append(event)
        return result, unassigned

    @staticmethod
    def _json_object(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SectionBundleError(f"invalid JSON in {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise SectionBundleError(f"JSON object required in {path}")
        return value

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @classmethod
    def _instructions(cls, session_id: str, section_count: int) -> str:
        return f"""# Candidate Section-assisted Decision extraction

This bundle contains {section_count} independent Section inputs for session `{session_id}`.

The Section index is a development-set candidate pending human adjudication. This is not a Gold or formal oracle experiment.

For each `sections/SEC-xxx/` directory, give a fresh AI task only these three inputs:

1. root `analysis_prompt.md`
2. that Section's `analysis_session.json`
3. root `decision_analysis_v3.schema.json`

Save the first JSON output unchanged as `sections/SEC-xxx/decisions.raw.json`. Do not retry or repair an invalid first output. Validate it against that same Section input with `validate-decisions-v3`.

Do not give Section titles, types, Gold, whole-session Decisions, evaluation reports, or another Section's input to the extraction task. Empty `decisions` is a valid output when no design or implementation Decision exists.

This stage does not deduplicate Decisions across Sections and does not integrate lifecycle state across Sections.
"""
