# plism PoC 引継ぎ書

最終更新: 2026-08-23

## 1. この文書の目的

この文書は、会社PCや別の作業者が `plism` を再開するときに、現在地、再現手順、評価上の注意、未完了作業を誤解なく引き継ぐための入口である。実験の詳しい時系列は [PROJECT_HISTORY.md](PROJECT_HISTORY.md) を参照する。

本PoCの目的は、AI駆動開発の長いチャット履歴から、後で再利用できる意思決定と要求を、元発言へ戻れるEvidence付きで復元できるか検証することである。完成した仕様書生成サービスや、AIが自動で正解を決めるシステムではない。

## 2. 現在の結論

### 技術成立性

PoCとして次は成立した。

- Codex Raw JSONLを全行保持して正規化できる。
- 開発会話、内部コンテキスト、制約、実装イベント、添付本文を分けられる。
- 長期会話をSectionへ分け、各SectionからDecision候補を抽出できる。
- MessageとAttachmentを型付きEvidenceとして検証できる。
- Section間の重複候補を絞り、統合後にlifecycleを再判定できる。
- Schemaの限定的な型崩れを、原文とEvidenceを変えずに救済できる。
- AI原本、評価値、Hashを分離保存し、失敗も上書きせず比較できる。

### 品質成立性

同じ開発用セッション内では大きく改善した。しかし一般化性能は未証明である。

> 技術成立性のPoCはほぼ完了している。精度・一般化のPoCを完了するには、現在のコードとPromptを凍結し、未見セッションで一度だけ盲検評価する必要がある。

7月26日の長期会話は、Prompt、GiNZA規則、Section処理、lifecycle処理を調整するために繰り返し使用した。以後これは **development set** であり、最終性能の根拠には使わない。

### 製品としての中心価値

主目的は、会話から仕様書一式を完全自動復元することではない。

> 会話に埋もれた重要な判断を、元のMessage／Attachmentへ戻れるEvidence付きDecision Recordとして残し、次の開発者やAIが全履歴を再読せず安全に作業を再開できるようにする。

Architecture以外の運用、業務、実験、評価、プロジェクト停止・再開もDecision typeで区別する。Requirement、実装記録、検証記録はDecision lifecycleと別軸である。AI提案だけを自動でacceptedにせず、不足情報はunknownまたはmissing informationとして残す。

専用画面で全候補を事前承認させる運用にはしない。Decision lifecycleとは別に、次のtrust levelを持たせ、実際の利用時に例外確認する。

| trust level | 意味 |
|---|---|
| `confirmed` | 人間の明示発言があり、RecordをEvidenceが直接支える |
| `inferred` | 複数発言や実装経緯から強く推定できるが明示確認はない |
| `candidate` | 提案／決定、適用範囲、現在状態のいずれかが曖昧 |

人間確認が必要なのは、関連Decisionが矛盾する、lifecycle不明、削除・金銭・セキュリティ・外部公開など高リスク、推定Recordを恒久根拠にする、要約とRaw Evidenceが一致しない場合である。PR mergeはコード受入れのEvidenceではあるが、全実装詳細を恒久Requirementとして承認した証拠とはみなさない。

## 3. 現在のパイプライン

```text
Codex Raw JSONL
  ↓ ingest / lossless normalization
Normalized Session（監査用・完全保持）
  ↓ analysis projection
Messages + Constraints + Implementation Events + Attachments
  ↓ sectioning
Section候補
  ↓ GiNZA・軽量規則
候補signal（答えではない）
  ↓ Section単位 Prompt v4 + Interpretation Notebook
Section Decision原本
  ↓ Schema / Evidence検証 + 限定的lossless repair
有効なSection Decision
  ↓ cross-section integration
統合Decision
  ↓ lifecycle review
最終status付きDecision
```

古い一括パイプラインも再現用に残している。

```text
Raw JSONL → Normalized Session → Analysis Projection → AI → decisions.json
         → Schema/Evidence validation → SQLite → decisions.md → conversation.md
```

## 4. 層ごとの責務

| 層・成果物 | 役割 |
|---|---|
| Raw JSONL | 変更しないSource of Truth |
| `normalized_session.json` | 全イベントを保持する監査用中間形式 |
| `normalization_report.json` | recognized / unknown / parse_error / silent dropの確認 |
| `conversation.md` | 人間がMessage Evidenceの本文を確認する表示 |
| `analysis_session.json` | AIへ渡す分析用Projection。完全保存層とは別物 |
| `normalized_attachments.jsonl` | 添付本文、親Message、Section、SHA-256の正規化結果 |
| Section index | 機能・PR・調査・運用単位の候補境界 |
| signal | request / acceptance / rejection / reason / uncertainty / alternativeの候補。正解ラベルではない |
| `decisions.raw.json` | AIの初回原本。修正・上書き禁止 |
| validated Decision | SchemaとEvidence存在検査を通った機械可読データ |
| integrated Decision | Section間の同義・分割・置換候補を統合した結果 |
| lifecycle Decision | 後続発言を見てstatusを再判定した結果 |
| trust level | lifecycleとは別に、Recordが明示確認か推定か候補かを表す |
| `decisions.md` | 人間向け表示。JSON正本から生成する |
| Gold / Negative Set | 人間がAI出力を見る前に固定する評価基準 |

重要原則は次の二つである。

1. 情報を捨てずに保存することと、AIへ全部読ませることは別である。
2. signal、Section名、Notebookは補助情報であり、DecisionやRequirementの正解ではない。

## 5. DecisionとRequirement

このリポジトリでは両者を混同しない。

| 概念 | 問い | 例 |
|---|---|---|
| Decision | なぜ、その案・実現方式・方針を選んだか | 非同期方式をやめて同期方式を採用する |
| Requirement | 条件の下でシステムがどう振る舞うべきか | 全ページ保存成功時だけ同期カーソルを更新する |

Requirement、ADR、作業制約、進捗報告、テスト結果も分ける。`implementation_status` と `verification_status` はRequirementそのものではなく、後段のReconciliation情報として扱う設計である。

## 6. 主要な検証結果

### 6.1 Lossless normalization

- 実Codex JSONL 2件、合計10,753行で全行分類を確認した。
- 主に使った8月1日セッションは8,306イベント。
- `recognized=8,306`、`unknown=0`、`parse_error=0`、`silently_dropped=0`。
- Analysis Projectionは484会話、1 constraint、237 implementation eventsになった。

### 6.2 Gmail Requirement v1（8月1日、開発用セット）

人間裁定済みGoldは44件。固定Sourceは35 Message、AI出力は48件。

| 指標 | 結果 |
|---|---:|
| strict Recall | 70.45% |
| partial=0.5 Recall | 84.09% |
| strict Precision | 60.42% |
| partial=0.5 Precision | 73.96% |
| Evidence ID存在 | 98/98（100%） |
| Evidence意味妥当性 | 96/98（97.96%） |
| Critical Hallucination | 0件 |
| Requirement / ADR・作業制約の型混同 | 6件 |
| `superseded` Recall | 0/1 |

Gold SHA-256:

`af347780f1823363eab3763e9f25aac66fa0b0b67521d314c03c191182364347`

AI原本 SHA-256:

`1e7f2cf7090cc3c5043a4ce69004d271bad9e5d78fddd0d0a31ca0fcb548cfda`

解釈: 主要仕様の発見よりも、Requirement / ADR / 作業制約の分類、条件の保持、時間的status統合がボトルネックだった。

### 6.3 7月26日長期会話の正規化とSectioning

| 項目 | 結果 |
|---|---:|
| 正規化Message | 969（human 188 / assistant 780 / AGENTS 1） |
| Section候補 | 41 |
| Attachment | 35 |
| 添付欠落 | 0 |
| Section未割当 | 0 |
| 検証エラー | 0 |

Section index SHA-256:

`89bb2ac5d3e297d0667facb9e429e6b8056a7dcef7a4fac7a1163b8991c18ba3`

Sectionは現在も `candidate_pending_human_adjudication` であり、正式なGoldではない。

### 6.4 Decision v2 → Projection v3

添付35件は正規化済みだったが、v2の `analysis_session.json` には1件も入っていなかった。Projection v3でAttachmentを正式Evidenceにした。

| 指標 | v2 | Projection v3 |
|---|---:|---:|
| Decision | 24 | 31 |
| Attachment入力 | 0 | 35 |
| 全41 Section参照 | 22/41 | 33/41 |
| 暫定target Section | 21/32 | 28/32 |
| status | accepted 24/24 | accepted 31/31 |
| Critical Hallucination | 0 | 0 |

Projection v3は旧未取得11 Section中10 Sectionを回復し、Attachment Evidence 20/20は意味的に妥当だった。一方で存在しないEvidence IDが1件あり、Atomicityは75.0%から67.74%へ悪化、status collapseは残った。

### 6.5 GiNZA signal単独比較

- 968 Message中485件へ1,782 signalを付与した。
- request 908、acceptance 110、rejection 217、reason 268、uncertainty 9、alternative 270。
- 暫定target Sectionは28/32から30/32へ改善。
- Evidence存在は100%になった。
- Why-notは19/31から13/35へ低下。
- 入力サイズは40.15%増加。
- statusは全件acceptedのまま。

したがってGiNZA signal v1単独は **保留**。候補検索には使えるが、signalを増やすだけでWhy/Why-notや状態遷移が改善するとは確認できなかった。

### 6.6 Prompt v4 / Notebook単独比較

- Prompt v4: AtomicityとWhy-not構造には改善候補があったが、Evidence存在、旧Decision維持、Section coverageの事前条件を満たさず **棄却**。
- Interpretation Notebook v1: Evidence存在、Atomicity、型混同、1件の状態遷移は改善したが、意味維持とSection coverageが悪化し **棄却**。
- Notebookの合成例がDecisionへ漏れた証拠は0件。

Promptや知識を足せば単純に良くなるわけではなく、長文一括入力の選択揺れが強いことが分かった。

### 6.7 Hybrid Section抽出

Section分割、signal候補検索、Section単位Prompt v4 + Notebook、Section間統合を組み合わせた。

| 指標 | Hybrid v1 |
|---|---:|
| AI raw Decision | 268 |
| 機械検証後 | 257 |
| 統合後 | 256 |
| 全41 Section coverage | 36/41（87.80%） |
| 暫定target coverage | 31/32（96.88%） |
| Evidence存在 | 746/746（100%） |
| status | accepted 236 / proposed 10 / superseded 10 |

固定40件サンプルの暫定人手評価:

| 指標 | 結果 |
|---|---:|
| 再利用可能Decision | 34/40（85.0%） |
| Atomicity | 33/40（82.5%） |
| Evidence意味支持 | 40/40（100%） |
| status時系列妥当 | 33/40（82.5%） |
| Critical / Minor Hallucination | 0 / 0 |

11件の除外原因は、未知Evidence 4件とSEC-012のSchema型崩れ7件だった。

### 6.8 Schema recovery + lifecycle review

SEC-012の `rationale` が文字列で返った7件を、文字列内容を変えず1要素配列へ包む限定修復で回復した。その後、統合後に残ったproposed 10件だけを、元Sectionと後続2 Sectionで再判定した。

| 指標 | Hybrid v1 | Recovery + lifecycle |
|---|---:|---:|
| 検証後Decision | 257 | 264 |
| 統合後Decision | 256 | 263 |
| 全41 Section coverage | 36/41 | 37/41（90.24%） |
| 暫定target coverage | 31/32 | 32/32（100%） |
| status accepted | 236 | 251 |
| status proposed | 10 | 1 |
| status superseded | 10 | 11 |
| 元Decision Evidence | 746/746 | 766/766 |
| lifecycle Evidence | 対象外 | 10/10 |

既知のstatus失敗7件はすべて修正された。さらに2件が後続の人間Evidenceによりacceptedへ変わったが、固定済み旧裁定とは不一致であるため、人間の再裁定が必要である。保守的に数えると固定40件のstatus妥当性は38/40（95%）。

最終 lifecycle Decision SHA-256:

`7dd46cb9a57d26148019e9d15ff2b751da26c87f1ea59b6e96c3e5a4d9922b6d`

## 7. 現在言えること／言えないこと

### 言えること

- 長い実Codex履歴を欠損なく保持し、分析用入力へ変換できる。
- Attachment欠落はProjection層の問題として切り分け、型付きEvidenceで回復できた。
- Section単位処理は一括入力より候補Section coverageを改善した。
- Evidence存在・意味追跡は安定しており、確認した実験でCritical Hallucinationは0件だった。
- 限定的Schema recoveryと独立lifecycle工程は、同じ開発用セッション上で既知の失敗を改善した。

### まだ言えないこと

- 未見の会話でも同じRecall / Precisionが出る。
- 263件すべてが再利用可能なDecisionである。
- Section 32/32が正式なDecision Recall 100%を意味する。
- 「後続2 Section」が最適なstatus判定窓である。
- 現在のPrompt、Notebook、signal、Section境界、Schemaが最適である。
- RequirementとDecisionの一般性能が証明済みである。
- 将来のAIや人間がこのデータを十分に再利用できる。

Section coverageは正式Goldに対するRecallではない。Hybridの40件評価も全263件の品質保証ではない。

## 8. 過学習・評価漏洩への扱い

過学習の危険はある。モデルを再学習したわけではないが、同じ7月26日会話を見ながらPrompt、規則、窓幅、統合方法を改善したため、評価設計上は開発セットへの適合が起きている。

比較的汎用と考えられる変更:

- Attachmentの正式Evidence化
- Message / Attachmentの型付きEvidence存在検査
- AI原本を変えない限定的scalar-to-array修復
- 抽出とlifecycle判定の工程分離

未見データで特に検証すべき変更:

- GiNZAの語彙・rule
- Section境界と候補検索閾値
- Prompt v4の分類規則
- Notebookの解釈規則
- 後続2 Sectionというstatus窓
- Section間統合候補の閾値

## 9. 次に行う作業

機能追加より先に、二段階で評価する。

### A. 抽出の一般化評価

1. 現在のコード、Prompt、Schema、Notebook、GiNZA ruleを凍結しHashを記録する。
2. lifecycle差異2件（ID-220、ID-225）を人間が裁定し、開発セットの記録を閉じる。
3. これまでPrompt調整に使っていない別セッションを一つ選ぶ。可能なら別機能・別プロジェクトにする。
4. AI出力を見る前に、人間がDecision Gold 10〜20件とNegative Setを固定する。
5. Source retrievalとDecision extractionを別指標として扱う。
6. 現在のパイプラインを一度だけ実行し、途中でPromptやGoldを変更しない。
7. 事前固定した指標で採点し、成功・失敗の両方を保存する。

暫定の合格目安:

| 指標 | 目安 |
|---|---:|
| Decision Recall | 70%以上 |
| Decision Precision | 75%以上 |
| Evidence Accuracy | 95%以上 |
| Status Accuracy | 80%以上 |
| Atomicity | 75%以上 |
| Critical Hallucination | 0件 |

この閾値は未見結果を見る前にチームで承認し、結果後に動かさない。

### B. 再利用価値のA/B評価

抽出の一般化とは別に、同じ実務タスクを独立した二つのAIタスクへ渡す。

- Full-context: 許可されたRaw会話全体
- ADR-context: 承認済みDecision RecordとEvidence link。必要なRawだけ追加可能

入力byte・推定token・可能ならcredit、完了時間、追加質問、重要発見、根拠のない主張、過去判断との矛盾、人間の盲検選好を記録する。これにより「抽出できるか」だけでなく「次の開発で本当に役立つか」を判定する。

## 10. 環境構築と確認

Python 3.10以上。通常パイプラインは標準ライブラリ中心、signal実験ではGiNZA / spaCyを使用する。

```powershell
git clone https://github.com/soragaaoin-lang/plism.git
cd plism
python -m venv .venv-ginza
.\.venv-ginza\Scripts\python.exe -m pip install -e ".[dev,signals]"
.\.venv-ginza\Scripts\python.exe -m pytest -q
.\.venv-ginza\Scripts\python.exe -m chat_history_poc --help
```

PowerShellで `Activate.ps1` が拒否されても、仮想環境を有効化せず `.venv-ginza\Scripts\python.exe` を直接使えばよい。

基本的なingestとBundle生成:

```powershell
.\.venv-ginza\Scripts\python.exe -m chat_history_poc ingest C:\path\to\session.jsonl
.\.venv-ginza\Scripts\python.exe -m chat_history_poc export-analysis <session-id>
```

Hybrid、integration、lifecycleの具体的な引数は、実装と同期しているルート [README.md](../README.md) とCLIの `--help` を正とする。

最新のローカル確認ではテストは45件成功した。

## 11. 重要な成果物

| 用途 | パス |
|---|---|
| Gmail Requirement v1評価 | `evaluation/requirement_v1/gmail_sync/` |
| 確定Requirement Gold | `artifacts/correct/gmail_sync_gold_requirements_v1.json` |
| 7月26日Sectioning | `evaluation/sectioning_v1/asset_management_long_session/` |
| Decision v2 baseline | `evaluation/decision_v2/asset_management_long_session/` |
| Projection v3比較 | `evaluation/decision_v3/asset_management_long_session/` |
| GiNZA比較 | `evaluation/signal_v1/asset_management_long_session/` |
| Prompt / Notebook比較 | `evaluation/knowledge_v1/asset_management_long_session/` |
| Hybrid v1評価 | `evaluation/decision_hybrid_v1/asset_management_long_session/` |
| Recovery / lifecycle比較 | `evaluation/decision_hybrid_recovery_v1/asset_management_long_session/` |
| 抽出Prompt | `prompts/` |
| JSON Schema | `schemas/` |
| 解釈Notebook | `knowledge/` |

主要Hash一覧は各評価ディレクトリの `BASELINE_HASHES.json`、`RUN_HASHES.json`、`FROZEN_INPUT_HASHES.json` を参照する。

## 12. Gitとデータの状態

2026-08-23時点で、Projection v3以降のコード、Prompt、Schema、評価資料には未commit・未pushの変更がある。作業ツリーには利用者が作った成果物も含まれるため、まとめて追加する前に公開可否を個別確認する。

公開GitHubへ原則としてpushしないもの:

- `history/` の実会話
- Raw JSONL
- SQLite DB
- 実会話本文を含む `artifacts/`
- 会社名、個人情報、Token、ローカルPath、未公開コードを含む成果物

公開候補:

- Source本文を含まない製品コード
- Prompt、Schema、テスト
- 匿名化・集計済み評価レポート
- この引継ぎ書

公開前に `git diff`、未追跡ファイル、秘密情報、`.gitignore` を確認する。現在の未commit変更を一括で捨てたり、Raw履歴を誤って追加したりしないこと。

## 13. 作業用Codexタスクの整理

実験で作成されたCodex UI上の作業タスクは整理済みである。

- Hybrid SECタスク 41件
- Integration clusterタスク 6件
- Hybrid評価タスク 1件

合計48件をアーカイブした。削除ではないため必要なら復元できる。

リポジトリ内では、不要なGuardian系履歴44 JSONL（約6.57 MB）を削除し、研究対象の履歴と通常の3ファイルは残した。

## 14. 再開時チェックリスト

- [ ] この文書と `PROJECT_HISTORY.md` を読む
- [ ] `git status` で未commit変更を確認する
- [ ] `.venv-ginza` または同等環境でテストを実行する
- [ ] Raw、AI原本、Gold、評価結果のHash一致を確認する
- [ ] 7月26日とGmail 35 Messageをdevelopment setとして明記する
- [ ] lifecycle差異2件を裁定する
- [ ] trust level導入は未見評価後のMVP設計として扱い、既存Schemaへ無断追加しない
- [ ] 未見セッションのGoldをAI実行前に固定する
- [ ] 一度だけblind runする
- [ ] 結果を見てGoldや閾値を変更しない
- [ ] 公開前に実会話・秘密情報を除外する

## 15. 現在の到達点を一文で

> plismは、Codexの長期Raw履歴と添付を欠損なく分析可能な形へ変換し、Section単位のAI抽出、Evidence検証、Section間統合、lifecycle再判定まで実行でき、同じ開発用会話では高い暫定coverageとEvidence妥当性を得たが、一般化性能は未見セッションの盲検評価待ちである。
