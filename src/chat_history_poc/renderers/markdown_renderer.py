from __future__ import annotations

from chat_history_poc.domain.models import DecisionCandidate, NormalizedEvent


def render_conversation(messages: list[NormalizedEvent]) -> str:
    parts = ["# Conversation", ""]
    for message in messages:
        parts.extend([f"### {message.id}", "", f"**{(message.role or 'Unknown').title()}**", "",
                      message.content or "", "", f"Source JSONL line: {message.source_line}", "", "---", ""])
    return "\n".join(parts)


def render_decisions(decisions: list[DecisionCandidate]) -> str:
    parts = ["# 意思決定一覧", ""]
    for item in decisions:
        parts.extend([f"## {item.decision_id} {item.title}", "", "### 決定", "", item.decision, "",
                      "### 状態", "", item.status, "", "### 背景", "", item.context or "記録なし", ""])
        _list(parts, "比較案", item.alternatives)
        _list(parts, "採用理由", item.rationale)
        parts.extend(["### 却下理由", ""])
        if item.rejected_alternatives:
            for rejected in item.rejected_alternatives:
                parts.extend([f"- {rejected.alternative}", f"  - {rejected.reason}"])
        else:
            parts.append("- なし")
        parts.append("")
        _list(parts, "リスク", item.risks)
        _list(parts, "見直し条件", item.revisit_conditions)
        _list(parts, "不足情報", item.missing_information)
        parts.extend(["### Confidence", "", item.confidence, "", "### 根拠", ""])
        parts.extend([f"- [{mid}](conversation.md#{mid})" for mid in item.evidence_message_ids])
        parts.append("")
    return "\n".join(parts)


def _list(parts: list[str], title: str, values: list[str]) -> None:
    parts.extend([f"### {title}", ""])
    parts.extend([f"- {value}" for value in values] or ["- なし"])
    parts.append("")
