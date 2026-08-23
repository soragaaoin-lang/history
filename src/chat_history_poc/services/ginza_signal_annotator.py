from __future__ import annotations

import copy
import re
from collections import Counter
from typing import Any, Iterable

from chat_history_poc.domain.errors import SignalAnnotationError


class GinzaSignalAnnotator:
    """Adds heuristic Japanese-language signals without deciding lifecycle state."""

    ANNOTATION_VERSION = "ginza-signal-v1"
    SIGNAL_TYPES = (
        "request_candidate",
        "acceptance_candidate",
        "rejection_candidate",
        "reason_candidate",
        "uncertainty_candidate",
        "alternative_candidate",
    )
    CANDIDATE_NOTE = (
        "Heuristic candidate only. It is neither Decision evidence nor a final lifecycle/status label."
    )
    ACTORS = {"human", "assistant"}

    _PHRASE_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
        (
            "request_candidate",
            "phrase-request-v1",
            re.compile(
                r"(?:して\s*(?:ください|下さい|ほしい|欲しい)|"
                r"(?:実装|追加|作成|変更|修正|確認|対応)して|"
                r"お願い(?:します|したい|できる)|依頼(?:します|したい))"
            ),
        ),
        (
            "acceptance_candidate",
            "phrase-acceptance-v1",
            re.compile(
                r"(?:(?:それ|これ|その案|この案)?で\s*(?:進め|いこう|行こう)|"
                r"で\s*(?:お願い(?:します)?|いい|良い)|採用(?:する|します)?|"
                r"承認(?:する|します)?|その方針で)"
            ),
        ),
        (
            "rejection_candidate",
            "phrase-rejection-v1",
            re.compile(
                r"(?:やめ(?:る|よう)|止め(?:る|よう)|中止(?:する)?|停止(?:する)?|"
                r"見送(?:る|ります)|却下(?:する)?|廃止(?:する)?|"
                r"採用しない|使わない|不要(?:です|とする)?)"
            ),
        ),
        (
            "uncertainty_candidate",
            "phrase-uncertainty-v1",
            re.compile(
                r"(?:まだ\s*決め|保留|未定|検討中|かもしれない|かも(?:しれ)?|"
                r"必要になったら|再検討|判断できない|分からない|わからない)"
            ),
        ),
        (
            "alternative_candidate",
            "phrase-alternative-v1",
            re.compile(
                r"(?:ではなく|じゃなく(?:て)?|代わりに|または|もしくは|"
                r"どちら(?:に|が|を|で|\?|？)|比較(?:する|して|した))"
            ),
        ),
        (
            "reason_candidate",
            "phrase-reason-v1",
            re.compile(r"(?:ので|ため(?:に|、|,|\s)|から(?:、|,|\s)|理由(?:は|で|として))"),
        ),
    )

    _MATCHER_RULES: dict[str, list[list[dict[str, Any]]]] = {
        "request_candidate": [
            [{"LEMMA": {"IN": ["頼む", "願う", "依頼"]}}],
        ],
        "acceptance_candidate": [
            [{"LEMMA": {"IN": ["採用", "承認", "決定", "進める"]}}],
        ],
        "rejection_candidate": [
            [{"LEMMA": {"IN": ["止める", "やめる", "中止", "停止", "見送る", "却下", "廃止"]}}],
        ],
        "uncertainty_candidate": [
            [{"LEMMA": {"IN": ["保留", "未定", "再検討", "迷う"]}}],
        ],
        "alternative_candidate": [
            [{"LEMMA": {"IN": ["代わり", "比較", "選択"]}}],
        ],
        "reason_candidate": [
            [{"LEMMA": {"IN": ["理由"]}}],
        ],
    }

    _DECISION_LEMMAS = [
        "する",
        "変える",
        "変更",
        "採用",
        "決定",
        "進める",
        "止める",
        "やめる",
        "中止",
        "廃止",
    ]

    def __init__(self, model_name: str = "ja_ginza", *, nlp: Any | None = None) -> None:
        self.model_name = model_name
        self._nlp = nlp
        self._matcher: Any | None = None
        self._dependency_matcher: Any | None = None
        self._matcher_signal_types: dict[int, str] = {}

    def annotate_projection(self, projection: dict[str, Any]) -> dict[str, Any]:
        if projection.get("projection_version") != "3":
            raise SignalAnnotationError("Projection v3 analysis_session is required")
        messages = projection.get("messages")
        if not isinstance(messages, list):
            raise SignalAnnotationError("analysis_session.messages must be an array")

        self._ensure_runtime()
        result = copy.deepcopy(projection)
        result_messages = result["messages"]
        eligible: list[tuple[int, str]] = []
        for index, message in enumerate(result_messages):
            if not isinstance(message, dict):
                raise SignalAnnotationError(f"invalid Message at index {index}")
            content = message.get("content")
            if not isinstance(content, str):
                raise SignalAnnotationError(f"Message at index {index} has no text content")
            if message.get("actor") in self.ACTORS and content.strip():
                eligible.append((index, content))

        docs = self._nlp.pipe((text for _, text in eligible), batch_size=16)
        for (index, content), doc in zip(eligible, docs, strict=True):
            signals = self._signals(content, doc)
            if signals:
                result_messages[index]["signals"] = signals

        self._add_conversation_context(result_messages)
        counts = Counter(
            signal["type"]
            for message in result_messages
            for signal in message.get("signals", [])
        )
        result["signal_annotation"] = {
            "annotation_version": self.ANNOTATION_VERSION,
            "model": self.model_name,
            "candidate_only": True,
            "candidate_note": self.CANDIDATE_NOTE,
            "annotated_sources": ["messages"],
            "excluded_sources": ["attachments", "constraints", "implementation_events"],
            "signal_types": list(self.SIGNAL_TYPES),
            "messages_examined": len(eligible),
            "messages_with_signals": sum(bool(item.get("signals")) for item in result_messages),
            "signal_count": sum(counts.values()),
            "signal_counts": {signal_type: counts[signal_type] for signal_type in self.SIGNAL_TYPES},
        }
        return result

    def _ensure_runtime(self) -> None:
        try:
            import spacy
            from spacy.matcher import DependencyMatcher, Matcher
        except ImportError as exc:
            raise SignalAnnotationError(
                'GiNZA signal dependencies are missing. Install with: pip install -e ".[signals]"'
            ) from exc

        if self._nlp is None:
            try:
                self._nlp = spacy.load(self.model_name)
            except OSError as exc:
                raise SignalAnnotationError(
                    f"spaCy model is not available: {self.model_name}"
                ) from exc
        self._matcher = Matcher(self._nlp.vocab)
        for signal_type, patterns in self._MATCHER_RULES.items():
            rule_name = f"{signal_type}__lemma-v1"
            self._matcher.add(rule_name, patterns)
            self._matcher_signal_types[self._nlp.vocab.strings[rule_name]] = signal_type

        self._dependency_matcher = DependencyMatcher(self._nlp.vocab)
        dependency_rule = "reason_candidate__dependency-v1"
        self._dependency_matcher.add(
            dependency_rule,
            [[
                {
                    "RIGHT_ID": "decision",
                    "RIGHT_ATTRS": {"LEMMA": {"IN": self._DECISION_LEMMAS}},
                },
                {
                    "LEFT_ID": "decision",
                    "REL_OP": ">",
                    "RIGHT_ID": "reason_clause",
                    "RIGHT_ATTRS": {"DEP": {"IN": ["advcl", "ccomp"]}},
                },
            ]],
        )

    def _signals(self, content: str, doc: Any) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        for signal_type, rule_id, pattern in self._PHRASE_RULES:
            for match in pattern.finditer(content):
                start, end = match.span()
                signals.append(
                    self._signal(
                        signal_type,
                        ["phrase"],
                        [rule_id],
                        content[start:end],
                        start,
                        end,
                    )
                )

        for match_id, start_token, end_token in self._matcher(doc):
            span = doc[start_token:end_token]
            signals.append(
                self._signal(
                    self._matcher_signal_types[match_id],
                    ["spacy_matcher"],
                    [self._nlp.vocab.strings[match_id]],
                    span.text,
                    span.start_char,
                    span.end_char,
                )
            )

        for match_id, token_ids in self._dependency_matcher(doc):
            if len(token_ids) != 2:
                continue
            decision_token = doc[token_ids[0]]
            reason_token = doc[token_ids[1]]
            subtree = list(reason_token.subtree)
            start = min(token.idx for token in subtree)
            end = max(token.idx + len(token.text) for token in subtree)
            reason_text = content[start:end]
            if re.search(r"(?:ので|から|ため|理由|せい|ゆえ)", reason_text) is None:
                continue
            signals.append(
                self._signal(
                    "reason_candidate",
                    ["spacy_dependency_matcher"],
                    [self._nlp.vocab.strings[match_id]],
                    decision_token.text,
                    start,
                    end,
                    reason=reason_text,
                )
            )
        return self._deduplicate(signals)

    @classmethod
    def _deduplicate(cls, signals: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        ordered = sorted(
            signals,
            key=lambda item: (item["char_start"], item["char_end"], item["type"], item["rule_ids"]),
        )
        merged: list[dict[str, Any]] = []
        for candidate in ordered:
            duplicate = next(
                (
                    existing
                    for existing in merged
                    if existing["type"] == candidate["type"]
                    and (
                        cls._overlap(existing, candidate)
                        or (
                            existing["char_start"] == candidate["char_start"]
                            and existing["char_end"] == candidate["char_end"]
                        )
                    )
                ),
                None,
            )
            if duplicate is None:
                merged.append(candidate)
                continue
            duplicate["sources"] = sorted(set(duplicate["sources"] + candidate["sources"]))
            duplicate["rule_ids"] = sorted(set(duplicate["rule_ids"] + candidate["rule_ids"]))
            if candidate.get("reason") and not duplicate.get("reason"):
                duplicate["reason"] = candidate["reason"]
        return merged

    @staticmethod
    def _overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
        return max(left["char_start"], right["char_start"]) < min(
            left["char_end"], right["char_end"]
        )

    @classmethod
    def _signal(
        cls,
        signal_type: str,
        sources: list[str],
        rule_ids: list[str],
        trigger: str,
        char_start: int,
        char_end: int,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        result = {
            "type": signal_type,
            "sources": sources,
            "rule_ids": rule_ids,
            "trigger": trigger,
            "char_start": char_start,
            "char_end": char_end,
        }
        if reason is not None:
            result["reason"] = reason
        return result

    @staticmethod
    def _add_conversation_context(messages: list[dict[str, Any]]) -> None:
        for index, message in enumerate(messages):
            if not message.get("signals"):
                continue
            previous = messages[index - 1] if index > 0 else None
            message["signal_context"] = {
                "previous": GinzaSignalAnnotator._context_entry(previous),
            }

    @staticmethod
    def _context_entry(message: dict[str, Any] | None) -> dict[str, Any] | None:
        if message is None:
            return None
        return {
            "evidence_id": message.get("evidence_id"),
            "actor": message.get("actor"),
            "signal_types": sorted({item["type"] for item in message.get("signals", [])}),
        }
