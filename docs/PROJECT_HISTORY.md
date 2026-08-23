# plism PoC プロジェクト履歴

最終更新: 2026-08-23

この文書は逐語的な会話要約ではなく、プロジェクトの目的、設計変更、実験、失敗、判断の状態遷移を記録する。現在の実行手順と引継ぎ要点は [HANDOFF.md](HANDOFF.md) を参照する。

## 1. 出発点

AI駆動開発では、実装方針、比較案、採用理由、却下理由、途中の方向転換がチャットへ埋もれる。実装後に「なぜこの形になったか」を、人間も次のAIも追いにくいことが課題だった。

当初は次が混在し、完成像の議論が先行していた。

- 人間向け仕様書を作るのか
- AIが再利用する知識を作るのか
- 全自動にするのか、人間レビューを挟むのか
- RAG、Vector DB、Web UIまで作るのか

そこでPoCを、実履歴からEvidence付きDecisionを復元できるかという技術仮説へ絞った。

## 2. Codex JSONLを入力に固定

CodexがローカルへJSONL履歴を保存していることを確認し、架空会話ではなく実データを使う方針にした。

```text
抽象的な仕様書生成
  ↓
実際のAI開発履歴を材料にする
  ↓
Codex Raw JSONLをSource of Truthにする
```

RAG、Vector DB、Webアプリ、マルチエージェント、包括的UML・テスト計画はPoCの本体から外した。

## 3. Lossless normalization

最初の基盤では、JSONL全行をRaw Eventとして保持し、各行を `recognized`、`unknown`、`parse_error` のいずれかへ分類した。

設計原則:

- 入力JSONLを変更しない
- 未知イベントと解析失敗を捨てない
- Raw行、source order、Messageへ戻れるようにする
- 同じ入力はSHA-256で重複登録しない
- `silently_dropped = 0` を機械確認する

実Codex JSONL 2件、合計10,753行を全行分類できた。主セッション8,306行ではunknown、parse error、silent dropはいずれも0だった。

この段階で「正規化処理が中間情報を落とす」という最初の懸念は大きく減った。

## 4. 完全保存とAI入力の分離

最初のNormalized Sessionには、製品開発会話だけでなく次も大量に含まれた。

- Developer / System instructions
- permissions、plugins、skills
- environment context
- AGENTS.md
- command、apply_patch、file change

完全保存としては正しいが、AIのDecision分析にはノイズだった。この発見から二層設計へ変更した。

```text
Raw JSONL
  ↓
Normalized Session（監査用・欠損なし）
  ↓
Analysis Projection（分析に必要な情報）
```

Projectionでは、人間・Assistantの会話をmessages、AGENTS.mdをconstraints、commandとfile changeをimplementation eventsへ分離した。8,306 eventsは484 messages、1 constraint、237 implementation eventsへ整理された。

ここで「情報を保存すること」と「AIへ全部読ませること」は別問題だと確定した。

## 5. Decision extraction v1

Prompt v1はEvidence必須、推測禁止、不足情報の明記、提案と採用の区別を要求した。一括入力から約16件の主要Decisionを取得し、accepted、superseded、revertedを出力できた。

前向きな観測:

- Gmail差分同期の方針変更を拾えた
- 複雑な非同期Web方式から簡易同期Web方式への置換を分離できた
- Evidenceから元Messageへ戻れた
- 存在しないEvidenceをvalidatorで拒否できた

同時に次の問題が見えた。

- 一つのDecisionへ複数判断を詰め込む
- 実装を戻していない企画中止を `reverted` とする
- AI出力のフィールド名がSchema契約からずれる
- もっともらしい16件が全体の何割かはGoldなしでは分からない

この結果からAtomicityを評価項目に追加し、`cancelled` と `reverted` を分け、AI原本とSchema準拠版を分離保存する方針にした。

## 6. Prompt v2と人間向け表現

Prompt v2では出力キー、JSONテンプレート、Atomicity、最新状態、`cancelled` を明記した。JSONは機械可読な正本、人間向けは同じJSONからMarkdownまたは静的HTMLを生成する役割分担にした。

```text
analysis_session.json → AI入力
decisions.json        → 機械可読正本
decisions.md / HTML   → 人間向け表示
```

ただしHTML実装より先に、AI抽出が本当に正しいかを評価する方針を優先した。

## 7. Requirement層の設計

Decisionとは別に「現在期待される動作」を表すRequirement層を検討した。

- Decision: なぜその方針・方式を選んだか
- Requirement: 条件の下で何が起きるべきか
- ADR: どう実現するかという設計判断
- 作業制約: 今回の変更作業だけに適用する制約
- Reconciliation: 会話上の仕様、コード実装、テスト検証を後から照合する層

USDM、EARS、Kiro `requirements.md` は正本ではなく、同じRequirement JSONから生成する表示候補とした。Requirement本体へimplementation / verification statusを混ぜない設計にした。

## 8. Gmail Requirement Goldの先行作成

AI Requirement出力を見る前にGoldを固定するため、Gmail差分同期の関連Messageを35件へ絞り、前後turn付きSource、blind版、空Goldテンプレート、Negative Setテンプレート、評価Protocolを作成した。

Source retrievalとRequirement extractionを分離した。35件セットで測れるのは「選択済みSourceからの抽出」であり、セッション全体からSourceを見つけるRecallではない。

人間裁定でGoldは40件候補から44件へ確定した。Requirement v1の結果:

- strict Recall 70.45%
- partial=0.5 Recall 84.09%
- strict Precision 60.42%
- partial=0.5 Precision 73.96%
- Evidence意味妥当性 97.96%
- Critical Hallucination 0件
- 型混同6件
- `superseded` Recall 0/1

主問題は仕様候補を見つけられないことより、Requirement / ADR / 作業制約の分類、条件脱落、状態統合だった。

この評価結果を見た時点でGmail 35 Messageはdevelopment setになった。以後、未見性能の主張には使わない。

## 9. 7月26日長期会話とSectioning

次に約40MBの長期会話を扱った。正規化結果は969 Message、35 Attachment。Guardian履歴とenvironment / pluginだけのuser-role Eventを製品会話から除外し、41 Section候補へ分割した。

Message未割当、Attachment欠落、参照エラーはいずれも0。Section名・境界・typeは `candidate_pending_human_adjudication` で、Goldではない。

長文一括入力の問題を切り分けるため、Section coverageを暫定proxyとして使った。ただし正式Recallとは呼ばない。

## 10. Decision v2長期会話Baseline

一括Analysis Projectionから24 Decisionを抽出した。

- Schema 24/24
- Evidence存在 62/62
- Evidence意味支持 24/24
- Critical Hallucination 0
- 暫定type precision 91.67%
- Atomicity 75.0%
- 全41 Section参照 22/41
- 暫定target 21/32
- statusは全24件accepted

精度より前に、正規化済みAttachment 35件が `analysis_session.json` へ1件も投影されていない欠落を発見した。正規化失敗ではなくProjection失敗だった。

## 11. Projection v3

Analysis Projectionへattachments配列を追加し、MessageとAttachmentを型付きEvidenceとして扱った。旧Prompt判断規則は可能な限り維持し、独立変数をAttachment追加に絞った。

結果:

- Decision 24 → 31
- 全41 Section参照 22 → 33
- 暫定target 21/32 → 28/32
- 旧未取得11 Section中10を回復
- Attachment Evidence 20/20が意味的に妥当
- Critical Hallucination 0

一方で、存在しないEvidence IDが1件、Atomicity悪化、旧Decision維持率58.33%、全件acceptedが残った。Projection v3は採用したが、この31件原本はEvidence検査失敗例として修正せず保持した。

## 12. GiNZA signal実験

GiNZAと軽量Phrase規則で、REASON、REJECTION、ACCEPTANCE、REQUEST、UNCERTAINTY、ALTERNATIVEの候補をMessageへ付与した。signalはstatusや正解ではなく、LLMが見る候補位置である。

1,782 signalを485 Messageへ付与した比較では、target Section coverageとEvidence存在は改善したが、Why-notは低下し、入力サイズが40.15%増えた。全status acceptedも変わらなかった。

結論は保留。GiNZAは候補検索には役立つ可能性があるが、それだけで理由・却下理由・lifecycleを解決しない。

## 13. Prompt v4とInterpretation Notebook

自然言語解析だけでなく、厳密分類Promptと、正解を含まない一般的な解釈Notebookを与える実験を行った。

Prompt v4はWhy-not配列とAtomicityを改善したが、Evidence存在100%、旧Decision維持85%、target coverageの事前条件を落としたため棄却した。

Notebook追加はEvidence存在、Atomicity、型混同、wrapper置換の状態表現を改善し、合成例漏洩も0だった。しかし意味維持とSection coverageをさらに悪化させたため棄却した。

この結果から、情報や指示を足すほど良くなるとは限らず、長文一括入力における選択揺れが支配的だと判断した。

## 14. Hybrid Section pipeline

次の構成を統合した。

```text
Section分割
  ↓
GiNZA・軽量規則で候補検索
  ↓
Section単位でPrompt v4 + Notebookを使って厳密判定
  ↓
Section間でDecisionを統合
  ↓
時系列からstatusを確定
```

初回Section抽出は268 raw Decision。257件が検証を通り、統合後256件になった。全41 Section 36、暫定target 31/32を覆った。

固定40件サンプルでは、再利用可能85%、Atomicity 82.5%、Evidence意味支持100%、status妥当82.5%、幻覚0件だった。

失敗11件のうち、SEC-012の7件は意味やEvidenceの問題ではなく、`rationale` がstringで返ったSchema型崩れだった。残り4件は未知Evidence IDだった。

統合候補の絞り込みにより、257件全組み合わせではなく15 Decision / 6 cluster / 11 pairまで人間・AIレビュー対象を減らした。ただし「候補に入らなかった同義Decisionがない」とは証明していない。

## 15. Lossless schema recovery

Schema崩れでSection全体を失わないため、限定的修復を追加した。

許可するのは、配列であるべき次のフィールドへ単一文字列が来た場合、その文字列を1要素配列へ包むことだけである。

- alternatives
- rationale
- risks
- revisit_conditions
- missing_information

Decision ID、status、Evidence、本文の意味は変更しない。修復箇所を記録し、Raw出力とHashを保持する。

これによりSEC-012の7件と20 Evidenceをすべて回復し、暫定targetは32/32になった。

## 16. Lifecycle review

Section抽出とcross-section integrationだけでは、後続の採用・置換を見落とした。そこで統合後に残るproposed 10件を対象に、元Sectionと後続2 SectionのEvidenceを見てstatusだけを再裁定する独立工程を追加した。

- proposed → accepted: 8件
- proposed → superseded: 1件
- proposed維持: 1件

既知のstatus失敗7件はすべて改善した。新たに2件が後続人間Evidenceによりacceptedへ変化したが、固定済み旧裁定ではproposedが妥当だったため、結果を見て正解を書き換えず、人間再裁定待ちにした。

最終値は263 Decision、全41 Section 37/41、暫定target 32/32、Evidence 776/776。固定40件statusを保守的に数えると38/40（95%）。

## 17. 実験タスクと不要履歴の整理

Hybrid実験でCodex UI上に作成した41 Section、6 Integration cluster、1評価の計48タスクをアーカイブした。削除ではなく復元可能である。

リポジトリ内の不要なGuardian系JSONL 44件、約6.57MBを削除した。研究対象の7月・8月履歴と通常の3ファイルは維持した。

## 18. 現在の評価判断

同じ開発セット上では次が確認できた。

- Attachment-aware Projectionは欠落を明確に改善した。
- Section単位処理は一括入力よりcoverage proxyを改善した。
- Evidence追跡は強い。
- 限定Schema recoveryは不必要な全件損失を防いだ。
- lifecycleを別工程にすると既知の状態失敗を改善した。

一方、7月26日会話を見ながら改善したため、結果には評価漏洩・開発セット適合がある。これはモデル重みの学習ではないが、研究評価上の過学習に相当する。

したがって現在の結論は次である。

> PoCは「この方式が技術的に動く」ことを示す段階まで到達した。「未知の会話でも十分な精度で動く」ことはまだ示していない。

製品運用では、当初の「全候補を人間が承認してから使う」案も見直した。全件レビューは継続利用の障壁になるため、lifecycleとは別に `confirmed`、`inferred`、`candidate` のtrust levelを保持し、通常は検索可能にする。人間確認は、矛盾、状態不明、高リスク、Evidence不一致が実際の作業で問題になるときだけ要求する。このtrust levelは現時点のDecision Schemaには未実装であり、MVP設計上の次段階である。

## 19. 次の状態遷移

次はコード機能を増やす段階ではなく、一般化仮説を評価する段階である。

```text
現在の実装・Prompt・Ruleを凍結
  ↓
開発セットの未裁定2件を人間確認
  ↓
未見セッションを選定
  ↓
AI実行前に人間Gold / Negative Setを固定
  ↓
一度だけblind run
  ↓
事前固定したRecall / Precision / Evidence / Status / Atomicity / Hallucinationで採点
```

この盲検評価を通るまでは、Gmailや7月26日で上がった値を一般性能として発表しない。

その後、製品価値を次のA/Bで確認する。

```text
同じ実務タスク
  ├─ Full-context: 許可されたRaw会話全体
  └─ ADR-context: 承認済みDecision Record + 必要時だけRaw Evidence
```

品質だけでなく、入力byte・推定token・credit、時間、質問回数、重要発見、誤認、過去判断との矛盾、人間の盲検選好を比較する。完全な仕様復元より、少ないコンテキストで次の作業を安全に始められるかを製品のgo/no-go基準にする。

## 20. Git上の状態

初期基盤、Python 3.10対応、Analysis Projection、Decision Prompt v2までは公開GitHubへ反映された履歴がある。一方、2026-08-23時点のProjection v3、Section、GiNZA、Notebook、Hybrid、Schema recovery、lifecycle、評価資料には未commit・未push変更が含まれる。

Repository: <https://github.com/soragaaoin-lang/history>

実会話と生成物には個人情報・秘密情報・未公開コードが含まれ得るため、公開するコード・Prompt・Schema・匿名化済み集計と、ローカル限定のRaw・Artifactsを分けて扱う。
