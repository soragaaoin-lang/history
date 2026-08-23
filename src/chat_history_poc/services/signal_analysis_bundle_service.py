from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from chat_history_poc.domain.errors import SignalAnnotationError
from chat_history_poc.services.ginza_signal_annotator import GinzaSignalAnnotator


class SignalAnalysisBundleService:
    """Exports a separate signal-assisted run while preserving the baseline input."""

    def __init__(self, annotator: GinzaSignalAnnotator | None = None) -> None:
        self.annotator = annotator or GinzaSignalAnnotator()

    def export(
        self,
        analysis_session_path: Path,
        output_dir: Path,
        *,
        base_prompt_path: Path,
        guidance_path: Path,
        schema_path: Path,
        baseline_decisions_path: Path | None = None,
    ) -> Path:
        projection = self._json_object(analysis_session_path)
        if output_dir.exists() and any(output_dir.iterdir()):
            raise SignalAnnotationError(f"output directory is not empty: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)

        annotated = self.annotator.annotate_projection(projection)
        analysis_output = output_dir / "analysis_session.json"
        analysis_output.write_text(
            json.dumps(annotated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        guidance = guidance_path.read_text(encoding="utf-8").rstrip()
        base_prompt = base_prompt_path.read_text(encoding="utf-8").lstrip()
        prompt_output = output_dir / "analysis_prompt.md"
        prompt_output.write_text(f"{guidance}\n\n---\n\n{base_prompt}", encoding="utf-8")
        schema_output = output_dir / schema_path.name
        shutil.copyfile(schema_path, schema_output)

        annotation = annotated["signal_annotation"]
        manifest = {
            "run_id": f'{annotated["session_id"]}-ginza-signal-v1',
            "state": "ready_for_signal_assisted_run",
            "experiment": {
                "research_question": (
                    "Does deterministic Japanese linguistic candidate annotation improve "
                    "Why/Why-not Decision extraction?"
                ),
                "independent_variable": "GiNZA/spaCy candidate signals and candidate-only guidance",
                "held_constant": [
                    "Projection v3 Message and Attachment evidence",
                    "Decision extraction criteria",
                    "Decision Schema v3",
                    "AI model and execution settings must be held constant by the evaluator",
                ],
                "signal_types": annotation["signal_types"],
                "candidate_only": True,
                "no_lifecycle_assignment_by_annotator": True,
            },
            "source": {
                "analysis_session_path": str(analysis_session_path.resolve()),
                "analysis_session_sha256": self._sha256(analysis_session_path),
                "base_prompt_path": str(base_prompt_path.resolve()),
                "base_prompt_sha256": self._sha256(base_prompt_path),
                "guidance_path": str(guidance_path.resolve()),
                "guidance_sha256": self._sha256(guidance_path),
                "schema_path": str(schema_path.resolve()),
                "schema_sha256": self._sha256(schema_path),
            },
            "outputs": {
                "analysis_session": "analysis_session.json",
                "analysis_session_sha256": self._sha256(analysis_output),
                "analysis_prompt": "analysis_prompt.md",
                "analysis_prompt_sha256": self._sha256(prompt_output),
                "schema": schema_output.name,
                "schema_sha256": self._sha256(schema_output),
                "first_ai_output": "decisions.raw.json",
            },
            "annotation_report": annotation,
        }
        if baseline_decisions_path is not None:
            manifest["source"]["signal_free_baseline_decisions_path"] = str(
                baseline_decisions_path.resolve()
            )
            manifest["source"]["signal_free_baseline_decisions_sha256"] = self._sha256(
                baseline_decisions_path
            )
        (output_dir / "SIGNAL_RUN_MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (output_dir / "RUN_INSTRUCTIONS.md").write_text(
            self._instructions(annotated["session_id"]), encoding="utf-8"
        )
        (output_dir / "SIGNAL_ANNOTATION_REPORT.md").write_text(
            self._report(annotation, analysis_session_path, analysis_output), encoding="utf-8"
        )
        return output_dir

    @staticmethod
    def _json_object(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SignalAnnotationError(f"invalid JSON in {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise SignalAnnotationError(f"JSON object required in {path}")
        return value

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _instructions(session_id: str) -> str:
        return f"""# GiNZA signal-assisted Decision extraction v1

Session: `{session_id}`

Give a fresh AI task only these three files:

1. `analysis_prompt.md`
2. `analysis_session.json`
3. `decision_analysis_v3.schema.json`

Use the same AI model and execution settings as the signal-free Projection v3 baseline. Save the first output unchanged as `decisions.raw.json`; do not retry or repair it before evaluation.

The six `*_candidate` signals are deterministic hints, not labels, Evidence, Gold, or lifecycle status. Evaluate the resulting Decisions against the frozen signal-free baseline for Decision coverage, rationale/rejected-alternative coverage, Evidence accuracy, status accuracy, atomicity, type confusion, and hallucination.
"""

    @classmethod
    def _report(
        cls,
        annotation: dict[str, Any],
        source_path: Path,
        output_path: Path,
    ) -> str:
        counts = "\n".join(
            f"- `{name}`: {annotation['signal_counts'][name]}"
            for name in annotation["signal_types"]
        )
        source_size = source_path.stat().st_size
        output_size = output_path.stat().st_size
        growth = (output_size / source_size - 1) if source_size else 0
        return f"""# GiNZA Signal Annotation v1

## 機械処理結果

- 対象Message: {annotation['messages_examined']}
- signalありMessage: {annotation['messages_with_signals']}
- signal総数: {annotation['signal_count']}
- 入力サイズ: {source_size} bytes
- signal付き入力サイズ: {output_size} bytes
- サイズ増加率: {growth:.2%}

## 種別

{counts}

## 解釈上の注意

これは抽出精度の評価結果ではありません。signalは候補であり、Decision、Evidence、Gold、lifecycle statusではありません。Attachment、constraint、implementation eventはv1の注釈対象外です。

次はsignalなしProjection v3と同じAIモデル・設定で一度だけ抽出し、Decisionの対応付け後にWhy/Why-not、Evidence、status、atomicity、型混同、幻覚を比較します。
"""
