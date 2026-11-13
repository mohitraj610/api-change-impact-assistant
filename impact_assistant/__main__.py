"""Command line entry point."""

import argparse
import json
from pathlib import Path
import re
import sys

import yaml

from .agents import OllamaInvestigator
from .contracts import compare, load_spec
from .evidence import DocsSearch, PythonSearch
from .workflow import build_graph


def markdown(report: dict) -> str:
    def inline(text: str) -> str:
        text = " ".join(text.split())
        fence = "`" * (1 + max((len(run) for run in re.findall(r"`+", text)), default=0))
        return f"{fence} {text} {fence}"

    contracts = report["contracts"]
    lines = [
        "# API change impact report", "", f"Mode: {inline(report['mode'])}",
        f"Contracts: {inline(contracts['old'])} to {inline(contracts['new'])}", "",
    ]
    for warning in report["warnings"]:
        lines.append(f"- Coverage warning: {inline(warning)}")
    if not report["changes"]:
        lines.extend(["", "No changes detected within the supported checks."])
    for entry in report["changes"]:
        change = entry["change"]
        lines.extend(["", f"## {inline(change['method'] + ' ' + change['route'])}", "",
                      f"- Contract change: {inline(entry['description'])}",
                      f"- Assessment: **{entry['impact']}**",
                      f"- Next check: {inline(entry['next_check'])}"])
        lines.extend(["", "### Open questions", ""])
        lines.extend(f"- {inline(question)}" for question in entry["open_questions"])
        for role, result in entry["specialists"].items():
            if result["evidence"]:
                lines.extend(["", f"### {role.capitalize()} evidence", ""])
            for evidence in result["evidence"]:
                location = f"{evidence['path']}:{evidence['line']}"
                lines.append(f"- **{evidence['id']}** {inline(location)}: {inline(evidence['excerpt'])}")
            for finding in result["findings"]:
                references = ", ".join(finding["evidence_ids"])
                lines.append(f"- Model suggestion for review ({references}): {inline(finding['observation'])}")
                lines.append(f"  - Verify: {inline(finding['next_check'])}")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review API changes against a local Python consumer.")
    parser.add_argument("old", type=Path, help="Old OpenAPI YAML or JSON file")
    parser.add_argument("new", type=Path, help="New OpenAPI YAML or JSON file")
    parser.add_argument("consumer", type=Path, help="Consumer repository directory")
    parser.add_argument("--ollama-model", help="Optional installed local model for specialist findings")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)
    try:
        root = args.consumer.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Consumer must be a directory")
        changes, warnings = compare(load_spec(args.old), load_spec(args.new))
        mode = args.ollama_model or "evidence only"
        entries = []
        if changes:
            code = PythonSearch(root)
            warnings.extend(code.warnings)
            model = OllamaInvestigator(args.ollama_model) if args.ollama_model else None
            graph = build_graph(code, DocsSearch(root), model)
            entries = [graph.invoke({"change": change})["report"] for change in changes]
        report = {
            "mode": mode,
            "contracts": {"old": args.old.name, "new": args.new.name},
            "warnings": warnings,
            "changes": entries,
        }
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(markdown(report), end="")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(errors="backslashreplace")
    raise SystemExit(main())
