# AI駆動開発チャット履歴再利用PoC

Codexがローカルに保存したJSONL会話履歴を共通形式へ正規化し、設計・実装上の意思決定候補と元会話の根拠を追跡できるか検証するPoCです。入力JSONLは変更せずSource of Truthとして扱い、全行を `recognized`、`unknown`、`parse_error` のいずれかに分類します。

引継ぎ・再開時は次を参照してください。

- [引継ぎ書](docs/HANDOFF.md)
- [プロジェクト履歴](docs/PROJECT_HISTORY.md)

## Architecture

```text
Codex JSONL → Raw Event → Codex Adapter → Normalized Event → SQLite
                                                         ├→ conversation.md
                                                         └→ Analysis Projection
                                                              └→ analysis bundle
                                                              ↓ human-mediated AI
                                                         decisions.json
                                                              ↓ validation
                                                         decisions.md
```

AI呼び出しはCoreから分離されています。初期実装の `FileExchangeAnalysisRunner` はファイル交換だけを担当し、外部APIへ履歴を送信しません。

## Setup

Python 3.10以上を使用します。実行時依存は標準ライブラリだけです。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
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
