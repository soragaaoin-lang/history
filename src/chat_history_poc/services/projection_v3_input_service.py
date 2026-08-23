from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chat_history_poc.domain.errors import ProjectionInputError


class ProjectionV3InputService:
    """Loads already-normalized Message/Attachment evidence for Projection v3."""

    MESSAGE_REQUIRED = {"raw_line", "message_id", "actor"}
    ATTACHMENT_REQUIRED = {
        "attachment_id", "parent_message_ids", "section_ids", "content", "sha256", "authority_note"
    }

    def load(self, messages_path: Path, attachments_path: Path) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
        messages = self._jsonl(messages_path)
        attachments = self._jsonl(attachments_path)

        by_source_line: dict[int, dict[str, Any]] = {}
        message_ids: set[str] = set()
        for index, message in enumerate(messages, 1):
            if not self.MESSAGE_REQUIRED.issubset(message):
                raise ProjectionInputError(f"normalized message line {index} is missing required fields")
            source_line = message["raw_line"]
            message_id = message["message_id"]
            actor = message["actor"]
            if not isinstance(source_line, int) or not isinstance(message_id, str) or actor not in {"human", "assistant", "context"}:
                raise ProjectionInputError(f"normalized message line {index} has invalid fields")
            if source_line in by_source_line or message_id in message_ids:
                raise ProjectionInputError(f"duplicate normalized message at line {index}")
            by_source_line[source_line] = message
            message_ids.add(message_id)

        projected_attachments: list[dict[str, Any]] = []
        attachment_ids: set[str] = set()
        for index, attachment in enumerate(attachments, 1):
            if not self.ATTACHMENT_REQUIRED.issubset(attachment):
                raise ProjectionInputError(f"normalized attachment line {index} is missing required fields")
            attachment_id = attachment["attachment_id"]
            parents = attachment["parent_message_ids"]
            sections = attachment["section_ids"]
            if not isinstance(attachment_id, str) or not attachment_id or attachment_id in attachment_ids:
                raise ProjectionInputError(f"normalized attachment line {index} has invalid or duplicate id")
            if not isinstance(parents, list) or not parents or any(parent not in message_ids for parent in parents):
                raise ProjectionInputError(f"normalized attachment line {index} has unknown parent Message")
            if not isinstance(sections, list) or any(not isinstance(value, str) for value in sections):
                raise ProjectionInputError(f"normalized attachment line {index} has invalid Section ids")
            for field in ("content", "sha256", "authority_note"):
                if not isinstance(attachment[field], str) or not attachment[field]:
                    raise ProjectionInputError(f"normalized attachment line {index}.{field} is invalid")
            attachment_ids.add(attachment_id)
            projected_attachments.append({
                "attachment_id": attachment_id,
                "parent_message_ids": parents,
                "section_ids": sections,
                "content": attachment["content"],
                "sha256": attachment["sha256"],
                "authority_note": attachment["authority_note"],
            })
        return by_source_line, projected_attachments

    @staticmethod
    def _jsonl(path: Path) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProjectionInputError(f"invalid JSONL in {path} line {index}: {exc}") from exc
            if not isinstance(value, dict):
                raise ProjectionInputError(f"JSONL object required in {path} line {index}")
            result.append(value)
        return result
