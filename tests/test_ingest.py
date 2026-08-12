from chat_history_poc.services.ingest_service import IngestService


def test_ingest_preserves_every_line_and_classifies_loss(repository, fixture_path):
    session_id, report, duplicate = IngestService(repository).ingest(fixture_path)
    assert not duplicate
    assert report == {
        "total_lines": 8,
        "recognized_events": 5,
        "unknown_events": 1,
        "parse_errors": 2,
        "silently_dropped": 0,
    }
    assert report["total_lines"] == report["recognized_events"] + report["unknown_events"] + report["parse_errors"]
    events = repository.events(session_id)
    assert len(events) == 8
    assert {event.kind for event in events} >= {"message", "metadata", "command", "file_change", "unknown", "parse_error"}
    assert any(event.content == "保存形式はJSONでいい？" for event in events)


def test_same_file_is_idempotent(repository, fixture_path):
    service = IngestService(repository)
    first_id, _, first_duplicate = service.ingest(fixture_path)
    second_id, _, second_duplicate = service.ingest(fixture_path)
    assert first_id == second_id
    assert not first_duplicate
    assert second_duplicate
    assert repository.counts(first_id)["total"] == 8
