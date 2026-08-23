from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from chat_history_poc.domain.errors import PocError
from chat_history_poc.repositories.sqlite_repository import SQLiteRepository
from chat_history_poc.services.analysis_bundle_service import AnalysisBundleService
from chat_history_poc.services.analysis_import_service import AnalysisImportService
from chat_history_poc.services.ingest_service import IngestService
from chat_history_poc.services.render_service import RenderService
from chat_history_poc.services.decision_v3_validation_service import DecisionV3ValidationService
from chat_history_poc.services.section_analysis_bundle_service import SectionAnalysisBundleService
from chat_history_poc.services.integration_candidate_service import IntegrationCandidateService
from chat_history_poc.services.integration_adjudication_bundle_service import (
    IntegrationAdjudicationBundleService,
)
from chat_history_poc.services.integration_adjudication_validation_service import (
    IntegrationAdjudicationValidationService,
)
from chat_history_poc.services.integration_adjudication_v2_bundle_service import (
    IntegrationAdjudicationV2BundleService,
)
from chat_history_poc.services.integrated_decision_assembly_service import (
    IntegratedDecisionAssemblyService,
)
from chat_history_poc.services.ginza_signal_annotator import GinzaSignalAnnotator
from chat_history_poc.services.signal_analysis_bundle_service import SignalAnalysisBundleService
from chat_history_poc.services.knowledge_experiment_bundle_service import (
    KnowledgeExperimentBundleService,
)
from chat_history_poc.services.hybrid_section_bundle_service import HybridSectionBundleService
from chat_history_poc.services.hybrid_section_run_service import HybridSectionRunService
from chat_history_poc.services.lifecycle_review_bundle_service import (
    LifecycleReviewBundleService,
)
from chat_history_poc.services.lifecycle_adjudication_service import (
    LifecycleAdjudicationService,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="python -m chat_history_poc")
    result.add_argument("--db", type=Path, default=Path("data/chat_history.db"))
    result.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    sub = result.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("jsonl", type=Path)
    export = sub.add_parser("export-analysis")
    export.add_argument("session_id")
    export.add_argument("--prompt-version", choices=("v1", "v2", "v3"), default="v2")
    export.add_argument("--projection-version", choices=("1", "3"), default="1")
    export.add_argument("--normalized-messages", type=Path)
    export.add_argument("--normalized-attachments", type=Path)
    import_analysis = sub.add_parser("import-analysis")
    import_analysis.add_argument("session_id")
    import_analysis.add_argument("decisions_json", type=Path)
    import_analysis.add_argument("--prompt-version", choices=("v1", "v2"), default="v2")
    render = sub.add_parser("render")
    render.add_argument("session_id")
    validate_v3 = sub.add_parser("validate-decisions-v3")
    validate_v3.add_argument("analysis_session", type=Path)
    validate_v3.add_argument("decisions_json", type=Path)
    export_sections = sub.add_parser("export-section-analysis")
    export_sections.add_argument("analysis_session", type=Path)
    export_sections.add_argument("section_index", type=Path)
    export_sections.add_argument("output_dir", type=Path)
    export_sections.add_argument("--prompt", type=Path, default=Path("prompts/decision_extraction_v3.md"))
    export_sections.add_argument("--schema", type=Path, default=Path("schemas/decision_analysis_v3.schema.json"))
    integration = sub.add_parser("export-integration-candidates")
    integration.add_argument("section_bundle", type=Path)
    integration.add_argument("output_dir", type=Path)
    adjudication = sub.add_parser("export-integration-adjudication")
    adjudication.add_argument("candidate_bundle", type=Path)
    adjudication.add_argument("output_dir", type=Path)
    adjudication.add_argument(
        "--prompt",
        type=Path,
        default=Path("prompts/integration_adjudication_v1.md"),
    )
    adjudication.add_argument(
        "--schema",
        type=Path,
        default=Path("schemas/integration_adjudication_v1.schema.json"),
    )
    validate_adjudication = sub.add_parser("validate-integration-adjudication")
    validate_adjudication.add_argument("cluster_input", type=Path)
    validate_adjudication.add_argument("adjudication_json", type=Path)
    adjudication_v2 = sub.add_parser("export-integration-adjudication-v2")
    adjudication_v2.add_argument("candidate_bundle", type=Path)
    adjudication_v2.add_argument("output_dir", type=Path)
    adjudication_v2.add_argument(
        "--prompt", type=Path, default=Path("prompts/integration_adjudication_v2.md")
    )
    assemble_integrated = sub.add_parser("assemble-integrated-decisions")
    assemble_integrated.add_argument("candidate_bundle", type=Path)
    assemble_integrated.add_argument("adjudication_bundle", type=Path)
    assemble_integrated.add_argument("output_dir", type=Path)
    adjudication_v2.add_argument(
        "--schema", type=Path, default=Path("schemas/integration_adjudication_v1.schema.json")
    )
    signal_analysis = sub.add_parser("export-signal-analysis")
    signal_analysis.add_argument("analysis_session", type=Path)
    signal_analysis.add_argument("output_dir", type=Path)
    signal_analysis.add_argument("--model", default="ja_ginza")
    signal_analysis.add_argument(
        "--base-prompt", type=Path, default=Path("prompts/decision_extraction_v3.md")
    )
    signal_analysis.add_argument(
        "--guidance", type=Path, default=Path("prompts/ginza_signal_guidance_v1.md")
    )
    signal_analysis.add_argument(
        "--schema", type=Path, default=Path("schemas/decision_analysis_v3.schema.json")
    )
    signal_analysis.add_argument("--baseline-decisions", type=Path)
    knowledge_experiment = sub.add_parser("export-knowledge-experiment")
    knowledge_experiment.add_argument("analysis_session", type=Path)
    knowledge_experiment.add_argument("output_root", type=Path)
    knowledge_experiment.add_argument(
        "--prompt", type=Path, default=Path("prompts/decision_extraction_v4.md")
    )
    knowledge_experiment.add_argument(
        "--knowledge",
        type=Path,
        default=Path("knowledge/decision_extraction_notebook_v1.md"),
    )
    knowledge_experiment.add_argument(
        "--schema", type=Path, default=Path("schemas/decision_analysis_v3.schema.json")
    )
    knowledge_experiment.add_argument("--control-decisions", type=Path, required=True)
    hybrid_sections = sub.add_parser("export-hybrid-section-analysis")
    hybrid_sections.add_argument("analysis_session", type=Path)
    hybrid_sections.add_argument("section_index", type=Path)
    hybrid_sections.add_argument("output_dir", type=Path)
    hybrid_sections.add_argument("--model", default="ja_ginza")
    hybrid_sections.add_argument(
        "--prompt", type=Path, default=Path("prompts/decision_extraction_v4.md")
    )
    hybrid_sections.add_argument(
        "--guidance", type=Path, default=Path("prompts/hybrid_section_guidance_v1.md")
    )
    hybrid_sections.add_argument(
        "--knowledge",
        type=Path,
        default=Path("knowledge/decision_extraction_notebook_v1.md"),
    )
    hybrid_sections.add_argument(
        "--schema", type=Path, default=Path("schemas/decision_analysis_v3.schema.json")
    )
    finalize_hybrid = sub.add_parser("finalize-hybrid-section-runs")
    finalize_hybrid.add_argument("bundle_dir", type=Path)
    lifecycle_review = sub.add_parser("export-lifecycle-review")
    lifecycle_review.add_argument("integrated_decisions", type=Path)
    lifecycle_review.add_argument("section_bundle", type=Path)
    lifecycle_review.add_argument("output_dir", type=Path)
    lifecycle_review.add_argument(
        "--prompt", type=Path, default=Path("prompts/lifecycle_adjudication_v1.md")
    )
    lifecycle_review.add_argument(
        "--schema", type=Path, default=Path("schemas/lifecycle_adjudication_v1.schema.json")
    )
    apply_lifecycle = sub.add_parser("apply-lifecycle-adjudication")
    apply_lifecycle.add_argument("integrated_decisions", type=Path)
    apply_lifecycle.add_argument("review_bundle", type=Path)
    apply_lifecycle.add_argument("output_dir", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.command == "export-section-analysis":
            path = SectionAnalysisBundleService().export(
                args.analysis_session,
                args.section_index,
                args.output_dir,
                prompt_path=args.prompt,
                schema_path=args.schema,
            )
            print(path)
            return 0
        if args.command == "export-integration-candidates":
            print(IntegrationCandidateService().export(args.section_bundle, args.output_dir))
            return 0
        if args.command == "export-integration-adjudication":
            print(
                IntegrationAdjudicationBundleService().export(
                    args.candidate_bundle,
                    args.output_dir,
                    prompt_path=args.prompt,
                    schema_path=args.schema,
                )
            )
            return 0
        if args.command == "validate-integration-adjudication":
            validation = IntegrationAdjudicationValidationService().validate_files(
                args.cluster_input,
                args.adjudication_json,
            )
            print(json.dumps(validation, ensure_ascii=False, indent=2))
            return 0
        if args.command == "export-integration-adjudication-v2":
            print(
                IntegrationAdjudicationV2BundleService().export(
                    args.candidate_bundle,
                    args.output_dir,
                    prompt_path=args.prompt,
                    schema_path=args.schema,
                )
            )
            return 0
        if args.command == "assemble-integrated-decisions":
            print(
                IntegratedDecisionAssemblyService().assemble(
                    args.candidate_bundle,
                    args.adjudication_bundle,
                    args.output_dir,
                )
            )
            return 0
        if args.command == "export-signal-analysis":
            print(
                SignalAnalysisBundleService(GinzaSignalAnnotator(args.model)).export(
                    args.analysis_session,
                    args.output_dir,
                    base_prompt_path=args.base_prompt,
                    guidance_path=args.guidance,
                    schema_path=args.schema,
                    baseline_decisions_path=args.baseline_decisions,
                )
            )
            return 0
        if args.command == "export-knowledge-experiment":
            print(
                KnowledgeExperimentBundleService().export(
                    args.analysis_session,
                    args.output_root,
                    prompt_path=args.prompt,
                    knowledge_path=args.knowledge,
                    schema_path=args.schema,
                    control_decisions_path=args.control_decisions,
                )
            )
            return 0
        if args.command == "export-hybrid-section-analysis":
            print(
                HybridSectionBundleService(GinzaSignalAnnotator(args.model)).export(
                    args.analysis_session,
                    args.section_index,
                    args.output_dir,
                    prompt_path=args.prompt,
                    guidance_path=args.guidance,
                    knowledge_path=args.knowledge,
                    schema_path=args.schema,
                )
            )
            return 0
        if args.command == "finalize-hybrid-section-runs":
            print(HybridSectionRunService().finalize(args.bundle_dir))
            return 0
        if args.command == "export-lifecycle-review":
            print(
                LifecycleReviewBundleService().export(
                    args.integrated_decisions,
                    args.section_bundle,
                    args.output_dir,
                    prompt_path=args.prompt,
                    schema_path=args.schema,
                )
            )
            return 0
        if args.command == "apply-lifecycle-adjudication":
            print(
                LifecycleAdjudicationService().apply(
                    args.integrated_decisions,
                    args.review_bundle,
                    args.output_dir,
                )
            )
            return 0

        repo = SQLiteRepository(args.db)
        if args.command == "ingest":
            session_id, report, duplicate = IngestService(repo).ingest(args.jsonl)
            print(json.dumps({"session_id": session_id, "status": "already_ingested" if duplicate else "ingested", "report": report}, ensure_ascii=False, indent=2))
        elif args.command == "export-analysis":
            prompt_path = Path(f"prompts/decision_extraction_{args.prompt_version}.md")
            path = AnalysisBundleService(repo, args.artifacts, prompt_path).export(
                args.session_id,
                projection_version=args.projection_version,
                normalized_messages_path=args.normalized_messages,
                normalized_attachments_path=args.normalized_attachments,
            )
            print(path)
        elif args.command == "import-analysis":
            run_id = AnalysisImportService(repo).import_file(
                args.session_id, args.decisions_json, prompt_version=f"decision_extraction_{args.prompt_version}"
            )
            print(json.dumps({"analysis_run_id": run_id, "status": "imported"}))
        elif args.command == "render":
            print(RenderService(repo, args.artifacts).decisions(args.session_id))
        elif args.command == "validate-decisions-v3":
            result = DecisionV3ValidationService().validate_files(args.analysis_session, args.decisions_json)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (PocError, OSError, ValueError) as exc:
        print(str(exc))
        return 2
