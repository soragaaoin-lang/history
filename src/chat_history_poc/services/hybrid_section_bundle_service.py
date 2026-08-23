from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from chat_history_poc.domain.errors import SectionBundleError
from chat_history_poc.services.ginza_signal_annotator import GinzaSignalAnnotator
from chat_history_poc.services.section_analysis_bundle_service import SectionAnalysisBundleService


class HybridSectionBundleService:
    """Adds candidate signals and interpretation knowledge to every Section input."""

    VERSION = "hybrid-section-v1"

    def __init__(self, annotator: GinzaSignalAnnotator | None = None) -> None:
        self.annotator = annotator or GinzaSignalAnnotator()

    def export(
        self,
        analysis_session_path: Path,
        section_index_path: Path,
        output_dir: Path,
        *,
        prompt_path: Path,
        guidance_path: Path,
        knowledge_path: Path,
        schema_path: Path,
    ) -> Path:
        SectionAnalysisBundleService().export(
            analysis_session_path,
            section_index_path,
            output_dir,
            prompt_path=prompt_path,
            schema_path=schema_path,
        )

        manifest_path = output_dir / "SECTION_RUN_MANIFEST.json"
        manifest = self._json_object(manifest_path)
        knowledge_text = knowledge_path.read_text(encoding="utf-8")
        knowledge_sha256 = self._sha256(knowledge_path)
        guidance = guidance_path.read_text(encoding="utf-8").rstrip()
        prompt = prompt_path.read_text(encoding="utf-8").lstrip()
        combined_prompt = output_dir / "analysis_prompt.md"
        combined_prompt.write_text(f"{guidance}\n\n---\n\n{prompt}", encoding="utf-8")

        total_counts: Counter[str] = Counter()
        messages_with_signals = 0
        total_messages = 0
        for run in manifest["section_runs"]:
            input_path = output_dir / run["input_path"]
            projection = self._json_object(input_path)
            annotated = self.annotator.annotate_projection(projection)
            annotated["interpretation_knowledge"] = {
                "knowledge_id": "decision-extraction-interpretation-notebook-v1",
                "authority": "interpretation_only_not_evidence",
                "source_specific_answers": False,
                "sha256": knowledge_sha256,
                "content": knowledge_text,
            }
            input_path.write_text(
                json.dumps(annotated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            annotation = annotated["signal_annotation"]
            total_messages += annotation["messages_examined"]
            messages_with_signals += annotation["messages_with_signals"]
            total_counts.update(annotation["signal_counts"])
            run["input_sha256"] = self._sha256(input_path)
            run["input_bytes"] = input_path.stat().st_size
            run["state"] = "ready_for_independent_hybrid_run"

        manifest["run_id"] = f'{manifest["source"]["analysis_session_sha256"][:16]}-{self.VERSION}'
        manifest["state"] = "ready_for_independent_hybrid_runs"
        manifest["experiment"] = {
            "version": self.VERSION,
            "pipeline": [
                "Candidate Section scope without Section exclusion",
                "GiNZA and phrase candidate signals",
                "Decision Prompt v4",
                "interpretation-only Notebook v1",
            ],
            "candidate_only_signals": True,
            "knowledge_is_evidence": False,
            "section_gold": False,
            "formal_oracle_experiment": False,
            "no_cross_section_information_during_extraction": True,
            "no_lifecycle_integration_during_section_extraction": True,
        }
        manifest["source"].update(
            {
                "prompt_v4_path": str(prompt_path.resolve()),
                "prompt_v4_sha256": self._sha256(prompt_path),
                "signal_guidance_path": str(guidance_path.resolve()),
                "signal_guidance_sha256": self._sha256(guidance_path),
                "knowledge_path": str(knowledge_path.resolve()),
                "knowledge_sha256": knowledge_sha256,
            }
        )
        manifest["prompt_sha256"] = self._sha256(combined_prompt)
        manifest["signal_annotation_summary"] = {
            "messages_examined": total_messages,
            "messages_with_signals": messages_with_signals,
            "signal_count": sum(total_counts.values()),
            "signal_counts": {
                name: total_counts[name] for name in GinzaSignalAnnotator.SIGNAL_TYPES
            },
        }
        self._write_json(manifest_path, manifest)
        self._write_json(output_dir / "HYBRID_RUN_MANIFEST.json", manifest)
        (output_dir / "RUN_INSTRUCTIONS.md").write_text(
            self._instructions(manifest["section_count"]), encoding="utf-8"
        )
        return output_dir

    @staticmethod
    def _instructions(section_count: int) -> str:
        return f"""# Hybrid Section Decision extraction v1

This bundle contains {section_count} independent Candidate Section inputs. Candidate Sections are not Gold.

For every `sections/SEC-xxx/` directory, give a fresh AI task only:

1. root `analysis_prompt.md`
2. that Section's `analysis_session.json`
3. root `decision_analysis_v3.schema.json`

Do not provide Section title/type, another Section, prior Decisions, Control/GiNZA/Prompt evaluations, Gold, repository history, or integration candidates. Save the first JSON unchanged as `decisions.raw.json`, compute its SHA-256 immediately, and do not retry or repair before validation.

Signals are candidate hints and interpretation_knowledge is not Evidence. Empty Decisions are valid. Cross-Section deduplication and lifecycle integration occur only after all Section raw outputs are frozen.
"""

    @staticmethod
    def _json_object(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SectionBundleError(f"invalid JSON in {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise SectionBundleError(f"JSON object required in {path}")
        return value

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
