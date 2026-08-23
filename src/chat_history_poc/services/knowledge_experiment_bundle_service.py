from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from chat_history_poc.domain.errors import KnowledgeExperimentError


class KnowledgeExperimentBundleService:
    """Exports prompt-only and prompt-plus-knowledge experimental arms."""

    EXPERIMENT_VERSION = "decision-knowledge-v1"
    ARMS = ("prompt_only", "prompt_plus_knowledge")

    def export(
        self,
        analysis_session_path: Path,
        output_root: Path,
        *,
        prompt_path: Path,
        knowledge_path: Path,
        schema_path: Path,
        control_decisions_path: Path,
    ) -> Path:
        projection = self._json_object(analysis_session_path)
        if projection.get("projection_version") != "3":
            raise KnowledgeExperimentError("Projection v3 analysis_session is required")
        if "signal_annotation" in projection or any(
            isinstance(message, dict) and "signals" in message
            for message in projection.get("messages", [])
        ):
            raise KnowledgeExperimentError("signal-free Projection v3 input is required")
        if output_root.exists() and any(output_root.iterdir()):
            raise KnowledgeExperimentError(f"output directory is not empty: {output_root}")
        output_root.mkdir(parents=True, exist_ok=True)

        prompt = prompt_path.read_bytes()
        schema = schema_path.read_bytes()
        knowledge_text = knowledge_path.read_text(encoding="utf-8")
        knowledge_sha256 = self._sha256(knowledge_path)
        source_hash = self._sha256(analysis_session_path)
        control_hash = self._sha256(control_decisions_path)

        arms: list[dict[str, Any]] = []
        for arm in self.ARMS:
            arm_dir = output_root / arm
            arm_dir.mkdir()
            analysis_output = arm_dir / "analysis_session.json"
            if arm == "prompt_only":
                shutil.copyfile(analysis_session_path, analysis_output)
            else:
                knowledge_projection = json.loads(json.dumps(projection, ensure_ascii=False))
                knowledge_projection["interpretation_knowledge"] = {
                    "knowledge_id": "decision-extraction-interpretation-notebook-v1",
                    "authority": "interpretation_only_not_evidence",
                    "source_specific_answers": False,
                    "sha256": knowledge_sha256,
                    "content": knowledge_text,
                }
                analysis_output.write_text(
                    json.dumps(knowledge_projection, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            (arm_dir / "analysis_prompt.md").write_bytes(prompt)
            (arm_dir / schema_path.name).write_bytes(schema)
            (arm_dir / "RUN_INSTRUCTIONS.md").write_text(
                self._instructions(arm), encoding="utf-8"
            )
            arms.append(
                {
                    "arm": arm,
                    "independent_variable": (
                        "Decision Prompt v4 only"
                        if arm == "prompt_only"
                        else "interpretation Notebook added to the same Prompt v4"
                    ),
                    "analysis_session": f"{arm}/analysis_session.json",
                    "analysis_session_sha256": self._sha256(analysis_output),
                    "analysis_session_bytes": analysis_output.stat().st_size,
                    "prompt_sha256": self._sha256(arm_dir / "analysis_prompt.md"),
                    "schema_sha256": self._sha256(arm_dir / schema_path.name),
                    "first_ai_output": f"{arm}/decisions.raw.json",
                    "state": "ready_for_independent_first_run",
                }
            )

        manifest = {
            "experiment_version": self.EXPERIMENT_VERSION,
            "state": "ready_for_two_independent_first_runs",
            "research_questions": [
                "Does explicit classification and temporal reasoning in Prompt v4 improve Decision extraction over v3?",
                "Does an interpretation-only Notebook improve the same Prompt v4 without source-specific answer leakage?",
            ],
            "source": {
                "analysis_session_path": str(analysis_session_path.resolve()),
                "analysis_session_sha256": source_hash,
                "analysis_session_bytes": analysis_session_path.stat().st_size,
                "control_decisions_path": str(control_decisions_path.resolve()),
                "control_decisions_sha256": control_hash,
                "prompt_path": str(prompt_path.resolve()),
                "prompt_sha256": self._sha256(prompt_path),
                "knowledge_path": str(knowledge_path.resolve()),
                "knowledge_sha256": knowledge_sha256,
                "schema_path": str(schema_path.resolve()),
                "schema_sha256": self._sha256(schema_path),
            },
            "held_constant": [
                "signal-free Projection v3 Messages and Attachments",
                "Decision Schema v3",
                "AI model and execution settings",
                "one unrepaired first output per arm",
            ],
            "forbidden_inputs_during_extraction": [
                "Control Decisions",
                "GiNZA Decisions and evaluation",
                "Section titles and evaluation",
                "Gold or mapping files",
            ],
            "arms": arms,
        }
        (output_root / "EXPERIMENT_MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return output_root

    @staticmethod
    def _instructions(arm: str) -> str:
        knowledge_note = (
            "The input contains no interpretation Notebook."
            if arm == "prompt_only"
            else (
                "The input contains interpretation_knowledge. It is a classification guide only, "
                "not Evidence or source-specific truth."
            )
        )
        return f"""# Independent Decision extraction: {arm}

Give a fresh AI task only these three files from this directory:

1. `analysis_prompt.md`
2. `analysis_session.json`
3. `decision_analysis_v3.schema.json`

{knowledge_note}

Do not provide Control/GiNZA Decisions, evaluation reports, Section labels, Gold, repository history, or the other experimental arm. Use the same model and settings for both arms. Save the first output unchanged as `decisions.raw.json`, compute its SHA-256 immediately, and do not retry or repair before evaluation.
"""

    @staticmethod
    def _json_object(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise KnowledgeExperimentError(f"invalid JSON in {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise KnowledgeExperimentError(f"JSON object required in {path}")
        return value

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
