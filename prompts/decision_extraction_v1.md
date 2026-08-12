# Decision Extraction Prompt v1

添付された `analysis_session.json` から、設計・実装上の重要な意思決定候補を抽出してください。

`messages` は人間とAssistantの開発会話、`constraints` はAGENTS.md由来のプロジェクト制約、
`implementation_events` はコマンドやファイル変更の痕跡です。制約や実装イベントだけを根拠に、
会話に存在しない意思決定理由を作ってはいけません。

出力は `decision_analysis.schema.json` に従うJSONオブジェクトだけにしてください。Markdownや説明文を付けないでください。

各候補に、決定内容、背景、比較した案、採用理由、却下理由、リスク、見直し条件、Evidence Message IDs、Confidence、不足情報を含めてください。

厳守事項：

- 会話に存在しない情報を推測してはいけません。
- 理由が記録されていない場合、もっともらしい理由を生成せず `missing_information` へ記録してください。
- 一時的な提案を確定した決定として扱わないでください。
- 撤回された判断は最終決定と区別してください。
- EvidenceのないDecisionを生成してはいけません。
- `evidence_message_ids` には入力中に実在する `kind: message` のIDだけを指定してください。
- Confidenceは `high`、`medium`、`low` のいずれかにしてください。
- 根拠が不足している候補のConfidenceは `low` にしてください。
- `status` は `proposed`、`accepted`、`rejected`、`superseded`、`reverted`、`unknown` のいずれかにしてください。
- 後から撤回・置換された判断を、現在も有効な最終決定として扱わないでください。
