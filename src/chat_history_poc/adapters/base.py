from typing import Any, Protocol

from chat_history_poc.domain.models import NormalizedEvent, RawEvent


class SessionAdapter(Protocol):
    def can_handle(self, raw: dict[str, Any]) -> bool: ...

    def normalize(self, raw_event: RawEvent, raw: dict[str, Any] | None) -> NormalizedEvent: ...

