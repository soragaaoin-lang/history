# Decision Extraction Prompt v2

`analysis_session.json` から、設計・実装上の重要な意思決定候補を抽出してください。

## 入力の意味

- `messages`: 人間とAssistantの開発会話
- `constraints`: AGENTS.md由来のプロジェクト制約
- `implementation_events`: コマンドやファイル変更の痕跡

制約や実装イベントだけを根拠に、会話に存在しない意思決定や理由を作ってはいけません。

## 抽出基準

- 事実、確定した判断、一時的な提案、相談中の案を区別してください。
- 後の会話で変更・中止された判断は、古い状態を現在方針として扱わないでください。
- 原則として `1 Decision = 1つの独立した判断` にしてください。
- 別々に検索・参照され得る判断は、同じテーマでもDecisionを分けてください。
- ただし、同じ判断の理由や実施条件を不自然に別Decisionへ分割してはいけません。
- 会話にない背景や理由を推測してはいけません。
- 不明な情報は、もっともらしく補完せず `missing_information` に記録してください。
- EvidenceのないDecisionを生成してはいけません。
- `evidence_message_ids` には、入力の `messages` に実在するIDだけを指定してください。
- `constraints` と `implementation_events` のIDを `evidence_message_ids` に入れてはいけません。

## Status

`status` は必ず次のいずれかにしてください。

- `proposed`: 提案されたが採用は確認できない
- `accepted`: 採用された判断
- `rejected`: 明示的に採用されなかった判断
- `superseded`: 後の別方針に置き換えられた判断
- `reverted`: 一度適用された後、元の状態へ戻された判断
- `cancelled`: 作業・企画が中止または放棄されたが、元の状態へ戻したとは確認できない判断
- `unknown`: 状態を根拠から判定できない

`reverted` と `cancelled` を混同してはいけません。

## Confidence

- `high`: 決定内容と状態を直接示す明確なEvidenceがある
- `medium`: Decisionであることは確認できるが、一部の背景・理由・状態が間接的
- `low`: 根拠が限定的または状態が不明

根拠が不足する場合は `low` とし、不足内容を `missing_information` に記録してください。

## 出力契約

出力はJSONだけにしてください。Markdown、コードフェンス、前置き、説明、後書きを付けてはいけません。

トップレベルのキーは `decisions` だけです。`session_id` などのキーを追加してはいけません。

各Decisionは次の13個のキーを、表記どおり必ず一度ずつ持たなければなりません。追加キーは禁止です。

1. `decision_id`
2. `title`
3. `decision`
4. `context`
5. `alternatives`
6. `rationale`
7. `rejected_alternatives`
8. `risks`
9. `revisit_conditions`
10. `evidence_message_ids`
11. `confidence`
12. `missing_information`
13. `status`

次の別名は禁止です。

- `background`
- `alternatives_considered`
- `adoption_reasons`
- `rejection_reasons`

`decision_id` は出力順に `D-001`、`D-002` の形式で重複なく付けてください。

`rejected_alternatives` は文字列配列ではなく、`alternative` と `reason` を持つオブジェクト配列です。却下理由が会話にない案を、推測してこの配列へ入れてはいけません。

以下の形へ厳密に従ってください。

```json
{
  "decisions": [
    {
      "decision_id": "D-001",
      "title": "短いタイトル",
      "decision": "決定内容",
      "context": "会話に記録された背景。なければnull",
      "alternatives": [],
      "rationale": [],
      "rejected_alternatives": [
        {
          "alternative": "却下された案",
          "reason": "会話に記録された却下理由"
        }
      ],
      "risks": [],
      "revisit_conditions": [],
      "evidence_message_ids": ["実在するmessage ID"],
      "confidence": "high",
      "missing_information": [],
      "status": "accepted"
    }
  ]
}
```

最終出力前に、トップレベルと各Decisionに余分なキーがないこと、必須キーがすべてあること、Evidence IDが入力に実在することを確認してください。
