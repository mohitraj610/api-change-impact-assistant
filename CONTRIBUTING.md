# Contributing

For a bug report, include the command, Python version, expected result, and actual result. A minimal synthetic OpenAPI pair and a small consumer snippet are helpful for reproducing issues. Remove credentials and private source excerpts from reports.

For a pull request, describe the behavior it changes and run the test suite from the repository root:

```sh
uv sync --locked
uv run --locked python -m unittest discover -s tests -v
```

For a new detection or matching rule, include a small regression fixture and document its supported cases. Keep tests independent of live APIs and downloaded model weights.
