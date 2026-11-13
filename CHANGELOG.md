# Changelog

## v0.1.0

Initial public release of the read-only API change review CLI.

- Compare OpenAPI 3.x contracts for removed operations, newly required top-level JSON request properties, and removed top-level JSON response properties on matching explicit success statuses.
- Run parallel LangGraph investigations for Python call sites, test calls, and Markdown documentation. Enable local Ollama for optional specialist findings with evidence references.
- Export Markdown and JSON reports with file and line references, open questions, and suggested migration checks.
- Run the bundled synthetic payments example and automated tests without API credentials.

See [coverage](README.md#coverage) for the limits of contract and call-site matching.
