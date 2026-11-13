from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from impact_assistant.__main__ import main, markdown
from impact_assistant.agents import Assessment, OllamaInvestigator
from impact_assistant.contracts import Change, compare, load_spec
from impact_assistant.evidence import DocsSearch, PythonSearch
from impact_assistant.workflow import build_graph

FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "payments"
ARGS = [str(FIXTURE / name) for name in ("before.yaml", "after.yaml", "consumer")]


class WorkflowTests(unittest.TestCase):
    def test_cli_reports_three_changes_with_the_correct_evidence(self):
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([*ARGS, "--format", "json"]), 0)
        report = json.loads(output.getvalue())
        entries = {item["change"]["kind"]: item for item in report["changes"]}
        self.assertEqual(set(entries), {
            "operation_removed", "required_request_field_added", "response_field_removed",
        })
        removed = entries["operation_removed"]
        self.assertEqual(removed["impact"], "No direct usage found")
        self.assertEqual(removed["specialists"]["code"]["evidence"], [])
        self.assertEqual(removed["specialists"]["tests"]["evidence"], [])
        self.assertTrue(any("dynamic URL" in question for question in removed["open_questions"]))
        required = entries["required_request_field_added"]
        self.assertEqual(required["change"]["field"], "currency")
        self.assertEqual(required["impact"], "Potential impact")
        self.assertEqual(required["specialists"]["code"]["evidence"][0]["path"], "payments.py")
        self.assertEqual(required["specialists"]["tests"]["evidence"][0]["path"], "tests/test_payments.py")
        self.assertIn("currency", required["specialists"]["docs"]["evidence"][0]["excerpt"])
        self.assertTrue(any("currency" in question for question in required["open_questions"]))
        self.assertEqual(entries["response_field_removed"]["change"]["field"], "receipt_url")
        self.assertIn("payments.py:2", markdown(report))
        self.assertIn("### Open questions", markdown(report))

    def test_identical_specs_have_no_changes(self):
        spec = load_spec(FIXTURE / "before.yaml")
        self.assertEqual(compare(spec, spec), ([], []))

    def test_invalid_input_exits_without_partial_report(self):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(["does-not-exist.yaml", *ARGS[1:]]), 1)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("Error:", err.getvalue())

    def test_fstring_route_matches_without_matching_similar_paths(self):
        source = (
            'client.get(f"{base_url}/accounts/{id}")\n'
            'client.get("/accounting/123")\n'
            'client.post("/accounts/123")\n'
        )
        with patch("impact_assistant.evidence.repo_files", return_value=[("client.py", source)]):
            index = PythonSearch(FIXTURE / "consumer")
        result = index.search(Change("GET", "/accounts/{id}", "operation_removed"), tests=False)
        self.assertEqual([item.line for item in result], [1])

    def test_model_findings_are_validated_against_each_specialists_evidence(self):
        class WrongCitation:
            def investigate(self, change, role, evidence):
                return Assessment.model_validate({"findings": [{
                    "evidence_ids": ["fake-1"], "observation": "An invented finding", "next_check": "Review",
                }]})

        root = FIXTURE / "consumer"
        graph = build_graph(PythonSearch(root), DocsSearch(root), WrongCitation())
        with self.assertRaisesRegex(ValueError, "unknown evidence ID"):
            graph.invoke({"change": Change("POST", "/payments", "required_request_field_added", "currency")})

    @patch("impact_assistant.agents.build_opener")
    def test_ollama_adapter_requests_structured_output_and_report_cites_evidence(self, opener):
        root = FIXTURE / "consumer"

        def respond(http_request, timeout):
            payload = json.loads(http_request.data)
            context = json.loads(payload["messages"][1]["content"])
            self.assertIn("findings", payload["format"]["properties"])
            response = {"findings": [{
                "evidence_ids": [context["evidence"][0]["id"]],
                "observation": "Review the cited candidate.", "next_check": "Confirm request construction.",
            }]}
            return StringIO(json.dumps({"message": {"content": json.dumps(response)}}))

        request = opener.return_value.open
        request.side_effect = respond
        graph = build_graph(PythonSearch(root), DocsSearch(root), OllamaInvestigator("test-model"))
        report = graph.invoke({"change": Change("POST", "/payments", "required_request_field_added", "currency")})["report"]
        self.assertEqual(request.call_count, 3)
        for branch in ("code", "docs", "tests"):
            result = report["specialists"][branch]
            self.assertEqual(result["findings"][0]["evidence_ids"], [result["evidence"][0]["id"]])
