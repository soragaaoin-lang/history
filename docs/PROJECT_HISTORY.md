# AI駆動開発・意思決定履歴PoC プロジェクト履歴

最終更新: 2026-08-12

この文書は会話の逐語要約ではなく、PoCの状態遷移と、各段階で判明した問題を記録します。

## 1. 当初の課題

AI駆動開発では、実装方針、比較案、採用理由、却下理由、リスク、エラー対応などが長いチャット履歴へ埋もれます。その結果、開発後に「なぜこの実装になったか」を追跡しにくいという課題がありました。

当初は人間向け仕様書を作るのか、将来のAIが再利用する知識を作るのか、完全自動化するのか人間確認を挟むのかが明確でなく、完成像の議論が先行していました。

## 2. PoCへの具体化

議論は次のように具体化しました。

```text
抽象的な仕様書生成
  ↓
実際のAI開発履歴を材料にする
  ↓
Codexがローカルに保存するJSONLを入力にする
  ↓
まず欠損なく共通形式へ正規化する
  ↓
AIが意思決定候補を抽出できるか試す
  ↓
構造化JSONを正本とし、人間向けMarkdownを生成する
```

RAG、Vector DB、Webアプリ、マルチエージェント、完全自動仕様書生成はPoC対象外としました。

## 3. Lossless Normalization

最初の実装では、JSONL全行をRaw Eventとして保存し、各行を`recognized`、`unknown`、`parse_error`のいずれかへ分類する構成を作りました。

重要原則:

- 入力JSONLを変更しない
- 未知イベントを捨てない
- `silently_dropped = 0`
- Raw JSONL行まで追跡可能にする
- 同じ入力はSHA-256で重複登録しない

実Codex JSONL 2件、合計10,753行で全行分類を確認しました。主に評価対象として使用したSessionは8,306行です。

## 4. 内部コンテキスト問題の発見

最初の`normalized_session.json`には、実際の開発会話だけでなく次も大量に含まれていました。

- Developer/System instructions
- permissions
- skills
- plugins
- environment context
- AGENTS.md
- Tool Event

これは完全保存という目的には正しい一方、意思決定分析の入力としてはノイズになります。

ここで次の原則が明確になりました。

> 情報を捨てずに保存することと、AIへすべて読ませることは別である。

## 5. Analysis Projectionの追加

Normalized Sessionを変更せず、その上にAnalysis Projectionを追加しました。

```text
Raw JSONL
  ↓
Normalized Session（完全保存）
  ↓
Analysis Projection（分析用）
```

Projectionでは次を分離しました。

- 人間とAssistantの開発会話 → `messages`
- AGENTS.md由来の制約 → `constraints`
- file changeとcommand → `implementation_events`
- permissionsやenvironment context等 → 分析会話から除外

8,306イベントは、484会話、1制約、237実装イベントへ投影されました。元情報はNormalized Sessionに残っています。

## 6. AI Decision Extraction v1

Prompt v1では次を要求しました。

- Evidence必須
- 会話にない理由を推測しない
- 不足情報は`missing_information`へ記録
- 一時的な提案を確定判断として扱わない
- statusを付ける

一括入力に対し、AIは16件のDecisionを生成しました。

確認結果:

- Evidence参照: 62件
- ユニークEvidence: 54件
- 存在しないEvidence: 0件
- accepted: 13件
- superseded: 2件
- reverted: 1件

重要な方針転換を`superseded`として分離できたことは、仮説に対する前向きな観測です。ただし、人間Gold Setとの比較前なので精度・網羅性は未評価です。

## 7. v1で判明した問題

### 出力契約

最初のAI出力は意味的には正しかったものの、Schemaとは異なるフィールド名を使用しました。

例:

- `background`ではなく`context`が必要
- `alternatives_considered`ではなく`alternatives`が必要
- `adoption_reasons`ではなく`rationale`が必要
- `rejection_reasons`ではなく`rejected_alternatives`が必要

これは抽出能力と構造化出力契約を別に評価すべきことを示しました。

### Decisionの粒度

一部Decisionは、独立して参照され得る複数の判断を1レコードへまとめていました。人間向け要約としては読めても、AIが後から個別判断を検索する用途では大きすぎる可能性があります。

評価項目へAtomicityを追加する必要があると分かりました。

### Status体系

実装を元へ戻したわけではなく、企画や未完了実装を中止したケースが`reverted`になりました。

この実データから、`cancelled`が必要であり、`reverted`とは区別すべきことが分かりました。

## 8. Prompt v2

v1 baselineを保持したまま、Prompt v2を追加しました。

主な変更:

- トップレベルキーを`decisions`だけに固定
- 13個のDecisionキーを明記
- 追加キーと別名フィールドを禁止
- 完全なJSONテンプレートを提示
- Atomicityを指示
- `cancelled`を追加
- `reverted`との違いを定義
- Prompt versionをAnalysis Runへ記録

v2の抽出精度はまだ評価していません。

## 9. 現在の表現形式

役割は次のように分離しています。

```text
analysis_session.json → AI入力
decisions.json        → 機械可読な正本
decisions.md          → 人間向け表示
conversation.md       → Evidenceの元会話
```

静的HTMLは、人間が意思決定履歴を理解しやすいか検証する候補です。ただし、Gold SetとMarkdown可読性評価より先には実装しません。

## 10. 現在の評価段階

現在確認できたのは次です。

> 長いCodex履歴を欠損なく正規化し、内部コンテキストを分離したうえで、AIが実在Evidence付きの主要な意思決定候補を生成できる。

まだ確認できていないのは次です。

> AIが重要Decisionを十分なRecallとPrecisionで網羅し、理由・状態・粒度を正しく抽出できる。

次は機能追加よりも、人間Gold Setによる評価を優先します。

## 11. 主要Git履歴

| Commit | 内容 |
|---|---|
| `0b466ff` | 正規化PoCの初期実装 |
| `f8ccbe7` | Python 3.10対応 |
| `12b0ffb` | pytest一時領域対応 |
| `f1056fc` | pytest ACL競合回避 |
| `3a665d9` | editable install metadata除外 |
| `6166aad` | GitHub初期コミット履歴の統合 |
| `265618b` | Analysis Projection追加 |
| `e0ba792` | Decision Extraction Prompt v2追加 |

Repository: <https://github.com/soragaaoin-lang/plism>

