# AI駆動開発チャット履歴再利用PoC 技術設計書

## 1. 基本設計方針

以下を設計原則とする。

```text
Rawは捨てない
CoreはCodexに依存しない
AIに直接Markdownを書かせない
AI出力には必ずEvidenceを持たせる
不足情報をAIに推測させない
表示形式と保存形式を分離する
```

---

# 2. 全体アーキテクチャ

```text
                 ┌────────────────────┐
                 │ Codex JSONL        │
                 │ Raw Source         │
                 └─────────┬──────────┘
                           │
                           ▼
                 ┌────────────────────┐
                 │ CodexJsonlAdapter  │
                 └─────────┬──────────┘
                           │
                           ▼
                 ┌────────────────────┐
                 │ NormalizedSession  │
                 │ NormalizedEvent    │
                 └─────────┬──────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
       ┌────────────┐ ┌───────────┐ ┌─────────────┐
       │ SQLite     │ │conversation│ │Analysis     │
       │            │ │.md         │ │Bundle       │
       └────────────┘ └───────────┘ └──────┬──────┘
                                           │
                                           ▼
                                  ┌────────────────┐
                                  │ AI             │
                                  │ Decision       │
                                  │ Extraction     │
                                  └───────┬────────┘
                                          │
                                          ▼
                                  ┌────────────────┐
                                  │ decisions.json │
                                  └───────┬────────┘
                                          │
                             Validation   │
                                          ▼
                                  ┌────────────────┐
                                  │ SQLite         │
                                  │ Decisions      │
                                  └───────┬────────┘
                                          │
                                          ▼
                                  ┌────────────────┐
                                  │ decisions.md   │
                                  └────────────────┘
```

---

# 3. ディレクトリ構成

```text
chat-history-poc/
├─ pyproject.toml
├─ README.md
├─ .gitignore
│
├─ src/
│  └─ chat_history_poc/
│     ├─ __init__.py
│     ├─ __main__.py
│     ├─ cli.py
│     │
│     ├─ domain/
│     │  ├─ models.py
│     │  └─ errors.py
│     │
│     ├─ adapters/
│     │  ├─ base.py
│     │  └─ codex_jsonl.py
│     │
│     ├─ repositories/
│     │  └─ sqlite_repository.py
│     │
│     ├─ services/
│     │  ├─ ingest_service.py
│     │  ├─ normalization_service.py
│     │  ├─ analysis_bundle_service.py
│     │  ├─ analysis_import_service.py
│     │  └─ render_service.py
│     │
│     └─ renderers/
│        ├─ markdown_renderer.py
│        └─ html_renderer.py
│
├─ prompts/
│  └─ decision_extraction_v1.md
│
├─ schemas/
│  └─ decision_analysis.schema.json
│
├─ templates/
│  ├─ conversation.md.j2
│  ├─ decisions.md.j2
│  └─ decisions.html.j2
│
├─ tests/
│  ├─ fixtures/
│  │  └─ sample_codex_session.jsonl
│  ├─ test_codex_adapter.py
│  ├─ test_ingest.py
│  ├─ test_analysis_import.py
│  └─ test_markdown_renderer.py
│
├─ data/
│  └─ .gitkeep
│
└─ artifacts/
   └─ .gitkeep
```

HTMLはStretch Goalのため、初期実装では空実装でも構わない。

---

# 4. Domain Model

## RawEvent

```python
RawEvent(
    id: str,
    session_id: str,
    source_line: int,
    raw_text: str,
    parsed_ok: bool,
    event_type: str | None,
    timestamp: str | None,
)
```

---

## NormalizedEvent

```python
NormalizedEvent(
    id: str,
    session_id: str,
    raw_event_id: str,
    source_line: int,
    source_event_type: str | None,
    kind: str,
    role: str | None,
    timestamp: str | None,
    content: str | None,
)
```

`kind`:

```text
message
tool
file_change
command
metadata
unknown
parse_error
```

---

## DecisionCandidate

```python
DecisionCandidate(
    decision_id: str,
    title: str,
    decision: str,
    context: str | None,
    alternatives: list[str],
    rationale: list[str],
    rejected_alternatives: list[RejectedAlternative],
    risks: list[str],
    revisit_conditions: list[str],
    evidence_message_ids: list[str],
    confidence: Literal["high", "medium", "low"],
    missing_information: list[str],
)
```

---

# 5. ID生成

IDは再実行しても同じ値になるよう決定的に生成する。

例：

```text
session_id
= SHA256(source_file_hash)[0:16]

raw_event_id
= session_id + "-raw-" + source_line

message_id
= session_id + "-msg-" + source_line
```

Random UUIDだけに依存しない。

---

# 6. JSONL Parser

## 処理

```text
for each line:
    raw_text保持
        ↓
    json.loads
        ↓
 成功             失敗
   │                │
   ▼                ▼
event type解析    parse_error
   │
   ▼
既知？
│    │
yes  no
│    │
▼    ▼
normalize unknown
```

Parse ErrorやUnknown Eventがあっても他行の処理は継続する。

---

# 7. CodexJsonlAdapter

Codex固有のフィールド解釈はすべてこのクラスへ閉じ込める。

```python
class SessionAdapter(Protocol):

    def can_handle(self, raw: dict) -> bool:
        ...

    def normalize(
        self,
        raw_event: RawEvent,
    ) -> NormalizedEvent:
        ...
```

Codex以外の対応では、

```text
KiroSessionAdapter
CopilotSessionAdapter
```

等を追加する。

Core Serviceを変更しない。

---

# 8. DB設計

SQLiteを使用する。

## sessions

```text
id PK
source_type
source_file
source_sha256 UNIQUE
created_at
normalized_at
```

## raw_events

```text
id PK
session_id FK
source_line
raw_text
parsed_ok
event_type
timestamp

UNIQUE(session_id, source_line)
```

## messages

```text
id PK
session_id FK
raw_event_id FK
source_line
role
kind
content
timestamp
```

## analysis_runs

```text
id PK
session_id FK
prompt_version
runner_type
status
created_at
completed_at
```

## decisions

```text
id PK
analysis_run_id FK
session_id FK
title
decision
context
confidence
status
raw_analysis_json
```

`status`:

```text
candidate
approved
edited
rejected
```

PoCではcandidateのみでもよい。

## decision_evidence

```text
decision_id FK
message_id FK

PRIMARY KEY(decision_id, message_id)
```

---

# 9. Idempotency

同じ原本を再度取り込んでも重複しない。

`source_sha256`を使って既存Sessionを判定する。

既存の場合は、

```text
already_ingested
```

として終了するか、明示的な`--force`のみ再構築する。

---

# 10. Analysis Bundle

AI分析前に以下を生成する。

```text
artifacts/
└─ <session-id>/
   ├─ normalized_session.json
   ├─ conversation.md
   ├─ normalization_report.json
   ├─ analysis_prompt.md
   └─ decisions.json
```

最初の4ファイルをPythonが生成する。

`decisions.json`をAIが生成する。

---

# 11. AI Runner Interface

```python
class AnalysisRunner(Protocol):

    def analyze(
        self,
        session_id: str,
        normalized_path: Path,
        prompt_path: Path,
    ) -> Path:
        ...
```

初期実装：

```text
FileExchangeAnalysisRunner
```

責務：

AIに渡すファイルを生成するところまで。

AI呼び出しそのものは行わない。

---

# 12. 将来のCodex CLI自動化

オプション機能として、

```text
CodexCliAnalysisRunner
```

を実装可能とする。

Codex CLIは非対話実行とJSONL出力をサポートしているため、将来的にはスクリプトからAI処理を接続可能である。

ただしPoCのCore機能はCodex CLIが存在しなくても動作すること。

---

# 13. Decision JSON Validation

JSON SchemaまたはPydanticを使用する。

以下を検証する。

- 必須フィールド
- confidence
- evidence_message_ids
- 重複ID
- Message IDの存在
- 空のdecision
- 不正な型

存在しないMessage IDを指定しているAI結果は受理しない。

---

# 14. Evidence Tracking

重要。

AIの判断そのものを信用するのではなく、

```text
Decision
↓
Evidence message
↓
Normalized event
↓
Raw event
↓
JSONL line
```

まで追跡可能にする。

---

# 15. Markdown Renderer

RendererはDBまたはDecision Modelから表示用Markdownを生成する。

AIにMarkdown生成を任せない。

これにより、

```text
同じDecision JSON
├─ Markdown
├─ HTML
└─ 将来のAI向け出力
```

を生成可能とする。

---

# 16. HTML Stretch Goal

実装する場合は静的HTMLのみとする。

Flask、FastAPI等のWebサーバーは導入しない。

表示内容：

- Session情報
- Decision一覧
- Confidence
- Missing Information
- Evidence
- 元会話

Evidenceをクリックすると該当会話へ移動する。

---

# 17. Logging

最低限以下を出力する。

```text
INFO source file
INFO source hash
INFO total lines
INFO parsed events
INFO normalized messages
WARNING unknown events
WARNING parse errors
INFO generated artifact paths
```

Rawの機密内容そのものを通常ログへ出さない。

---

# 18. テスト設計

## Parser

- 正常JSONL
- Unknown event
- 不正JSON
- 空行
- Unicode日本語
- 長文

## Idempotency

同じファイルを2回importしてもDB件数が増えない。

## Loss Detection

```text
入力行数
=
recognized
+ unknown
+ parse_error
```

となること。

## Analysis Validation

存在しないEvidence IDを拒否。

## Renderer

DecisionとEvidenceリンクがMarkdownへ出力される。

---

# 19. 使用ライブラリ

可能な限り依存を少なくする。

推奨：

```text
Python >= 3.11
pydantic >= 2
jinja2
pytest
```

SQLite、JSON、hashlib、argparse、loggingは標準ライブラリを使用する。

CLIフレームワークはPoCでは不要。

---

# 20. 実装順序

### Phase 1

Project skeleton

### Phase 2

Raw JSONL ingest

### Phase 3

CodexJsonlAdapter

### Phase 4

SQLite保存

### Phase 5

conversation.md / normalization_report

### Phase 6

AI analysis bundle

### Phase 7

decisions.json validation

### Phase 8

decisions.md

### Phase 9

Integration test

### Phase 10

HTML Stretch Goal

---

# 21. PoCで重要視すること

コード量より以下を優先する。

```text
Traceability
Data preservation
Simple architecture
Reproducibility
Testability
```

複雑な抽象化や将来機能を先取りしない。

ただし、

```text
Codex-specific input
↓
Common model
```

の境界だけは明確にする。