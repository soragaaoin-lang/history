from __future__ import annotations

from typing import Any

from chat_history_poc.domain.models import NormalizedEvent, RawEvent


class CodexJsonlAdapter:
    """Adapter for the Codex event shapes observed in the supplied samples."""

    TOP_LEVEL_TYPES = {"session_meta", "event_msg", "response_item", "world_state", "turn_context", "compacted"}
    EVENT_METADATA = {
        "task_started", "task_complete", "thread_settings_applied", "token_count",
        "agent_reasoning", "context_compacted", "turn_aborted", "user_message", "agent_message",
    }
    EVENT_TOOL = {"web_search_end", "mcp_tool_call_end"}
    EVENT_FILE_CHANGE = {"patch_apply_end"}

    def can_handle(self, raw: dict[str, Any]) -> bool:
        return raw.get("type") in self.TOP_LEVEL_TYPES and isinstance(raw.get("payload"), dict)

    def normalize(self, raw_event: RawEvent, raw: dict[str, Any] | None) -> NormalizedEvent:
        if raw is None:
            return self._event(raw_event, "parse_error", None, None)
        top_type = raw.get("type")
        payload = raw.get("payload")
        if not isinstance(payload, dict):
            return self._event(raw_event, "unknown", None, None)
        if top_type in {"session_meta", "world_state", "turn_context", "compacted"}:
            return self._event(raw_event, "metadata", None, self._metadata_summary(top_type, payload))
        if top_type == "event_msg":
            return self._normalize_event_msg(raw_event, payload)
        if top_type == "response_item":
            return self._normalize_response_item(raw_event, payload)
        return self._event(raw_event, "unknown", None, None)

    def _normalize_event_msg(self, raw_event: RawEvent, payload: dict[str, Any]) -> NormalizedEvent:
        subtype = payload.get("type")
        content = self._first_text(payload, "message", "text", "reason", "info")
        if subtype in self.EVENT_METADATA:
            return self._event(raw_event, "metadata", None, content)
        if subtype in self.EVENT_TOOL:
            return self._event(raw_event, "tool", None, content)
        if subtype in self.EVENT_FILE_CHANGE:
            return self._event(raw_event, "file_change", None, content)
        return self._event(raw_event, "unknown", None, content)

    def _normalize_response_item(self, raw_event: RawEvent, payload: dict[str, Any]) -> NormalizedEvent:
        subtype = payload.get("type")
        if subtype == "message":
            role = payload.get("role") if isinstance(payload.get("role"), str) else None
            content = self._content_text(payload.get("content"))
            return self._event(raw_event, "message", role, content)
        if subtype == "reasoning":
            return self._event(raw_event, "metadata", None, self._content_text(payload.get("summary")))
        if subtype in {"custom_tool_call", "custom_tool_call_output", "function_call", "function_call_output"}:
            name = payload.get("name")
            kind = "tool"
            if name == "shell_command":
                kind = "command"
            elif name == "apply_patch":
                kind = "file_change"
            content = self._first_text(payload, "name", "arguments", "input", "output")
            return self._event(raw_event, kind, None, content)
        return self._event(raw_event, "unknown", None, None)

    @staticmethod
    def _content_text(content: Any) -> str | None:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return None
        texts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            for key in ("text", "input_text", "output_text"):
                value = item.get(key)
                if isinstance(value, str):
                    texts.append(value)
                    break
        return "\n\n".join(texts) if texts else None

    @staticmethod
    def _first_text(payload: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str):
                return value
        return None

    @staticmethod
    def _metadata_summary(top_type: str, payload: dict[str, Any]) -> str:
        subtype = payload.get("type")
        return f"{top_type}:{subtype}" if subtype else top_type

    @staticmethod
    def _event(raw: RawEvent, kind: str, role: str | None, content: str | None) -> NormalizedEvent:
        prefix = "msg" if kind == "message" else "evt"
        return NormalizedEvent(
            id=f"{raw.session_id}-{prefix}-{raw.source_line:06d}", session_id=raw.session_id,
            raw_event_id=raw.id, source_line=raw.source_line, source_event_type=raw.event_type,
            kind=kind, role=role, timestamp=raw.timestamp, content=content,
        )

