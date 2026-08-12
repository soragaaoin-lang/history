# AI駆動開発・意思決定履歴PoC 引継ぎ書

最終更新: 2026-08-12

## 1. 引継ぎの目的

この文書は、別のPCまたは会社環境で本PoCを再開するときに、現在地、確認済み事実、未評価事項、実行手順を正確に引き継ぐためのものです。

本PoCの目的は、AI駆動開発のチャット履歴を共通形式へ正規化し、設計・実装上の意思決定候補と根拠を後から追跡できるか検証することです。完成した仕様書生成システムや自動判断システムを作ることが目的ではありません。

## 2. 現在の到達点

現在、次のパイプラインが成立しています。

```text
Codex JSONL
  ↓ Raw Eventを全件保存
Normalized Session
  ↓ 分析対象を投影
Analysis Projection
  ↓ AIへ明示的に渡す
Decision Extraction
  ↓ Schema・Evidence検証
SQLite
  ↓ Python Renderer
decisions.md
  ↓ Evidence link
conversation.md
```

一文で表すと、次の状態です。

> Codexの実履歴を欠損なく正規化し、内部コンテキストを分離した分析入力からAIが意思決定候補を構造化し、人間がMarkdownで読み、Evidenceから元会話へ追跡できるところまで成立している。

これは抽出精度や網羅性が証明済みという意味ではありません。

## 3. 確認済みの結果

1件の実Codexセッションで確認した最新値です。

| 項目 | 件数 |
|---|---:|
| Raw events | 8,306 |
| Recognized events | 8,306 |
| Unknown events | 0 |
| Parse errors | 0 |
| Silent drops | 0 |
| Analysis messages | 484 |
| Constraints | 1 |
| Implementation events | 237 |
| AI Decisions v1 | 16 |
| Evidence references | 62 |
| Missing Evidence | 0 |
| Automated tests | 14 passed |

AI Decision v1のstatus内訳は、`accepted` 13件、`superseded` 2件、`reverted` 1件でした。これは人間評価前のbaselineです。

## 4. 実装済み機能

- JSONL全行のRaw保存
- Codex固有形式を扱うAdapter
- `unknown` / `parse_error`の保持
- SHA-256による同一入力の冪等取り込み
- SQLiteへのSession、Raw Event、Event、Analysis Run、Decision、Evidence保存
- `normalization_report.json`
- `conversation.md`
- `normalized_session.json`
- `analysis_session.json`
- Developer/System設定と既知の内部コンテキストの分析対象外化
- AGENTS.md制約の`constraints`への分離
- `file_change` / `command`の`implementation_events`への分離
- Decision JSONの厳密な構造検証
- Evidence Message IDの存在検証
- `decisions.md`と元会話リンクの生成
- Prompt v1とv2の選択およびAnalysis Runへのversion記録

## 5. Promptの状態

### v1

最初の一括抽出に使用したbaselineです。重要なDecisionを16件抽出できましたが、最初のAI出力は意味的には正しくてもSchemaのフィールド名へ厳密に従いませんでした。

v1は再現性のため変更せず残しています。

### v2

次を改善しています。

- トップレベルと13個のDecisionキーを固定
- 追加キーと別名フィールドを禁止
- 完全なJSONテンプレートを提示
- `1 Decision = 1判断`のAtomicityを指示
- 事実、提案、採用済み判断を区別
- 最新状態を優先
- `cancelled`を追加
- `reverted`と`cancelled`の違いを定義

v2はまだ同じSessionでAI抽出・人間評価していません。

## 6. 未評価・未決事項

次は未評価です。確認済み事実として扱わないでください。

- Decision Recall
- Decision Precision
- Rationale Accuracy
- Evidence Accuracyの人間による意味評価
- Status Accuracy
- Atomicity
- Hallucination件数
- `decisions.md`が人間に十分読みやすいか
- 将来のAIがDecision JSONを有効に再利用できるか
- Decision Schemaの最適性
- Decisionとimplementation eventの自動関連付け
- KiroやCopilotの履歴でも同じ方式が成立するか
- Chunkingが必要か
- 静的HTMLが人間向け表現として有効か

`supersedes_decision_id`、implementation evidence、chunking、HTMLは必要性を評価してから実装します。

## 7. 次に行う検証

優先順位は次のとおりです。

1. 人間が重要と覚えているDecisionを10〜15件挙げ、Gold Setとして固定する
2. v1の16件をGold Setと照合する
3. Recall / Precisionを算出する
4. Rationale / Evidence / Status / Atomicityを人間が評価する
5. Hallucination件数を数える
6. `decisions.md`の可読性を人間が評価する
7. 同じ入力をPrompt v2で一度だけ抽出し、v1と比較する

Gold SetをAI出力へ合わせて後から変更しないことが重要です。

## 8. 環境構築

Python 3.10以上を使用します。PowerShellのExecution Policyを変更する必要はありません。

```powershell
git clone https://github.com/soragaaoin-lang/plism.git
cd plism
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

## 9. 基本実行手順

### JSONL取り込み

```powershell
.\.venv\Scripts\python.exe -m chat_history_poc ingest C:\path\to\session.jsonl
```

### Analysis Bundle生成（Prompt v2）

```powershell
.\.venv\Scripts\python.exe -m chat_history_poc export-analysis <session-id>
```

v1 baselineを再現する場合:

```powershell
.\.venv\Scripts\python.exe -m chat_history_poc export-analysis <session-id> --prompt-version v1
```

AIへ渡すもの:

- `analysis_prompt.md`
- `analysis_session.json`
- `schemas/decision_analysis.schema.json`

AIから受け取るもの:

- JSONだけで構成された`decisions.json`

### Decision Import

```powershell
.\.venv\Scripts\python.exe -m chat_history_poc import-analysis <session-id> C:\path\to\decisions.json
```

v1結果の場合:

```powershell
.\.venv\Scripts\python.exe -m chat_history_poc import-analysis <session-id> C:\path\to\decisions.json --prompt-version v1
```

### Markdown生成

```powershell
.\.venv\Scripts\python.exe -m chat_history_poc render <session-id>
```

## 10. 成果物の役割

| ファイル | 役割 |
|---|---|
| `normalized_session.json` | 完全保存・監査用の正規化結果 |
| `normalization_report.json` | 全行分類と欠損確認 |
| `analysis_session.json` | AI分析用Projection |
| `analysis_prompt.md` | 抽出ルール |
| `conversation.md` | 人間による元会話確認 |
| `decisions.json` | 機械可読なDecision正本 |
| `decisions.md` | 人間向け表示 |

## 11. データの取扱い

次はGit管理対象外です。

- `history/`
- `data/*.db`
- `artifacts/<session-id>/`

これらにはチャット本文、ソースコード、パス、社内情報、秘密情報が含まれる可能性があります。会社PCへ移す場合は、会社の情報管理規程と持ち出し規程を確認してください。

公開GitHubリポジトリには実履歴、SQLite DB、生成済みDecisionをpushしないでください。会社データを利用する場合は、会社管理下のPrivate Repositoryまたは承認された保管場所を使用してください。

安全に移せない場合は、会社環境内のCodex/Kiro履歴から新しいSessionを取り込み、同じパイプラインを再実行してください。

## 12. 引継ぎ時に保持すべきもの

再現性のため、許可された安全な場所へ次をセットで保存します。

- 入力JSONLの識別情報とSHA-256
- 使用したPrompt version
- `analysis_session.json`
- AIが返した未修正のraw output
- Schema準拠後の`decisions.json`
- Gold Set
- 評価結果
- 使用したAI製品・モデル・実行日

raw outputはSchema変換版で上書きしないでください。

## 13. 事実ラベル

中間報告や引継ぎ資料では、必要に応じて次のラベルを使用します。

- `[共有済み]`: チーム内で共有・合意されたこと
- `[実装済み]`: コードとして存在すること
- `[検証済み]`: 実データまたはテストで確認したこと
- `[Baseline]`: AI抽出の未評価結果
- `[変更済み]`: 一度採用後、置き換えられたこと
- `[相談案]`: AIとの相談で出たが未合意の案
- `[未決]`: まだ判断されていないこと
- `[未評価]`: 実装・出力はあるが品質評価前のこと

