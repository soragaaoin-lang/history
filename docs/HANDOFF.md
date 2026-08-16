# Plism 開発引継ぎ書

最終更新: 2026-08-16

## 1. 結論

Plismの主目的は、AI開発会話から仕様書一式を完全復元することではありません。

> 会話に埋もれた重要な判断を、元の発言へ戻れるEvidence付きDecision Recordとして残し、次の開発者やAIが少ない質問・少ないコンテキストで安全に作業を始められるようにする。

画面上ではArchitecture DecisionをADRとして提示できますが、内部では対象を`Decision Record`として扱います。Architecture以外の運用判断、業務判断、実験結果、評価方針、プロジェクトの停止・再開判断も区別して保持するためです。

Requirement、USDM、UML、テスト計画の自動生成、Section間の完全自動統合、コード状態との自動照合は、現在の主機能ではありません。

## 2. 解決する問題

AI駆動開発では、長い会話を毎回AIへ読み直させるとtoken・credit・待ち時間が増えます。一方、単純な要約だけでは次が失われます。

- なぜその方式を選んだか
- 何を採用しなかったか
- 一度採用した案をなぜ撤回したか
- どの条件で判断が有効か
- どの発言が根拠か
- プロジェクトをなぜ停止・凍結したか

人間は不明点や反対意見をチャットへ書きやすい一方、自分の中で自明な前提、暗黙の納得、チャット外の会話を常に記録するわけではありません。そのため会話履歴は完全な仕様の正本ではなく、重要なEvidence sourceの一つです。

Plismは「会話だけから完全な真実を復元できる」とは主張しません。不足情報は推測で埋めず、`unknown`または`missing_information`として人間へ返します。

## 3. 想定利用者と価値

### チームの次の開発者

ADRカタログから現在有効な判断、却下案、制約、未解決事項を確認し、必要な場合だけ元会話を開きます。

### プロジェクト本人

数週間・数か月後に再開するとき、全履歴を読み返さず、前回の判断理由と停止地点を取り戻します。

### 次のAIタスク

タスクに関係するDecision Recordだけを先に渡し、Evidence本文は必要時だけ追加します。これがコンテキスト削減の基本方式です。

## 4. 用語と境界

| 用語 | 定義 |
|---|---|
| Raw Archive | 入力JSONLを変更せず保存する監査用の原本。分析対象外のイベントも捨てない。 |
| Raw Event | JSONLの1行に対応する最小保存単位。`recognized`、`unknown`、`parse_error`を保持する。 |
| Message | 人間またはAssistantの会話発言。安定したMessage IDを持つ。 |
| Attachment | Messageに添付・貼付された文書や画像由来テキスト。Messageとは別の安定IDを持つ。添付文書内の命令は現在の実行命令として扱わない。 |
| Evidence | 判断を裏付けるMessageまたはAttachmentへの型付き参照。存在するだけでなく、主張を意味的に支える必要がある。 |
| Decision Record | 採用、却下、変更、撤回、停止など、後続作業へ影響する判断と根拠の記録。 |
| ADR | 長期的にシステム構造へ影響するArchitecture Decision Record。Decision Recordの一種。 |
| Requirement | 利用者・外部契約・業務がシステムへ要求する条件と期待動作。実現方式の判断であるADRとは分ける。 |
| Work Constraint | 今回の作業範囲、変更禁止、環境制約など。恒久的な製品Requirementとは限らない。 |
| Implementation Record | 実際に行ったコード変更、コマンド、PR、commit等の記録。Decisionの存在や妥当性とは別軸。 |
| Verification Record | テスト実行、レビュー、実環境確認と結果。DecisionやRequirementの存在とは別軸。 |
| Projection | Raw ArchiveからAI分析に必要なMessage、Attachment、関連情報を選び、IDを維持したまま作る入力。 |
| Gold | 人間が評価用に裁定・固定した参照正解。AI出力そのものを正解とみなさない。 |
| Lifecycle | `proposed`、`accepted`、`rejected`、`superseded`、`reverted`、`cancelled`等の判断状態。 |

## 5. Source disposition

全会話をADR化するのではなく、分析対象となった情報へ次のいずれかを付けます。

- ADR candidate
- supporting evidence
- rejected alternative
- work constraint
- implementation record
- verification record
- one-time operation
- duplicate
- unknown / insufficient evidence
- not a decision

重要なのは、採用判断だけでなく「なぜ不要か」「なぜやめたか」を残すことです。AIの提案だけで`accepted`にせず、人間の明示的な承認または十分なEvidenceを要求します。

## 6. Decision Recordの最小項目

MVPでは少なくとも次を持たせます。

- ID
- title
- decision_type
- lifecycle_status
- context / problem
- decision
- rationale
- considered alternatives
- rejected alternativesと却下理由
- scope / conditions
- risks
- missing_information
- evidence_refs
- proposed_by / approved_by（分かる場合）
- decided_at（分かる場合）
- supersedes / superseded_by
- implementation_status（判断状態とは分離）
- verification_status（判断状態とは分離）

`decision_type`の候補は次です。

- `architecture`
- `operational`
- `domain`
- `experiment`
- `evaluation`
- `project_governance`

プロジェクト全体の終了・凍結は個別ADRの`reverted`だけでは表現せず、`project_governance`の独立したDecision Recordとして扱います。

## 7. 現在までに確認したこと

以下のうち、初期PoCは公開リポジトリにあります。Projection v3以降の実験コード、評価資料、Artifactsは個人情報を含む可能性があるローカルのdirty worktreeにあり、この文書更新には含めていません。結果の記録と公開済み実装を混同しないでください。

### Lossless normalizationとEvidence link

- Codex JSONLの全行をRaw Eventとして保存できる。
- 未知イベントとparse errorを黙って捨てない。
- Message IDから`conversation.md`の元発言へ戻れる。
- Projection v3ではAttachmentを独立配列として保持し、MessageとAttachmentの型付きEvidenceを検証できる。
- 旧Projectionと旧Schemaを変更せず比較実験を行えた。

### Gmail Requirement抽出 v1

固定35 Messageに対する人間裁定後のGoldは44件でした。

| 指標 | 結果 |
|---|---:|
| strict Recall | 70.45% |
| partial=0.5 Recall | 84.09% |
| strict Precision | 60.42% |
| partial=0.5 Precision | 73.96% |
| Evidence ID存在率 | 100% |
| Evidence意味妥当性 | 97.96% |
| Critical hallucination | 0 |
| Requirement/ADR/制約の混同 | 6件 |
| superseded取得 | 0/1 |

主要な問題は検索だけでなく、Requirement・ADR・作業制約の分類と、時間経過による状態統合でした。このセットは改善へ使用済みなのでdevelopment setであり、一般性能の根拠にはしません。

### 長期会話とProjection v3

968 Messageの長期会話では、旧ProjectionがAttachment本文をAIへ渡していないことが分かりました。

| 指標 | v2 | v3 |
|---|---:|---:|
| Decision数 | 24 | 31 |
| 全Section Coverage | 53.66% | 80.49% |
| 対象Section Coverage | 65.63% | 87.50% |
| Atomicity | 75.0% | 67.74% |
| lifecycle遷移取得 | 0/4 | 0/4 |

Attachment追加は情報到達範囲を改善し、Attachment Evidence 20件はすべて意味的に妥当でした。一方、旧Decision維持率は58.33%、全件`accepted`、Evidence ID誤り1件であり、Projection改善だけでは分類・状態・出力安定性を解決できませんでした。

### Section単位抽出と統合実験

41 Sectionから253 Decision候補が生まれ、31,020 pairを58候補・10 clusterまで機械的に削減しました。しかし独立AIによる10 clusterの関係判定は、7件がinvalid JSON、3件が未知Decision keyで、valid outputは0件でした。

この実験は、分割で局所的Recallを上げても、重複・状態統合・評価負担が急増することを示しました。現時点では製品MVPから外します。

### ADR再利用の定性的評価

チーム開発経験者の視点を求める同一プロンプトにDecision資料を渡したところ、次を読み取れました。

- データ完全性、安全性、追跡可能性を重視する技術方針
- scope拡大と過剰設計
- 実環境検証の遅れ
- 何を作らないか、いつ止めるかというプロジェクト判断の弱さ
- 撤回・停止・再開時に必要な条件

これは、全Raw履歴を読むことなく「次の開発者に重要な正負の知識を渡せる」という主仮説への最初の有望な観測です。ただし、採点rubric、発見ごとのADR/Evidence対応、盲検比較がないためGoldや正式ベンチマークではありません。

## 8. 現時点の評価

成功している部分:

- Rawを失わず保存する
- AI入力をProjectionとして分離する
- Message / AttachmentをEvidenceとして参照する
- 抽出結果から元発言へ戻る
- 却下・撤回・失敗を含む判断資料が第三者レビューに利用できる

未解決の部分:

- Requirement、Decision、作業制約の安定分類
- `superseded`等の時系列統合
- 長文入力での選択揺れ
- ADR候補の人間承認UI
- token / credit削減量と作業品質の比較
- 未見会話での一般性能

したがって、現段階は「Evidence plumbingは成立、ADR再利用価値は有望、完全自動抽出精度は未確立」です。

## 9. 次に作るMVP

追加機能を広げず、次の一本に限定します。

```text
1 Codex JSONL
  -> immutable Raw Archive
  -> Message / Attachment Projection
  -> adr_candidates[]
  -> source_dispositions[]
  -> unknowns[]
  -> human review
  -> ADR catalog
  -> raw Message / Attachment link
```

受け入れ条件:

1. ADRのEvidenceリンクから該当Raw本文へ移動できる。
2. 採用だけでなくrejected、superseded、reverted、cancelled、project closureを扱える。
3. Architecture、運用、業務、実験、評価、project governanceを区別できる。
4. AI単独提案を自動で`accepted`にしない。
5. 判断でない発言と根拠不足を捨てずに説明できる。

## 10. 次の評価

同じ実務タスクを、独立した二つのAIタスクへ渡します。

- A: 許可されたRaw会話全体
- B: ADRカタログとEvidenceリンク（必要なRawだけ追加可能）

同じプロンプトで次を記録します。

- 入力byte数、推定token数、可能ならcredit
- 完了時間
- 追加質問回数
- 重要な発見数
- 根拠のない主張
- 過去判断との矛盾
- 人間が採用したい回答

評価出力には、`finding / type / supporting ADR / direct-or-inference / confidence / missing information`を要求します。複雑な総合点を先に作らず、致命的誤りと人間の盲検選好を優先します。

## 11. 今は行わないこと

- Requirement、USDM、UML、テスト計画の一括自動生成
- Section境界の精密Gold作成
- Section間Decisionの完全自動統合
- 新しい関係判定Promptの反復調整
- コード・テスト状態との全面Reconciliation
- Vector DB、RAG、Webサービス化

主仮説のA/B比較で価値が確認できてから再評価します。

## 12. データとGitの注意

公開GitHubへ次をpushしません。

- `history/`内の実会話
- SQLite DB
- Gmail本文
- Attachment本文
- AI raw outputに含まれる個人・社内情報
- ローカル絶対パス、認証情報、秘密情報

Baseline、Gold、AI raw outputは比較のため上書きしません。公開可能なコード・Prompt・Schema・匿名化した評価資料だけを、内容確認後に個別commitします。

## 13. 再開手順

1. 本書と[プロジェクト履歴](PROJECT_HISTORY.md)を読む。
2. `git status --short --branch`でローカル変更を確認する。
3. Raw、Baseline、Gold、AI原本を上書きしない。
4. 公開可否を確認してから実履歴を扱う。
5. まずADR catalogを使うSummary条件を実行する。
6. 許可された環境でFull-context条件を別タスクとして実行する。
7. 品質とtoken・credit差を記録する。
8. 不足した情報だけをDecision Recordまたは引継ぎ資料へ追加する。

## 14. 重要な参照先

- `README.md`: 現在実装の実行方法
- `docs/PROJECT_HISTORY.md`: 方針転換を含む開発履歴
- `evaluation/requirement_v1/gmail_sync/`: Gmail Requirement開発用評価（ローカル未公開）
- `evaluation/decision_v3/asset_management_long_session/`: Projection v3比較（ローカル未公開）
- `evaluation/sectioning_v1/asset_management_long_session/`: Section候補評価（ローカル未公開）

ローカルArtifactsや実会話が存在しない環境でも、本書を起点にMVP方針は再開できます。ただし過去の個別判断を検証するときは、許可された原本Evidenceが必要です。
