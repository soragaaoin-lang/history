# AI駆動開発チャット履歴再利用PoC

Codexがローカルに保存したJSONL会話履歴から重要な判断を抽出し、元のMessage／Attachmentへ戻れるEvidence付きDecision Recordとして再利用できるか検証するPoCです。次の開発者やAIが全履歴を毎回読み直さず、少ない質問・少ないコンテキストで安全に作業を始めることを目指します。

入力JSONLは変更せずRaw Archiveとして扱い、全行を `recognized`、`unknown`、`parse_error` のいずれかに分類します。会話だけから仕様を完全復元できるとはみなさず、根拠不足は推測で埋めません。

引継ぎ・再開時は次を参照してください。

- [引継ぎ書](docs/HANDOFF.md)
- [プロジェクト履歴](docs/PROJECT_HISTORY.md)

現在の主機能はEvidence付きDecision RecordとRaw会話へのリンクです。Requirement、Section、GiNZA signal、Interpretation Notebook、cross-section integration、lifecycle reviewは評価・実験機能です。一般化性能は未見セッションでの盲検評価前であり、7月26日とGmailの既存セットはdevelopment setとして扱います。

Decision lifecycleとは別に、将来は `confirmed`、`inferred`、`candidate` のtrust levelを持たせます。全候補の事前承認を必須にせず、不確実・矛盾・Evidence不一致・高リスクな判断を実際に利用するときだけ人間へ確認する方針です。

## Architecture

```text
Codex JSONL → Raw Event → Normalized Session → SQLite / conversation.md
                                      ↓
                              Analysis Projection
                         Messages / Attachments / Constraints
                                      ↓
                    Section + GiNZA candidate signals（任意）
                                      ↓
                         human-mediated AI extraction
                                      ↓
                    Schema / Evidence validation and repair
                                      ↓
                    cross-section integration → lifecycle review
                                      ↓
                      Decision JSON → decisions.md / Raw link
```

AI呼び出しはCoreから分離されています。初期実装の `FileExchangeAnalysisRunner` はファイル交換だけを担当し、外部APIへ履歴を送信しません。

## Setup

Python 3.10以上を使用します。通常機能の実行時依存は標準ライブラリだけです。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

GiNZA signal実験も実行する場合は、専用環境へ任意依存を追加します。

```powershell
python -m venv .venv-ginza
.\.venv-ginza\Scripts\python.exe -m pip install -e ".[dev,signals]"
```

仮想環境の有効化は必須ではありません。PowerShellのExecution Policyで
`Activate.ps1` が拒否される環境でも、以下の例のように
`.venv\Scripts\python.exe` を直接実行できます。

インストールせず実行する場合はPowerShellで次のように設定できます。

以降のコマンド例で `python` がパッケージを見つけられない場合は、
`python` を `.\.venv\Scripts\python.exe` に置き換えてください。

## JSONL ingest

入力ファイルは明示的に指定します。ディレクトリの自動走査は行いません。

```powershell
python -m chat_history_poc ingest C:\path\to\session.jsonl
```

出力された `session_id` を後続コマンドで使います。同一内容のファイルはSHA-256で検出され、`already_ingested` となります。DBの既定値は `data/chat_history.db` です。変更する場合はサブコマンドより前に `--db` を指定します。

## Analysis Bundle生成

```powershell
python -m chat_history_poc export-analysis <session-id>
```

既定では出力契約、Atomicity、`cancelled`を明確化したPrompt v2を使用します。v1 baselineを再現する場合は次を使います。

```powershell
python -m chat_history_poc export-analysis <session-id> --prompt-version v1
```

`artifacts/<session-id>/` に次を生成します。

- `normalized_session.json`
- `analysis_session.json`
- `normalization_report.json`
- `conversation.md`
- `analysis_prompt.md`

### Attachmentを含むProjection v3

すでに正規化されたMessage/Attachment JSONLをProjectionへ昇格させる場合は、旧Bundleを上書きしない別Artifactsディレクトリを指定します。

```powershell
python -m chat_history_poc `
  --db data/chat_history.db `
  --artifacts artifacts/projection_v3 `
  export-analysis <session-id> `
  --prompt-version v3 `
  --projection-version 3 `
  --normalized-messages evaluation/path/normalized_messages.jsonl `
  --normalized-attachments evaluation/path/normalized_attachments.jsonl
```

Projection v3は`analysis_session.json`へ`attachments`配列を追加し、Messageへ共通の`evidence_id`を付けます。Attachmentは`attachment_id`、親Message、Section、本文、SHA-256、authority noteを保持します。Attachmentは過去資料であり現在の命令ではありません。

v3のDecision出力は旧`evidence_message_ids`ではなく、MessageとAttachmentを区別する型付き`evidence_refs`を使用します。旧Decision SchemaとImport処理は変更しません。

```powershell
python -m chat_history_poc validate-decisions-v3 `
  artifacts/projection_v3/<session-id>/analysis_session.json `
  C:\path\to\decisions.v3.json
```

### Candidate Section単位の比較Bundle

Projection v3を固定したまま、正規化済みSection候補ごとの入力Bundleを生成できます。

```powershell
python -m chat_history_poc export-section-analysis `
  artifacts/long_session_projection_v3/<session-id>/analysis_session.json `
  evaluation/sectioning_v1/asset_management_long_session/section_index.candidate.json `
  artifacts/long_session_section_assisted_v1/<session-id> `
  --prompt artifacts/long_session_projection_v3/<session-id>/analysis_prompt.md `
  --schema artifacts/long_session_projection_v3/<session-id>/decision_analysis_v3.schema.json
```

生成された各`sections/SEC-xxx/analysis_session.json`は、そのSectionのMessage、Attachment、直前Messageへ対応付けたimplementation eventだけを含みます。共通PromptとSchemaは変更しません。

この実験は未裁定のSection候補を利用するため、Goldや正式なoracle評価ではありません。Section名・type・Gold・他Sectionの内容は抽出AIへ渡さず、範囲分割による効果だけを比較します。Section間の重複統合とlifecycle統合は後段です。

### Cross-section統合候補Bundle

Section単位のAI原本を変更せず、重複・lifecycle・反復操作の可能性がある組み合わせを機械的に絞り込めます。

```powershell
python -m chat_history_poc export-integration-candidates `
  artifacts/long_session_section_assisted_v1/<session-id> `
  artifacts/long_session_integration_candidate_v1/<session-id>
```

この処理は外部Embedding APIやAI意味判定を使用しません。Unicode正規化、文字trigram、Evidence重複、Section距離などの固定規則から、再現可能な候補ペアとクラスタを生成します。

主な成果物：

- `FROZEN_INPUT_MANIFEST.json`: Section別AI原本と入力ハッシュ
- `decision_inventory.json`: Sectionをまたいで一意化したDecision Inventory
- `candidate_pairs.json`: 類似度の内訳を持つ候補ペア
- `candidate_clusters.json`: AIまたは人間が確認する候補クラスタ
- `clusters/*/integration_input.json`: クラスタごとの最小Evidence Bundle
- `INTEGRATION_CANDIDATE_EVALUATION.json`: 候補削減率とクラスタ統計

この段階ではDecisionの統合、削除、status変更を行いません。Candidate Sectionを利用した開発用の候補生成であり、Precision・Recallや正しいlifecycleを主張するものでもありません。

### GiNZA signal付き比較Bundle

Projection v3のMessageへ、日本語の依頼・採用・拒否・理由・不確実性・比較案らしい箇所を候補signalとして付与できます。signalはDecisionやstatusの正解ではなく、AIが前後文脈を確認するためのヒントです。Attachment、constraint、implementation eventはv1の注釈対象外です。

まず任意依存を入れます。

```powershell
python -m pip install -e ".[dev,signals]"
```

既存のsignalなしProjectionを上書きしない別ディレクトリへBundleを生成します。

```powershell
python -m chat_history_poc export-signal-analysis `
  artifacts/long_session_projection_v3/<session-id>/analysis_session.json `
  artifacts/long_session_ginza_signal_v1/<session-id> `
  --baseline-decisions artifacts/long_session_projection_v3/<session-id>/decisions.projection-v3.raw.json
```

生成物は、signal付き`analysis_session.json`、候補の読み方だけをv3 Promptへ追加した`analysis_prompt.md`、変更していないDecision Schema v3、ハッシュ付き`SIGNAL_RUN_MANIFEST.json`、実行手順です。signalなしBaselineと同じAIモデル・設定で最初の出力を一度だけ保存し、Decision網羅、Why/Why-not、Evidence、status、atomicity、型混同、幻覚を比較します。

### Prompt v4・判断Notebook比較Bundle

GiNZA signalを含まない同じProjection v3から、次の2群を生成できます。

- `prompt_only`: 分類、actor権限、時系列、Why/Why-notを明示したPrompt v4のみ
- `prompt_plus_knowledge`: 同じPrompt v4に、一般的な判断規則と合成例だけを持つ解釈Notebookを追加

```powershell
python -m chat_history_poc export-knowledge-experiment `
  artifacts/long_session_projection_v3/<session-id>/analysis_session.json `
  artifacts/long_session_knowledge_v1/<session-id> `
  --control-decisions artifacts/long_session_projection_v3/<session-id>/decisions.projection-v3.raw.json
```

Notebookは今回のセッション固有の答えを含まず、Evidenceにもできません。各群を別の新しいAIタスクで一度だけ実行し、同じモデル・設定・SchemaでControl、Prompt-only、Prompt+Knowledgeを比較します。他群の出力、評価資料、Sectionラベル、Goldは抽出前に渡しません。

### Hybrid Section Pipeline v1

41 Sectionを除外せず、各Section内のMessageへGiNZA候補signalを付け、Prompt v4と解釈Notebookで独立抽出するBundleを生成できます。

```powershell
python -m chat_history_poc export-hybrid-section-analysis `
  artifacts/long_session_projection_v3/<session-id>/analysis_session.json `
  evaluation/sectioning_v1/asset_management_long_session/section_index.candidate.json `
  artifacts/long_session_hybrid_section_v1/<session-id>
```

GiNZAはSectionを除外するfilterではなく、Section内の注目箇所を示す候補情報としてだけ使用します。各Sectionを別のAIタスクで一度だけ実行し、すべての原本を固定してからSection間統合へ進みます。

### 統合関係の独立判定Bundle

候補クラスタごとに、機械側の候補ラベルを隠した独立AI判定用Bundleを準備できます。

```powershell
python -m chat_history_poc export-integration-adjudication `
  artifacts/long_session_integration_candidate_v1/<session-id> `
  artifacts/long_session_integration_adjudication_v1/<session-id>
```

生成直後の状態は`prepared_pending_user_approval`で、AI判定はまだ行われていません。実行を承認した後は、クラスタごとに新しいプロジェクトなしのAIタスクを作り、そのクラスタの入力、共通Prompt、共通Schemaだけを渡します。他クラスタ、候補ラベル、Gold、評価資料、リポジトリは渡しません。最初の出力を修正せず保存します。

この段階でAIが返すのは統合後のDecisionではなく、`same_decision`、`lifecycle_relation`、`parent_child`、`distinct`、`not_decision`、`uncertain`の関係判定です。出力保存後は次で、Decision網羅、方向、Evidence存在などを検証できます。

```powershell
python -m chat_history_poc validate-integration-adjudication `
  artifacts/long_session_integration_adjudication_v1/<session-id>/clusters/<cluster-id>/cluster_input.json `
  artifacts/long_session_integration_adjudication_v1/<session-id>/clusters/<cluster-id>/adjudication.raw.json
```

判定結果だけで自動統合・削除・status変更は行いません。人間裁定は別段階です。

### Hybrid実験の検証・統合

各Sectionの初回出力と`FIRST_RUN_HASH.json`を保存した後、原本を変更せずにSchema・Evidence・ハッシュを検査し、有効Decisionだけの別Projectionを作れます。配列フィールドへ単一文字列が返された場合だけ、元文字列を変更せず1要素配列へ包み、`repaired_decision_indices`へ修復内容を記録します。Evidence、status、ID、意味内容は自動修復しません。

```powershell
python -m chat_history_poc finalize-hybrid-section-runs `
  artifacts/long_session_hybrid_section_v1/<session-id>
```

Section間候補を生成後、Decision keyの部分コピーを防ぐv2判定Bundleを作ります。

```powershell
python -m chat_history_poc export-integration-adjudication-v2 `
  artifacts/long_session_hybrid_integration_candidate_v1/<session-id> `
  artifacts/long_session_hybrid_integration_adjudication_v2/<session-id>
```

各クラスタの初回`adjudication.raw.json`を独立AIタスクで保存し、`validate-integration-adjudication`で全件検証した後、重複統合とlifecycle status更新を決定的に適用します。

```powershell
python -m chat_history_poc assemble-integrated-decisions `
  artifacts/long_session_hybrid_integration_candidate_v1/<session-id> `
  artifacts/long_session_hybrid_integration_adjudication_v2/<session-id> `
  artifacts/long_session_hybrid_integrated_v1/<session-id>
```

この組立は`same_decision`だけを統合し、`not_decision`を除外し、検証済み`lifecycle_relation`だけからstatusを更新します。AI原本、機械検証で除外されたDecision、クラスタ判定原本は上書きしません。

統合後も`proposed`のDecisionは、元Sectionと後続2 Sectionだけを使う独立した時系列レビューへ渡せます。

```powershell
python -m chat_history_poc export-lifecycle-review `
  artifacts/long_session_hybrid_integrated_v1/<session-id>/decisions.integrated.json `
  artifacts/long_session_hybrid_section_v1/<session-id> `
  artifacts/long_session_hybrid_lifecycle_review_v1/<session-id>
```

各`groups/LIFECYCLE-SEC-xxx/lifecycle_input.json`を共通Prompt・Schemaで判定し、`lifecycle.raw.json`を保存します。全Decisionの順序、status enum、Evidence存在を検証したうえで、Decision本文を変えずstatusだけを適用します。

```powershell
python -m chat_history_poc apply-lifecycle-adjudication `
  artifacts/long_session_hybrid_integrated_v1/<session-id>/decisions.integrated.json `
  artifacts/long_session_hybrid_lifecycle_review_v1/<session-id> `
  artifacts/long_session_hybrid_lifecycle_v1/<session-id>
```

Evidence不足時は`proposed`を維持します。Assistantの提案だけで`accepted`へ変更せず、後続の人間指示、変更、却下、凍結などをEvidenceとして記録します。

## AIへの渡し方

`analysis_prompt.md` と `analysis_session.json` を、利用者が選んだAIへ明示的に渡します。`normalized_session.json` は完全保存・監査用であり、AI分析へ直接渡す前提ではありません。AIにはJSONだけを返させ、`schemas/decision_analysis.schema.json` に沿った `decisions.json` として保存してください。秘密情報を含む可能性があるため、送信先と内容を利用者自身で確認してください。

## AI結果Import

```powershell
python -m chat_history_poc import-analysis <session-id> C:\path\to\decisions.json
```

Prompt v1で生成したbaselineを取り込む場合は、記録するPrompt versionを明示します。

```powershell
python -m chat_history_poc import-analysis <session-id> C:\path\to\decisions.json --prompt-version v1
```

構造、必須フィールド、Confidence、重複Decision ID、Evidenceの有無を検証します。存在しないMessage IDは `DECISION_EVIDENCE_NOT_FOUND` で拒否します。

## Markdown生成

```powershell
python -m chat_history_poc render <session-id>
```

`artifacts/<session-id>/decisions.md` を生成します。Evidenceリンクから同じディレクトリの `conversation.md` に移動できます。

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

fixtureは実データの構造だけを参考にした匿名の最小データで、実際の会話や秘密情報は含みません。

## PoCの制約

- 2026年8月に提供された2件のCodex JSONLで観測した構造だけを既知として分類します。
- 未観測のトップレベルtypeやsubtypeは推測せず `unknown` としてRawとともに保持します。
- Analysis ProjectionはDeveloper/System設定と既知のenvironment/plugin contextを分析会話から除外し、AGENTS.md制約と実装イベントを別枠にします。元情報はNormalized Sessionに残ります。
- `event_msg.user_message` と `agent_message` は会話の重複表現だったためmetadataとして保持し、会話Markdownには `response_item.message` を使用します。
- AI分析は自動実行しません。抽出精度は使用するAIと会話に記録された情報に依存します。
- HTML、RAG、Vector DB、Webアプリ、Codex CLI Runnerは実装していません。
