# Plism プロジェクト履歴

最終更新: 2026-08-16

この文書は会話の逐語要約ではなく、プロジェクトの目的、実験、失敗、方針転換を記録します。現在の判断は[引継ぎ書](HANDOFF.md)を参照してください。

初期PoCは公開リポジトリにあります。Projection v3以降の実験コード、評価資料、実会話Artifactsはローカル未公開であり、この履歴には確認済み結果だけを記載しています。

## 1. 出発点

AI駆動開発では、実装方針、比較案、採用・却下理由、エラー対応が長いチャットへ埋もれます。次の作業で履歴全体をAIへ再読させるとcreditを消費し、人間も「なぜこの実装なのか」を追跡できません。

最初の仮説は、会話を保存し、重要な判断をADRとして整理し、ADRから根拠となる生の発言へ移動できれば、履歴を再利用できるというものでした。

## 2. 初期PoC

対象をCodex JSONLに絞り、次を実装しました。

```text
Raw JSONL
  -> lossless normalization
  -> SQLite
  -> conversation.md
  -> analysis projection
  -> AI decision extraction
  -> schema/evidence validation
  -> decisions.md
```

重要原則は、入力を変更しない、未知イベントを捨てない、Raw行まで追跡可能にする、同じ入力をSHA-256で重複登録しないことでした。

## 3. 完全保存とAI入力の分離

正規化結果にはDeveloper/System instructions、permissions、skills、plugins、environment、AGENTS.md、tool eventも含まれます。監査には必要ですがDecision抽出にはノイズでした。

ここで次を分離しました。

- Raw / Normalized Session: 完全保存
- Analysis Projection: AIへ渡す対象
- constraints: 作業・環境制約
- implementation events: file changeとcommand

学びは「保存する情報」と「毎回AIへ読ませる情報」は同じではない、ということです。

## 4. Decision抽出baseline

一括入力からEvidence付きDecisionを抽出し、存在しないMessage IDを検証で拒否できました。一方で、Schemaの別名、複数判断の混在、statusの誤分類が見つかりました。

Prompt v2ではJSON契約、Atomicity、`cancelled`と`reverted`の区別を強化しました。ただしPromptを細かくするだけでは、情報がAI入力へ届いていない問題を解決できません。

## 5. Requirement抽出実験

Gmail差分同期の35 Messageから、人間裁定後44件のGold Requirementを作りました。主要な現行仕様は多く取得でき、Evidenceの意味妥当性も高い一方、RequirementへADR・SQLite実現方式・作業scope・操作制約を混在させ、廃止案の`superseded`を取得できませんでした。

この結果から、中心課題を単純な検索不足ではなく次の二つと捉えました。

1. Requirement、Decision、作業制約などの分類
2. 時系列を通じたproposed、accepted、superseded等の状態統合

この35 Messageは改善へ使用したdevelopment setであり、未見性能の主張には使いません。

## 6. 長期会話とAttachment欠落

968 Messageの長期会話baselineでは24 Decision、62 Evidence参照、欠落ID 0でしたが、すべて`accepted`で、Attachment本文がProjectionに存在しませんでした。

抽出器へ渡された範囲のEvidenceは妥当でも、Raw履歴から必要情報を届けるend-to-end completenessが不足していました。これを受けてProjection v3を追加し、35 Attachmentを独立Evidenceとして保持しました。

Projection v3ではSection Coverageが53.66%から80.49%へ改善し、Attachment Evidence 20件はすべて意味的に妥当でした。一方、Atomicityは悪化し、lifecycle遷移は0/4のまま、旧Decision維持率も58.33%でした。

学びは、Projection改善はRecallの前提になるが、それだけで分類、状態、安定性は解決しないことです。

## 7. Section単位抽出

実際の長い履歴を想定し、会話を41 Sectionへ分けて局所抽出する実験を行いました。局所的な情報回収は増えましたが、253 Decision候補が生まれました。

31,020 pairを決定的な規則で58候補、10 clusterまで絞り込みましたが、今度はSection間の重複・親子・lifecycle統合が新しい大問題になりました。

独立AIへ10 clusterの関係判定を依頼した結果はvalid 0件でした。7件はinvalid JSON、3件はDecision ID形式の不一致です。ここで、局所指標を上げる修正を続けても製品価値へ近づかず、評価設計自体に過適合する危険を認識しました。

## 8. 方針転換

評価を精密化し続ける方針を止め、最初の目的へ戻りました。

旧方向:

- Requirement、Decision、Attachment、Section、統合関係、実装状態、テスト状態を包括的に復元する
- Goldと細かな損失関数を増やして抽出器を最適化する

現在方向:

- 会話に埋もれた重要判断をEvidence付きDecision Recordとして残す
- 採用だけでなく却下、撤回、停止理由を残す
- trust levelを付け、曖昧・矛盾・高リスクな判断だけを利用時に人間へ確認する
- 次の作業では関連Decisionだけを読み、Rawは必要時に開く
- Full-contextとADR-contextの実務A/B比較で価値を測る

Requirement、USDM、UML、テスト計画の自動生成は主機能から外しました。

## 9. 第三者視点によるADR再利用の観測

チーム開発経験者としてDecision資料を評価するようAIへ依頼したところ、技術判断の堅実さだけでなく、次を指摘できました。

- scopeの拡大
- ローカル用途に対する過剰な非同期・lease設計
- 外部provider contract testの遅れ
- 「何を作らないか」「いつ止めるか」の弱さ
- Architecture、Operational、Domain、Experiment、Evaluationの混在
- project closureを独立判断として残す必要

これは、Decision Recordが単なる記録ではなく、次の開発者によるプロジェクト診断と再開判断に利用できる可能性を示しました。

ただし、点数のrubric、発見ごとのEvidence対応、Rawとの盲検比較がないため正式評価ではありません。次は同じ実務タスクをFull-contextとADR-contextで比較します。

## 10. 現在の製品境界

PlismのMVPは次です。

```text
complete raw archive
  -> message/attachment evidence
  -> decision candidates and source dispositions
  -> trust level付きreusable ADR catalog
  -> confirmation on exception
  -> click-through raw evidence
```

Decision typeはArchitectureに限定せず、operational、domain、experiment、evaluation、project governanceを区別します。UIではArchitecture subsetをADRとして表示できます。

当初は人間が全候補を承認してから利用する案でした。しかし、独立したレビュー作業は継続利用の障壁になります。そこで`confirmed`、`inferred`、`candidate`をlifecycleとは別に保持し、通常は自動生成結果をそのまま参照可能にします。人間の介入は、矛盾、状態不明、高リスク、Evidence不一致が実際の作業で問題になる時だけ要求します。

## 11. 失敗から残す原則

- 情報到達率と抽出精度を分ける。
- Evidence IDの存在と意味妥当性を分ける。
- Decision lifecycleとimplementation/verification statusを分ける。
- 人間のmerge承認を恒久Requirement承認とみなさない。
- AI単独提案をacceptedにしない。
- 全件の事前承認を要求せず、確認済みとAI推定を同じ扱いにしない。
- 採用案だけでなく却下案と停止理由を残す。
- 分割で候補を増やす前に、後段の統合コストを見積もる。
- 外部サービスは大規模実装前に最小contract testを行う。
- 評価指標の改善より、利用者が次の作業を安全に始められるかを優先する。
- Raw、Gold、AI raw outputを上書きしない。

## 12. 次の実験

同じタスクを次の二条件で実施します。

- Full-context: 許可された会話履歴全体
- ADR-context: ADR catalogとEvidenceリンク。必要なRawだけ追加

token・credit、時間、質問回数、重要発見、誤認、矛盾、根拠のない主張、人間の盲検選好を比較します。ADR-contextが同等品質を維持しながら入力を削減できるかが、次のgo/no-go判断です。

## 13. Git履歴

主要な初期commit:

| Commit | 内容 |
|---|---|
| `0b466ff` | 正規化PoCの初期実装 |
| `265618b` | Analysis Projection追加 |
| `e0ba792` | Decision Extraction Prompt v2追加 |
| `066ea79` | 初版引継ぎ書とプロジェクト履歴 |

Repository: <https://github.com/soragaaoin-lang/plism>
