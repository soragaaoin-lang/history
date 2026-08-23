# Decision Extraction Interpretation Notebook v1

## Authority

このNotebookは会話を分類・解釈するための一般的な判断ガイドである。

- 今回のプロジェクトで起きた事実ではない
- Decision、理由、代替案、statusのEvidenceではない
- 合成例の内容を実際の出力へ転記してはいけない
- Sourceと矛盾する場合はSourceを優先する
- Sourceだけで判断できない内容は`unknown`または`missing_information`とする

## Record taxonomy

### Decision

設計、実装、運用方法について、選択、採用、拒否、変更、中止、復元を行った記録。

### Requirement

利用者または製品が満たすべき期待動作。実現方法の選択を含まなければDecisionではない。

### Project constraint

複数作業へ継続的に適用される制約。制約そのものと、その制約を満たすために選んだ設計Decisionを区別する。

### Work instruction

調査、修正、レビュー、テスト、PR作成など、その作業を行う指示。実現方式の選択がなければDecisionではない。

### Progress report

作業開始、テスト成功、CI成功、merge完了などの報告。採用の補助Evidenceにはなり得るが、それ自体をDecisionにしない。

### Factual description

既存コード、環境、障害、データの状態説明。対応方針の選択がなければDecisionではない。

### Domain result

投資評価、ニュース判定、家計分析など、開発対象システムが扱う業務上の結果。ソフトウェア設計Decisionと混同しない。

## Actor authority

| 発言 | 通常の解釈 |
|---|---|
| 人間が「Bで進めて」と指示 | Bのaccepted候補 |
| Assistantが「Bを推奨します」 | Bのproposed候補 |
| AssistantがBの実装完了を報告 | 実装Evidence候補。採用理由とは限らない |
| 人間が後から「BをやめてCへ」 | Bのsupersededまたはcancelled、Cのaccepted候補 |
| 発言者や承認関係が不明 | proposedまたはunknown |

## Lifecycle distinctions

### Proposed versus accepted

提案が存在するだけではacceptedではない。人間の選択、明示的な合意、依頼との明確な対応を確認する。

### Rejected versus superseded

- 適用前に採用しなかった: rejected
- 一度採用した後に別方式へ置換: superseded

### Reverted versus cancelled

- 以前の状態へ戻した: reverted
- 作業や企画を止めたが、以前の状態へ戻したか不明: cancelled

### Unknown

実装報告と提案はあるが、誰が何を承認したか分からない場合などに使う。acceptedへ寄せない。

## Why / Why-not distinctions

### Rationale

採用・変更・中止した理由としてSourceに因果関係が明示されているもの。

### Alternative

実際に比較または検討された案。一般的に可能な方式をAIが追加してはいけない。

### Rejected alternative

不採用の案と、その案を不採用にした理由の両方がSourceに存在するもの。

案の不採用だけ分かり、理由がない場合は次のように扱う。

- 案は`alternatives`へ記録できる
- `rejected_alternatives`へ架空の理由を入れない
- 必要なら`missing_information`へ「却下理由不明」と記録する

## Synthetic examples

以下は分類方法を説明する合成例であり、実プロジェクトのEvidenceではない。

### Example 1: 提案だけ

Assistant: 「キャッシュにはRedisを使う案があります」

後続の承認・実装がない場合、Redisは`proposed`候補。`accepted`ではない。

### Example 2: 採用

Assistant: 「同期方式と非同期方式があります」

Human: 「まず同期方式で進めてください」

同期方式は`accepted`候補。Assistantの比較発言とHumanの指示をEvidenceにする。

### Example 3: 置換とWhy-not

Human: 「非同期方式で進めてください」

後のHuman: 「構成が複雑すぎるので、非同期方式はやめて同期方式へ変更してください」

- 非同期方式: `superseded`
- 同期方式: `accepted`
- Why-not: 非同期方式は構成が複雑すぎる

### Example 4: 却下理由なし

Human: 「案Aではなく案Bでお願いします」

案Bは`accepted`候補。案Aの不採用は分かるが、理由を推測してはいけない。

### Example 5: 中止と復元の違い

Human: 「この機能の企画はいったん中止します」

元のコードへ戻したEvidenceがなければ`cancelled`。`reverted`ではない。

### Example 6: RequirementとDecision

Human: 「障害時には利用者へエラーを表示してください」

これは期待動作でありRequirement候補。

Assistant: 「エラー通知は画面内バナーで実装します」

バナー方式が承認または実装されたなら、その方式選択はDecision候補。

### Example 7: 進捗報告

Assistant: 「テストがすべて成功し、PRを作成しました」

これはprogress report。独立した設計選択がなければDecisionではない。

### Example 8: Domain result

Assistant: 「この投資案件は見送り判定です」

これは業務上の評価結果。投資評価アルゴリズムや実装方式を決めた発言でなければソフトウェアDecisionではない。

## Final review checklist

1. 各Decisionは方式や方針の選択・変更を表しているか
2. actorの権限を確認したか
3. 後続発言で変更・中止されていないか
4. accepted以外のstatus候補を実際に確認したか
5. rationaleはSource上の理由か
6. rejected alternativeには明示された却下理由があるか
7. Requirement、作業指示、進捗報告、Domain resultを混入していないか
8. 合成例やNotebookをEvidenceにしていないか
