import json

from chat_history_poc.adapters.codex_jsonl import CodexJsonlAdapter
from chat_history_poc.domain.models import RawEvent


def normalize(obj, line=1):
    raw = RawEvent("s-raw-1", "s", line, json.dumps(obj), True, obj.get("type"), obj.get("timestamp"))
    return CodexJsonlAdapter().normalize(raw, obj)


def test_message_role_and_japanese_content():
    event = normalize({"type": "response_item", "timestamp": "t", "payload": {
        "type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "日本語です"}]}})
    assert event.kind == "message"
    assert event.role == "assistant"
    assert event.content == "日本語です"
    assert event.id == "s-msg-000001"


def test_unobserved_subtype_is_unknown():
    event = normalize({"type": "event_msg", "payload": {"type": "future_subtype"}})
    assert event.kind == "unknown"

