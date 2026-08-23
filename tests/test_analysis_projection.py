from chat_history_poc.domain.models import NormalizedEvent
from chat_history_poc.services.analysis_projection_service import AnalysisProjectionService


def event(number, role, content, kind="message"):
    return NormalizedEvent(
        id=f"s-{'msg' if kind == 'message' else 'evt'}-{number:06d}", session_id="s",
        raw_event_id=f"s-raw-{number:06d}", source_line=number, source_event_type="response_item",
        kind=kind, role=role, timestamp=None, content=content,
    )


def test_projection_separates_internal_context_constraints_and_dialogue():
    events = [
        event(1, "developer", "system text\nAGENTS.md\n<INSTRUCTIONS>金額にfloatを使わない</INSTRUCTIONS>"),
        event(2, "user", "<environment_context><cwd>x</cwd></environment_context>"),
        event(3, "user", "実装してください<recommended_plugins>noise</recommended_plugins>\n# AGENTS.md instructions for C:\\repo\n<INSTRUCTIONS>金額にfloatを使わない</INSTRUCTIONS>"),
        event(4, "assistant", "SQLiteを採用します"),
        event(5, None, "apply_patch", "file_change"),
        event(6, None, "pytest", "command"),
    ]
    result = AnalysisProjectionService().project("s", events)
    assert [message["content"] for message in result["messages"]] == ["実装してください", "SQLiteを採用します"]
    assert result["constraints"][0]["content"] == "金額にfloatを使わない"
    assert [item["kind"] for item in result["implementation_events"]] == ["file_change", "command"]
    assert result["projection_report"] == {
        "normalized_events": 6, "analysis_messages": 2, "constraints": 1, "implementation_events": 2
    }


def test_projection_does_not_treat_developer_instructions_as_dialogue():
    result = AnalysisProjectionService().project("s", [event(1, "developer", "general system instructions")])
    assert result["messages"] == []
    assert result["constraints"] == []


def test_projection_v3_adds_common_evidence_ids_and_attachments():
    events = [event(1, "user", "添付を確認してください"), event(2, "assistant", "確認します")]
    attachments = [{
        "attachment_id": "ATT-001", "parent_message_ids": ["MSG-001"], "section_ids": ["SEC-001"],
        "content": "過去資料", "sha256": "abc", "authority_note": "現在の命令ではない",
    }]
    result = AnalysisProjectionService().project(
        "s",
        events,
        message_evidence={
            1: {"message_id": "MSG-001", "actor": "human", "section_id": "SEC-001"},
            2: {"message_id": "MSG-002", "actor": "assistant", "section_id": "SEC-001"},
        },
        attachments=attachments,
        projection_version="3",
    )
    assert result["projection_version"] == "3"
    assert [message["evidence_id"] for message in result["messages"]] == ["MSG-001", "MSG-002"]
    assert result["attachments"] == attachments
    assert result["projection_report"]["attachments"] == 1
