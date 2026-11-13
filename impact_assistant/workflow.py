"""Run the source, test, and documentation specialists in parallel."""

from dataclasses import asdict
from typing import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph

from .agents import Investigator, checked_findings
from .contracts import Change
from .evidence import DocsSearch, Evidence, PythonSearch


class Investigation(TypedDict):
    change: Change
    code: NotRequired[dict]
    tests: NotRequired[dict]
    docs: NotRequired[dict]
    report: NotRequired[dict]


def build_graph(code: PythonSearch, docs: DocsSearch, investigator: Investigator | None):
    def inspect(change: Change, role: str, evidence: list[Evidence]) -> dict:
        findings = []
        if investigator is not None and evidence:
            assessment = investigator.investigate(change, role, evidence)
            findings = [item.model_dump() for item in checked_findings(assessment, evidence)]
        return {"evidence": [asdict(item) for item in evidence], "findings": findings}

    def code_agent(state: Investigation):
        change = state["change"]
        return {"code": inspect(change, "consumer code", code.search(change, tests=False))}

    def test_agent(state: Investigation):
        change = state["change"]
        return {"tests": inspect(change, "test coverage", code.search(change, tests=True))}

    def docs_agent(state: Investigation):
        change = state["change"]
        query = " ".join(filter(None, (change.route, change.field, change.status)))
        return {"docs": inspect(change, "migration documentation", docs.search(query))}

    def summarize(state: Investigation):
        change = state["change"]
        has_calls = bool(state["code"]["evidence"] or state["tests"]["evidence"])
        question = {
            "operation_removed": "Which replacement operation preserves the consumer's behavior?",
            "required_request_field_added": f"Does the final request always supply a valid {change.field!r}?",
            "response_field_removed": f"Which runtime paths still read {change.field!r} from status {change.status}?",
        }[change.kind]
        open_questions = [question] if has_calls else [
            "Does a shared client, generated SDK, or dynamic URL call this operation?"
        ]
        if not state["tests"]["evidence"]:
            open_questions.append("Which tests exercise this operation through indirect calls?")
        if not state["docs"]["evidence"]:
            open_questions.append("Is there a migration guide or internal note for this change?")
        next_check = {
            "operation_removed": "Find the replacement operation and test the migration in a sandbox.",
            "required_request_field_added": f"Trace request construction and test requests with and without {change.field!r}.",
            "response_field_removed": f"Trace readers of {change.field!r} and test against a response without it.",
        }[change.kind]
        if not has_calls:
            next_check = "Check shared clients, generated SDKs, and dynamically constructed URLs for usage."
        return {"report": {
            "change": asdict(change), "description": change.description,
            "impact": "Potential impact" if has_calls else "No direct usage found",
            "open_questions": open_questions,
            "next_check": next_check,
            "specialists": {key: state[key] for key in ("code", "tests", "docs")},
        }}

    graph = StateGraph(Investigation)
    graph.add_node("code", code_agent)
    graph.add_node("tests", test_agent)
    graph.add_node("docs", docs_agent)
    graph.add_node("report", summarize)
    for specialist in ("code", "tests", "docs"):
        graph.add_edge(START, specialist)
    graph.add_edge(["code", "tests", "docs"], "report")
    graph.add_edge("report", END)
    return graph.compile()
