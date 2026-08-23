# Requirement Extraction v1

添付された`source_messages.blind.md`だけを根拠に、会話上で表現されたシステムの期待動作・制約を抽出してください。

出力は`requirement_extraction_v1.schema.json`に適合するJSONだけにしてください。説明文やMarkdownコードフェンスを付けてはいけません。

## Requirementの定義

Requirementは、システムに期待される1つの独立して検証可能な動作または制約です。

- `1 Requirement = 1つの検証可能な期待動作`とする。
- 独立して変更、廃止、検証できる動作を1件へまとめない。
- `condition`には適用条件を、`expected_behavior`には観測可能な期待動作を書く。
- 条件が会話にない場合は推測せず`null`にする。
- 同じ意味の言い換えや実装完了報告を重複Requirementにしない。

## 抽出してはいけないもの

- 調査・実装を開始するという宣言
- 作業途中の進捗報告
- commit、PR、CI、merge、テスト成功だけの報告
- コード構成または現在実装の説明だけで、会話上の期待動作として採用されたことを確認できないもの
- 人間の指示・承認または後続の採用を確認できないAssistant単独の提案を`active`として扱うこと
- Requirementではなく実現方式だけを表す設計判断
- Gmail差分同期と無関係な前後文脈

実装報告の中で初めて具体的動作が示された場合、それを確定Requirementへ昇格させてはいけません。会話上の採用状態を判断できなければ`unknown`とし、不足を`missing_information`へ記録してください。

## lifecycle_status

次の値だけを使用してください。

- `proposed`: 案として示されたが、採用を確認できない
- `active`: 会話から現在有効な期待動作と読み取れる
- `rejected`: 明示的に採用しないとされた
- `superseded`: 後の期待動作へ置き換えられた
- `cancelled`: 仕様、作業、企画が中止された
- `unknown`: 会話だけでは判断できない

`active`は会話上の候補状態であり、コード実装済み・テスト検証済みを意味しません。

## Evidence

- すべてのRequirementに1件以上の`evidence_message_ids`を付ける。
- IDは入力に実在するMessage IDだけを使用する。
- 同じ機能名が書かれているだけのMessageをEvidenceにしない。
- 期待動作、条件、提案、承認、変更、置換、拒否、中止のいずれかを実際に支持するMessageを選ぶ。
- 会話にない数値、条件、理由、実装状態、検証状態を補完しない。

## 出力

- `requirement_id`は出現順に`R-001`から連番にする。
- `confidence`は`high`、`medium`、`low`のいずれかにする。
- 判断に必要な情報が不足する場合は、推測せず`missing_information`へ具体的に書く。
- Requirementが見つからない場合は空の`requirements`配列を返す。
