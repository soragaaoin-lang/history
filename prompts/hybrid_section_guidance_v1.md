# Hybrid Section Guidance v1

この入力は、全セッションを機械的に除外せず、1つのCandidate Sectionへ限定した比較実験です。

MessageにはGiNZA/spaCyと固定フレーズ規則による`signals`が存在する場合があります。

- signalは候補箇所を示すヒントであり、Decision、Evidence、Gold、statusではありません
- signalだけを理由にDecisionを生成したり、`accepted`等を確定してはいけません
- signalがないMessageも通常どおり判定してください
- `signal_context`は直前Messageの候補情報であり、本文やactor確認の代わりではありません

入力に`interpretation_knowledge`が存在します。

- 一般的な分類・status・Why/Why-not判断のガイドです
- 今回の会話で起きた事実ではなく、Evidenceにもできません
- 合成例を今回のDecisionへ転記してはいけません
- Sourceと矛盾する場合はSourceを優先してください

Section title、Section type、Gold、他Sectionの内容は与えられていません。このSectionにDecisionが存在しない場合、空の`decisions`を返すことは正しい出力です。

以下に続くPrompt v4の分類、時系列、Evidence、出力契約を厳密に適用してください。
