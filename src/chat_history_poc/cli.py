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


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="python -m chat_history_poc")
    result.add_argument("--db", type=Path, default=Path("data/chat_history.db"))
    result.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    sub = result.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("jsonl", type=Path)
    export = sub.add_parser("export-analysis")
    export.add_argument("session_id")
    export.add_argument("--prompt-version", choices=("v1", "v2"), default="v2")
    import_analysis = sub.add_parser("import-analysis")
    import_analysis.add_argument("session_id")
    import_analysis.add_argument("decisions_json", type=Path)
    import_analysis.add_argument("--prompt-version", choices=("v1", "v2"), default="v2")
    render = sub.add_parser("render")
    render.add_argument("session_id")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    repo = SQLiteRepository(args.db)
    try:
        if args.command == "ingest":
            session_id, report, duplicate = IngestService(repo).ingest(args.jsonl)
            print(json.dumps({"session_id": session_id, "status": "already_ingested" if duplicate else "ingested", "report": report}, ensure_ascii=False, indent=2))
        elif args.command == "export-analysis":
            prompt_path = Path(f"prompts/decision_extraction_{args.prompt_version}.md")
            path = AnalysisBundleService(repo, args.artifacts, prompt_path).export(args.session_id)
            print(path)
        elif args.command == "import-analysis":
            run_id = AnalysisImportService(repo).import_file(
                args.session_id, args.decisions_json, prompt_version=f"decision_extraction_{args.prompt_version}"
            )
            print(json.dumps({"analysis_run_id": run_id, "status": "imported"}))
        elif args.command == "render":
            print(RenderService(repo, args.artifacts).decisions(args.session_id))
        return 0
    except (PocError, OSError, ValueError) as exc:
        print(str(exc))
        return 2
