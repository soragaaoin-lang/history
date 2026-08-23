from __future__ import annotations

import re
from typing import Any

from chat_history_poc.domain.models import NormalizedEvent


INTERNAL_USER_BLOCKS = (
    "environment_context",
    "recommended_plugins",
    "permissions instructions",
    "skills_instructions",
    "app-context",
    "collaboration_mode",
    "apps_instructions",
    "plugins_instructions",
)


class AnalysisProjectionService:
    """Projects lossless normalized events into decision-analysis input."""

    def project(
        self,
        session_id: str,
        events: list[NormalizedEvent],
        *,
        message_evidence: dict[int, dict[str, Any]] | None = None,
        attachments: list[dict[str, Any]] | None = None,
        projection_version: str = "1",
    ) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        constraints: list[dict[str, Any]] = []
        implementation_events: list[dict[str, Any]] = []
        constraint_contents: set[str] = set()

        for event in events:
            if event.kind == "message":
                for constraint in self._agents_constraints(event):
                    if constraint["content"] not in constraint_contents:
                        constraints.append(constraint)
                        constraint_contents.add(constraint["content"])
                if event.role in {"user", "assistant"}:
                    content = self._strip_agents_blocks(event.content or "")
                    content = self._strip_internal_blocks(content)
                    if content.strip():
                        message = {
                            "id": event.id,
                            "actor": "human" if event.role == "user" else "assistant",
                            "content": content.strip(),
                            "source_line": event.source_line,
                        }
                        if message_evidence is not None:
                            evidence = message_evidence.get(event.source_line)
                            if evidence is None:
                                raise ValueError(f"missing message evidence for source line {event.source_line}")
                            if evidence["actor"] != message["actor"]:
                                raise ValueError(f"actor mismatch for source line {event.source_line}")
                            message.update({
                                "evidence_id": evidence["message_id"],
                                "section_id": evidence.get("section_id"),
                            })
                        messages.append(message)
            elif event.kind in {"file_change", "command"}:
                implementation_events.append({
                    "id": event.id,
                    "kind": event.kind,
                    "source_event_type": event.source_event_type,
                    "source_line": event.source_line,
                    "content": event.content,
                })

        result = {
            "session_id": session_id,
            "projection_version": projection_version,
            "messages": messages,
            "constraints": constraints,
            "implementation_events": implementation_events,
            "projection_report": {
                "normalized_events": len(events),
                "analysis_messages": len(messages),
                "constraints": len(constraints),
                "implementation_events": len(implementation_events),
            },
        }
        if attachments is not None:
            result["attachments"] = attachments
            result["projection_report"]["attachments"] = len(attachments)
        return result

    @staticmethod
    def _strip_internal_blocks(content: str) -> str:
        result = content
        for tag in INTERNAL_USER_BLOCKS:
            result = re.sub(
                rf"<{re.escape(tag)}(?:\s[^>]*)?>.*?</{re.escape(tag)}>",
                "",
                result,
                flags=re.DOTALL | re.IGNORECASE,
            )
        return result

    @staticmethod
    def _agents_constraints(event: NormalizedEvent) -> list[dict[str, Any]]:
        content = event.content or ""
        if "AGENTS.md" not in content:
            return []
        blocks = re.findall(r"<INSTRUCTIONS>\s*(.*?)\s*</INSTRUCTIONS>", content, flags=re.DOTALL | re.IGNORECASE)
        return [{
            "id": f"{event.id}-constraint-{index:03d}",
            "source_message_id": event.id,
            "source": "AGENTS.md",
            "content": block,
            "source_line": event.source_line,
        } for index, block in enumerate(blocks, 1) if block.strip()]

    @staticmethod
    def _strip_agents_blocks(content: str) -> str:
        return re.sub(
            r"(?:^|\n)\s*# AGENTS\.md instructions[^\n]*\n+\s*<INSTRUCTIONS>.*?</INSTRUCTIONS>",
            "",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
