from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


EVENT_KINDS = {"message", "tool", "file_change", "command", "metadata", "unknown", "parse_error"}


@dataclass(frozen=True)
class RawEvent:
    id: str
    session_id: str
    source_line: int
    raw_text: str
    parsed_ok: bool
    event_type: str | None
    timestamp: str | None


@dataclass(frozen=True)
class NormalizedEvent:
    id: str
    session_id: str
    raw_event_id: str
    source_line: int
    source_event_type: str | None
    kind: str
    role: str | None
    timestamp: str | None
    content: str | None

    def __post_init__(self) -> None:
        if self.kind not in EVENT_KINDS:
            raise ValueError(f"Unsupported event kind: {self.kind}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RejectedAlternative:
    alternative: str
    reason: str


@dataclass(frozen=True)
class DecisionCandidate:
    decision_id: str
    title: str
    decision: str
    context: str | None
    alternatives: list[str] = field(default_factory=list)
    rationale: list[str] = field(default_factory=list)
    rejected_alternatives: list[RejectedAlternative] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    revisit_conditions: list[str] = field(default_factory=list)
    evidence_message_ids: list[str] = field(default_factory=list)
    confidence: str = "low"
    missing_information: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

