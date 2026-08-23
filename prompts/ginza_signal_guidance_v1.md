# GiNZA Signal Guidance v1

入力Messageには、GiNZA/spaCyと固定フレーズ規則が付与した`signals`と`signal_context`があります。

- 対象は`request_candidate`、`acceptance_candidate`、`rejection_candidate`、`reason_candidate`、`uncertainty_candidate`、`alternative_candidate`の6種類です。
- signalは候補箇所を探しやすくするための決定論的ヒントです。正解ラベル、Evidence、Decision、採用状態ではありません。
- signalがあるだけでDecisionを生成したり、`accepted`、`rejected`等のstatusを確定してはいけません。
- `signals[].char_start` / `char_end`で示された箇所とMessage本文、actor、前後Messageを読み、通常の抽出基準で判断してください。
- `signal_context`は前後Messageの位置と候補種別だけを示します。前後Message本文の代わりにはなりません。
- signalがないMessageも抽出対象です。signal検出漏れをDecision不存在と解釈してはいけません。
- `reason_candidate`や`alternative_candidate`が実際の理由・比較案かは、本文と時系列から検証してください。
- `signals`自身を`evidence_refs`へ指定してはいけません。Evidenceには実在するMessageまたはAttachment IDだけを使ってください。

この実験では、以下に続くProjection v3の抽出規則と出力契約をそのまま適用してください。
