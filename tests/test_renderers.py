from chat_history_poc.domain.models import DecisionCandidate, NormalizedEvent
from chat_history_poc.renderers.markdown_renderer import render_conversation, render_decisions


def test_conversation_markdown():
    message = NormalizedEvent("session-msg-000002", "session", "raw", 2, "response_item", "message", "user", None, "こんにちは")
    rendered = render_conversation([message])
    assert "### session-msg-000002" in rendered
    assert "**User**" in rendered
    assert "Source JSONL line: 2" in rendered


def test_decision_markdown_contains_evidence_link():
    decision = DecisionCandidate("D-001", "保存形式", "SQLiteを採用", None,
        evidence_message_ids=["session-msg-000003"], confidence="high")
    rendered = render_decisions([decision])
    assert "## D-001 保存形式" in rendered
    assert "[session-msg-000003](conversation.md#session-msg-000003)" in rendered

