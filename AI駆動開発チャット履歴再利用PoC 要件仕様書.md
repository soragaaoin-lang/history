# AI駆動開発チャット履歴再利用PoC 要件仕様書

## 1. 背景

AI駆動開発では、ユーザーとAIの対話の中で以下のような情報が発生する。

- 実装方針
- 設計上の判断
- 比較した選択肢
- 採用理由
- 却下理由
- リスク
- エラーと修正方針
- 将来的な見直し条件

しかし、これらの情報は長いチャット履歴の中に埋もれやすく、開発終了後に「なぜこの実装になったのか」を追跡することが難しい。

また、チャット履歴自体に必要な情報が残っていない場合や、履歴を別形式へ変換する過程で情報が欠落する可能性もある。

本PoCでは、AI駆動開発ツールがローカルに保存する会話履歴を取得し、再利用可能な共通形式へ正規化したうえで、AIによって設計・実装上の意思決定候補を抽出できるかを検証する。

最初の対象としてCodexのJSONL形式の会話履歴を使用する。

将来的にはKiroなど他のAI駆動開発ツールの履歴にも対応可能な構成とする。

---

# 2. PoCの目的

本PoCの目的は以下の3点である。

### 2.1 会話履歴の再利用可能化

CodexのJSONL履歴を、特定ツールの内部形式に依存しない共通形式へ正規化する。

### 2.2 意思決定情報の抽出

正規化した会話履歴からAIを利用して以下を抽出する。

- 何を決めたか
- 背景
- 比較した案
- 採用理由
- 却下理由
- リスク
- 見直し条件
- 根拠となる元会話
- 不足している情報

### 2.3 情報欠損の検証

以下を区別できるようにする。

- 元の会話履歴にそもそも存在しなかった情報
- 正規化処理で認識できなかった情報
- AIが抽出できなかった情報

PoCでは欠損問題を完全に解決することよりも、どこで情報が失われたかを追跡可能にすることを優先する。

---

# 3. PoCで検証したい問い

本PoCでは以下を検証する。

1. AI駆動開発の会話履歴だけから、設計上の意思決定を抽出できるか。
2. 「なぜその実装になったか」まで復元できるか。
3. 比較案や却下理由まで取得できるか。
4. AIが抽出した情報について元会話まで追跡できるか。
5. 人間が読むために必要な情報と、AIが再利用するために必要な情報にどの程度共通項があるか。
6. 会話履歴そのものに不足している情報は何か。

---

# 4. 対象範囲

## 4.1 PoC必須範囲

以下を実装する。

```text
Codex JSONL
    ↓
Rawデータ保存
    ↓
共通形式へ正規化
    ↓
AI分析用データ生成
    ↓
AIによる意思決定候補抽出
    ↓
構造化JSON
    ↓
Markdown生成
    ↓
元会話への追跡
```

## 4.2 拡張範囲

余力があれば以下を実装する。

- 静的HTML表示
- Codex CLIによるAI分析の自動実行
- 人間による承認・却下状態の記録

## 4.3 今回対象外

以下はPoCでは実装しない。

- Webアプリ
- RAG
- ベクトルDB
- チャット形式での検索
- Skills自動生成
- チーム判断基準の自動学習
- Git差分との照合
- GitHub連携
- 完全自動仕様書生成
- Kiro専用Parser
- マルチエージェント
- 大規模な認証・ユーザー管理

---

# 5. 入力

## 5.1 入力形式

Codexが保存したJSONLファイル。

例：

```text
C:\Users\muto1\.codex\sessions\2026\07\...\*.jsonl
```

ただしパスをプログラムへハードコードしてはならない。

CLI引数としてファイルまたはディレクトリを指定可能にする。

## 5.2 原本の扱い

JSONLファイルを原本とする。

プログラムから原本を書き換えてはならない。

入力ファイルについてSHA-256を計算し、どの原本から生成されたデータか識別できるようにする。

---

# 6. 正規化要件

Codex固有のJSONL形式を以下の共通モデルへ変換する。

## NormalizedSession

```json
{
  "session_id": "session-001",
  "source_type": "codex",
  "source_file": "...",
  "source_sha256": "...",
  "events": []
}
```

## NormalizedEvent

最低限以下を保持する。

```json
{
  "event_id": "evt-000001",
  "source_line": 1,
  "source_event_type": "original event type",
  "kind": "message",
  "role": "user",
  "timestamp": null,
  "content": "message text",
  "raw_event_id": "raw-000001"
}
```

`kind`には最低限以下を許容する。

```text
message
tool
file_change
command
metadata
unknown
```

Codex形式に存在するイベントをすべてmessageへ無理に変換してはならない。

認識できないイベントは、

```text
kind = unknown
```

として保存する。

---

# 7. 情報欠損防止要件

## 7.1 Silent Drop禁止

入力されたJSONLの行を理由なく破棄してはならない。

すべての行について以下のいずれかに分類する。

```text
recognized
unknown
parse_error
```

## 7.2 Normalization Report

正規化終了時に以下を出力する。

```json
{
  "total_lines": 120,
  "parsed_lines": 120,
  "recognized_events": 104,
  "unknown_events": 16,
  "parse_errors": 0,
  "silently_dropped": 0
}
```

`silently_dropped`は必ず0であること。

## 7.3 Raw情報保持

DBには最低限以下を保存する。

- 元ファイル
- 元行番号
- Raw JSON文字列
- parse成否
- 正規化後Event ID

これにより、正規化後のデータから元JSONLへ追跡できること。

---

# 8. AI分析要件

AIは正規化済み会話から「意思決定候補」を抽出する。

Pythonコード自体が意思決定理由を推測してはならない。

AIへ渡すデータとプロンプトは明示的にファイルとして保存する。

例：

```text
work/
└─ session-001/
   ├─ normalized_session.json
   ├─ analysis_prompt.md
   └─ decisions.json
```

---

# 9. 意思決定データモデル

AIの出力はMarkdownではなく、最初に構造化JSONとする。

```json
{
  "decisions": [
    {
      "decision_id": "D-001",
      "title": "データ保存方式",
      "decision": "SQLiteを採用する",
      "context": "ローカルで動作する小規模アプリ",
      "alternatives": [
        "JSON",
        "SQLite"
      ],
      "rationale": [
        "検索や更新が容易"
      ],
      "rejected_alternatives": [
        {
          "alternative": "JSON",
          "reason": "更新処理が複雑になるため"
        }
      ],
      "risks": [
        "複数ユーザー利用には向かない"
      ],
      "revisit_conditions": [
        "複数ユーザー対応が必要になった場合"
      ],
      "evidence_message_ids": [
        "msg-000023",
        "msg-000024"
      ],
      "confidence": "high",
      "missing_information": []
    }
  ]
}
```

---

# 10. AI抽出ルール

AIは以下を厳守する。

1. 元会話に存在しない理由を推測して追加しない。
2. 不明な情報は`missing_information`へ記録する。
3. 各意思決定には必ず根拠となるMessage IDを付ける。
4. 一時的なアイデアを確定した意思決定として扱わない。
5. 撤回された判断は最終決定と区別する。
6. 複数案が存在した場合は可能な限り保持する。
7. 確信度をhigh / medium / lowで記録する。
8. 根拠が不足する場合はlowとする。
9. AI自身がもっともらしい背景を補完してはならない。

---

# 11. Markdown出力

Python側で`decisions.json`からMarkdownを生成する。

例：

```markdown
# 意思決定一覧

## D-001 データ保存方式

### 決定

SQLiteを採用する。

### 背景

ローカルで動作する小規模アプリ。

### 比較案

- JSON
- SQLite

### 採用理由

- 検索や更新が容易

### 却下理由

- JSON
  - 更新処理が複雑になるため

### リスク

- 複数ユーザー利用には向かない

### 見直し条件

- 複数ユーザー対応が必要になった場合

### 不足情報

なし

### 根拠

- [msg-000023](conversation.md#msg-000023)
- [msg-000024](conversation.md#msg-000024)
```

---

# 12. Conversation Markdown

正規化済み会話から、人間が確認できる`conversation.md`も生成する。

```markdown
# Conversation

### msg-000023

**User**

保存先はJSONでいい？

Source: line 84

---

### msg-000024

**Assistant**

検索や更新を考えるとSQLiteも候補になります。

Source: line 85
```

意思決定Markdownから該当箇所へリンクできること。

---

# 13. SQLite

SQLiteは検索・関連付け用データストアとして利用する。

JSONL原本を置き換えるものではない。

最低限以下のテーブルを持つ。

```text
sessions
raw_events
messages
analysis_runs
decisions
decision_evidence
```

---

# 14. AI実行方法

PoCではAI実行方法を固定しない。

以下のインターフェースとして分離する。

```text
AnalysisRunner
```

初期実装では、

```text
FileExchangeAnalysisRunner
```

を実装する。

処理：

```text
normalized_session.json
+
analysis_prompt.md
↓
人間がCodex / Kiro / Copilotなどへ入力
↓
decisions.json
↓
Pythonへimport
```

将来的に、

```text
CodexCliAnalysisRunner
KiroAnalysisRunner
OtherAnalysisRunner
```

を追加可能とする。

---

# 15. CLI

最低限以下を提供する。

```text
python -m chat_history_poc ingest <jsonl>
```

JSONLを読み込み、Raw保存・正規化・DB登録する。

```text
python -m chat_history_poc export-analysis <session-id>
```

AI分析用ファイルを生成する。

```text
python -m chat_history_poc import-analysis <session-id> <decisions.json>
```

AI結果を検証してDBへ登録する。

```text
python -m chat_history_poc render <session-id>
```

Markdownを生成する。

任意：

```text
python -m chat_history_poc render-html <session-id>
```

---

# 16. バリデーション

AIが返した`evidence_message_ids`について、存在しないMessage IDを指定した場合はエラーとする。

例：

```text
DECISION_EVIDENCE_NOT_FOUND
```

不正なJSONや必須フィールド欠落も受理しない。

---

# 17. 非機能要件

### ローカル優先

AI分析を除くすべての処理はローカルで完結可能とする。

### 原本非破壊

入力JSONLを変更しない。

### 再実行可能

同じJSONLを複数回取り込んでも同一データを重複生成しない。

### 可観測性

処理件数、Unknown件数、エラー件数をログへ出力する。

### テスト可能性

JSONL Adapter、正規化、AIレスポンス検証、Markdown生成を独立してテスト可能とする。

### 拡張性

Codex固有処理はAdapterへ閉じ込める。

Kiro対応時にCoreロジックを変更しない構成を目標とする。

---

# 18. セキュリティ

チャット履歴には以下が含まれる可能性がある。

- ソースコード
- ファイルパス
- 社内情報
- APIキー等の秘密情報

そのためPoCでは外部APIへの自動送信をデフォルトで行わない。

AIへ履歴を渡す操作は明示的に行う。

認証情報そのものをDB、ログ、成果物へコピーしない。

---

# 19. 完成条件

PoC完成条件は以下とする。

- [ ] 実際のCodex JSONLを1件以上読み込める
- [ ] JSONL全行についてrecognized / unknown / parse_errorのいずれかに分類できる
- [ ] silently_droppedが0になる
- [ ] 共通形式へ正規化できる
- [ ] conversation.mdを生成できる
- [ ] AI分析用データを生成できる
- [ ] AI結果JSONをバリデーションできる
- [ ] 意思決定候補を3件程度抽出できる
- [ ] decisions.mdを生成できる
- [ ] 各意思決定から元会話へ追跡できる
- [ ] 同じ入力を再実行してもDB上で重複しない
- [ ] Unknown Eventがあっても処理全体が停止しない
- [ ] 基本テストがすべて成功する

HTML生成はPoC必須完成条件には含めない。

---

# 20. PoC終了後の評価

PoC終了後、実際の会話履歴について人間でも意思決定を抽出し、AI出力と比較する。

確認項目：

- 意思決定の抽出率
- 採用理由の抽出率
- 比較案の抽出率
- 却下理由の抽出率
- AIによる事実でない補完の件数
- 元会話へ追跡できた割合
- 会話履歴自体に情報が存在しなかった割合

この結果をもとに、次Phaseで以下を判断する。

- 人向け仕様書として発展させるか
- AI向け知識として発展させるか
- 共通データモデルを利用して両方へ展開するか
- Git差分など別情報源を追加する必要があるか