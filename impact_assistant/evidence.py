"""Read-only evidence tools for Python source, tests, and Markdown."""

import ast
from collections import Counter
from dataclasses import dataclass
import math
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from .contracts import METHODS, Change

SKIP_DIRS = {"venv", "node_modules", "__pycache__", "build", "dist", "vendor"}
MAX_BYTES = 512_000
MAX_FILES = 5_000
IDENTIFIERS = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Evidence:
    id: str
    path: str
    line: int
    excerpt: str


def repo_files(root: Path, suffix: str):
    def raise_walk_error(error):
        raise error

    count = 0
    for directory, dirs, names in os.walk(root, onerror=raise_walk_error):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS)
        for name in sorted(names):
            if name.startswith(".") or not name.lower().endswith(suffix):
                continue
            path = Path(directory, name)
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
                continue
            count += 1
            if count > MAX_FILES:
                raise ValueError(f"Repository exceeds the {MAX_FILES} {suffix} file limit")
            with path.open("rb") as stream:
                data = stream.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError(f"File exceeds the {MAX_BYTES} byte limit: {path.relative_to(root)}")
            yield path.relative_to(root).as_posix(), data.decode("utf-8-sig")


def literal_url(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value if isinstance(part, ast.Constant) else "{variable}" for part in node.values
        )
    return None


def matches_route(url: str, route: str) -> bool:
    path = urlsplit(url).path
    if not path.startswith("/"):
        # An interpolated base URL is allowed before a literal route.
        if not path.startswith("{variable}/"):
            return False
        path = path[len("{variable}"):]
    expected, actual = route.split("/"), path.split("/")
    return len(expected) == len(actual) and all(
        bool(value) if re.fullmatch(r"\{[^{}]+\}", segment) else segment == value
        for segment, value in zip(expected, actual)
    )


class PythonSearch:
    def __init__(self, root: Path):
        self.calls: list[tuple[str, int, str, str, str, bool]] = []
        self.warnings = []
        for path, source in repo_files(root, ".py"):
            try:
                tree = ast.parse(source, filename=path)
            except SyntaxError as exc:
                self.warnings.append(f"Could not parse {path}:{exc.lineno}")
                continue
            lines = source.splitlines()
            is_test = (
                "tests" in path.split("/")[:-1]
                or Path(path).name.startswith("test_")
                or Path(path).name.endswith("_test.py")
            )
            for node in sorted(ast.walk(tree), key=lambda n: getattr(n, "lineno", 0)):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                arguments = node.args
                keywords = {item.arg: item.value for item in node.keywords}
                method = node.func.attr.upper()
                if method == "REQUEST":
                    method_node = keywords.get("method", arguments[0] if arguments else None)
                    method = (literal_url(method_node) or "").upper()
                    arguments = arguments[1:]
                if method.lower() not in METHODS:
                    continue
                url = literal_url(keywords.get("url", arguments[0] if arguments else None))
                if not url:
                    continue
                end = min(node.lineno + 7, node.end_lineno + 2)
                snippet = "\n".join(lines[node.lineno - 1:end]).strip()
                self.calls.append((path, node.lineno, method, url, snippet[:500], is_test))

    def search(self, change: Change, *, tests: bool, limit: int = 6) -> list[Evidence]:
        kind = "test" if tests else "code"
        hits = []
        for path, line, method, url, snippet, is_test in self.calls:
            if tests != is_test or method != change.method:
                continue
            try:
                matched = matches_route(url, change.route)
            except ValueError:
                matched = False
            if matched:
                hits.append(Evidence(f"{kind}-{len(hits) + 1}", path, line, snippet))
                if len(hits) == limit:
                    break
        return hits


def tokens(text: str) -> list[str]:
    return IDENTIFIERS.findall(text.lower())


class DocsSearch:
    """An in-memory BM25 index over line-addressable Markdown chunks."""

    def __init__(self, root: Path):
        self.chunks: list[tuple[str, int, str, Counter]] = []
        self.frequency: Counter = Counter()
        total_length = 0
        for path, source in repo_files(root, ".md"):
            lines = source.splitlines()
            for start in range(0, len(lines), 10):
                chunk = "\n".join(lines[start:start + 14])[:1_200].strip()
                counts = Counter(tokens(chunk))
                if counts:
                    self.chunks.append((path, start + 1, chunk, counts))
                    self.frequency.update(counts.keys())
                    total_length += counts.total()
        self.average_length = total_length / max(1, len(self.chunks))

    def search(self, query: str, limit: int = 3) -> list[Evidence]:
        terms = set(tokens(query))
        count = len(self.chunks)
        ranked = []
        for path, line, text, counts in self.chunks:
            norm = 1.2 * (0.25 + 0.75 * counts.total() / self.average_length)
            score = sum(
                math.log1p((count - self.frequency[t] + 0.5) / (self.frequency[t] + 0.5))
                * (counts[t] * 2.2) / (counts[t] + norm)
                for t in sorted(terms & counts.keys())
            )
            if score:
                ranked.append((-score, path, line, text))
        return [
            Evidence(f"doc-{i}", path, line, text)
            for i, (_, path, line, text) in enumerate(sorted(ranked)[:limit], start=1)
        ]
