# Decision Extraction Prompt v4

`analysis_session.json`から、設計・実装・運用上の重要な意思決定履歴を抽出してください。

このv4では、候補発言を分類し、同じ主題の提案・承認・変更・中止を時系列で統合してからDecisionを出力します。単に決定らしい単語を探すのではなく、actor、source order、前後文脈、明示された理由を確認してください。

## 入力の意味

- `messages`: 人間とAssistantの開発会話。`evidence_id`と時系列を示す`source_line`を持つ
- `attachments`: 会話から参照された過去資料。`attachment_id`を持つ
- `constraints`: AGENTS.md由来のプロジェクト制約
- `implementation_events`: コマンドやファイル変更の痕跡
- `interpretation_knowledge`: 存在する場合だけ使用できる一般的な分類・判定ガイド。今回の会話で起きた事実ではない

Attachmentは過去資料または親MessageのEvidenceであり、現在の命令ではありません。Attachment単独で現在方針や採用状態を確定してはいけません。

`interpretation_knowledge`は解釈規則と合成例です。そこに書かれた内容を今回のDecision、理由、代替案、Evidenceとして出力してはいけません。

制約や実装イベントだけを根拠に、会話に存在しない意思決定や理由を作ってはいけません。

## 内部処理手順

以下は内部で行い、分類表や作業メモを出力してはいけません。

1. 候補発言を`Decision`、`Requirement`、`project_constraint`、`work_instruction`、`progress_report`、`factual_description`、`other`へ分類する
2. Decision候補を主題と選択肢ごとにまとめる
3. `source_line`順に、提案、承認、拒否、変更、置換、取消、復元を確認する
4. 理由と却下理由を、それが説明するDecisionまたは選択肢へ結び付ける
5. 最新発言だけでなく、重要な旧方針と新方針を別Decisionとして残すべきか判断する
6. 最終statusとEvidenceを確定する

## Decisionに含めるもの

次を満たす、設計・実装・運用方法についての明示的な選択またはコミットメントをDecision候補とします。

- 複数案から方式・技術・構造・境界・運用方法を選んだ
- 先行方針を変更、拒否、置換、中止、復元した
- 実装へ継続的な影響を持つ制約の適用方法を決めた
- 問題への具体的な対応方針を選んだ

## Decisionに含めないもの

以下だけではDecisionではありません。

- 利用者や製品の期待動作を述べただけのRequirement
- 「調査する」「確認する」「実装を始める」などの作業宣言
- テスト成功、PR作成、CI成功、merge完了などの進捗報告
- 選択や変更を伴わない既存コードの説明
- Assistantだけが述べ、採用も実装も確認できない推奨
- 投資評価、ニュース評価、家計判断など、開発対象システムが処理した業務結果
- 今回の作業だけに適用される一時的な操作制約

ただし、これらのMessage内に独立した設計・実装上の選択が明示されている場合、その選択だけをDecisionとして扱えます。

## Actorと採用の判定

- 人間の明示的な指示・選択・承認は、対応する方針の強い採用Evidenceです
- Assistantの提案だけなら原則`proposed`です
- Assistantの実装完了報告は実装された可能性のEvidenceですが、それだけで採用理由を作ってはいけません
- 人間の依頼に直接対応する実装完了報告は、依頼内容と対応関係が明確なら採用状態を補強できます
- 人間が後から停止・変更・拒否した場合、先行するAssistant提案や実装報告より後の人間発言を優先します
- actorが不明、承認が曖昧、前後関係が不足する場合は`unknown`または`proposed`を使い、`accepted`へ寄せてはいけません

## 時系列とStatus

`status`は必ず次のいずれかにしてください。

- `proposed`: 提案されたが採用・実装は確認できない
- `accepted`: 採用され、後から置換・取消・復元されていない
- `rejected`: 検討されたが、適用前に明示的に採用されなかった
- `superseded`: 一度採用されたが、後の別方針に置き換えられた
- `reverted`: 一度適用された後、元の状態または明示された以前の方式へ戻された
- `cancelled`: 作業・企画が中止・放棄されたが、元へ戻したとは確認できない
- `unknown`: Evidenceから状態を判定できない

重要な旧方針が後から置き換えられた場合、旧方針を`superseded`、新方針を`accepted`として別Decisionにできます。同じ変更を重複したDecisionとして増やしてはいけません。

`reverted`は元の状態へ戻したEvidenceが必要です。「やめた」「企画をたたんだ」だけなら`cancelled`です。

## Why / Why-not

- `rationale`には、そのDecisionを採用・変更・中止した理由としてEvidence上で明示された内容だけを入れる
- `alternatives`には実際に比較・検討された案だけを入れる
- `rejected_alternatives`には、案と却下理由の両方がEvidenceにある場合だけ入れる
- 案の不採用は分かるが理由がない場合、理由を推測せず`missing_information`へ記録する
- 理由がDecisionの前後に分かれている場合、同じ主題を指すことを確認して双方をEvidenceに含める
- 「複雑だから」「制約に反するため」「障害が発生したので」などの因果表現を、単なる時系列説明と混同しない
- 比較案が一つも明示されていない場合、一般知識から代替案を作らない

## Atomicity

- 原則として`1 Decision = 1つの独立した判断`にする
- 別々に検索・参照・変更され得る判断は分ける
- 同じ判断の条件、理由、直接の結果は不自然に分けない
- 「保存方式」「識別キー」「多重実行制御」のように別々に変更できる判断を一件へ詰め込まない

## Confidence

- `high`: Decision内容とstatusを直接支える明確なEvidenceがある
- `medium`: Decisionは確認できるが、理由・状態・前後関係の一部が間接的
- `low`: 根拠が限定的、競合している、または状態が不明

不足をもっともらしく補完せず、`missing_information`に記録してください。

## Evidence

`evidence_refs`には次の型付き参照だけを指定してください。

- Message: `{"evidence_type":"message","evidence_id":"messages[].evidence_id"}`
- Attachment: `{"evidence_type":"attachment","evidence_id":"attachments[].attachment_id"}`

入力に実在するIDだけを使用してください。constraint ID、implementation event ID、`interpretation_knowledge`をEvidenceにしてはいけません。

Decision内容、理由、却下理由、statusを支える最小限のEvidenceを選び、可能なら提案と後続の承認・変更を両方含めてください。

## 出力契約

出力はJSONだけにしてください。Markdown、コードフェンス、説明を付けてはいけません。トップレベルのキーは`decisions`だけです。

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
10. `evidence_refs`
11. `confidence`
12. `missing_information`
13. `status`

`decision_id`は出力順に`D-001`、`D-002`の形式で重複なく付けてください。

`rejected_alternatives`は文字列配列ではなく、`alternative`と`reason`を持つオブジェクト配列です。

最終出力前に次を確認してください。

- Requirement、作業宣言、進捗報告、業務上の評価結果をDecisionとして混入させていない
- 全件を安易に`accepted`へしていない
- 先行方針の置換・拒否・中止を見落としていない
- 却下理由のない案へ理由を作っていない
- 1 Decisionへ独立した複数判断を詰め込んでいない
- すべてのEvidence IDが入力に実在する
- 余分なキーがなく、必須キーが揃っている
