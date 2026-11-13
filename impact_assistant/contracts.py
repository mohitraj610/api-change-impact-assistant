"""Deterministic checks for a documented subset of OpenAPI 3.x."""

from dataclasses import dataclass
from pathlib import Path

import yaml

METHODS = frozenset("get put post delete options head patch trace".split())


@dataclass(frozen=True)
class Change:
    method: str
    route: str
    kind: str
    field: str = ""
    status: str = ""

    @property
    def description(self) -> str:
        if self.kind == "operation_removed":
            return "Operation removed"
        if self.kind == "required_request_field_added":
            return f"JSON request field {self.field!r} became required"
        return f"JSON response field {self.field!r} removed from status {self.status}"


def load_spec(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as stream:
        spec = yaml.safe_load(stream)
    if not isinstance(spec, dict) or not str(spec.get("openapi", "")).startswith("3."):
        raise ValueError(f"{path.name}: expected an OpenAPI 3.x document")
    if not isinstance(spec.get("paths"), dict):
        raise ValueError(f"{path.name}: expected a paths object")
    return spec


def resolve(spec: dict, obj: dict) -> dict:
    seen = set()
    while isinstance(obj, dict) and "$ref" in obj:
        ref = obj["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/") or ref in seen:
            raise ValueError(f"Unsupported external or circular reference: {ref}")
        seen.add(ref)
        obj = spec
        try:
            for token in ref[2:].split("/"):
                obj = obj[token.replace("~1", "/").replace("~0", "~")]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"Unresolved reference: {ref}") from exc
    if not isinstance(obj, dict):
        raise ValueError("Expected an OpenAPI object")
    return obj


def operations(spec: dict) -> dict:
    result = {}
    for route, path_item in spec["paths"].items():
        if not isinstance(route, str) or not route.startswith("/"):
            continue
        for method, operation in resolve(spec, path_item).items():
            if method in METHODS:
                result[(route, method.upper())] = resolve(spec, operation)
    return result


def json_schema(spec: dict, envelope: dict) -> dict | None:
    content = resolve(spec, envelope).get("content", {})
    if not isinstance(content, dict):
        raise ValueError("Expected an OpenAPI content object")
    if "application/json" not in content:
        return None
    media = resolve(spec, content["application/json"])
    return resolve(spec, media["schema"]) if "schema" in media else None


def simple_object(schema: dict | None) -> bool:
    return schema is not None and schema.get("type") == "object" and not any(
        key in schema for key in ("allOf", "oneOf", "anyOf", "not", "if", "dependentSchemas")
    )


def required_fields(spec: dict, schema: dict) -> set[str]:
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    if not isinstance(properties, dict) or not isinstance(required, list) or not all(
        isinstance(field, str) for field in required
    ):
        raise ValueError("Expected object properties and a list of required field names")
    return {field for field in required if not resolve(spec, properties.get(field, {})).get("readOnly")}


def compare(old: dict, new: dict) -> tuple[list[Change], list[str]]:
    old_ops, new_ops = operations(old), operations(new)
    changes, warnings = [], []
    for route, method in sorted(old_ops):
        previous = old_ops[route, method]
        current = new_ops.get((route, method))
        if current is None:
            changes.append(Change(method, route, "operation_removed"))
            continue

        old_body = json_schema(old, previous.get("requestBody", {}))
        new_body = json_schema(new, current.get("requestBody", {}))
        if simple_object(old_body) and simple_object(new_body):
            added = required_fields(new, new_body) - required_fields(old, old_body)
            changes.extend(Change(method, route, "required_request_field_added", f) for f in sorted(added))
        elif old_body is not None or new_body is not None:
            warnings.append(f"{method} {route}: request JSON schemas are outside the supported subset")

        old_responses = previous.get("responses", {})
        new_responses = current.get("responses", {})
        if not isinstance(old_responses, dict) or not isinstance(new_responses, dict):
            raise ValueError("Expected OpenAPI responses objects")
        old_responses = {str(key): value for key, value in old_responses.items()}
        new_responses = {str(key): value for key, value in new_responses.items()}
        for status in sorted(old_responses.keys() & new_responses.keys()):
            if len(status) != 3 or not status.isdigit() or not status.startswith("2"):
                continue
            old_body = json_schema(old, old_responses[status])
            new_body = json_schema(new, new_responses[status])
            if simple_object(old_body) and simple_object(new_body):
                old_properties, new_properties = old_body.get("properties", {}), new_body.get("properties", {})
                if not isinstance(old_properties, dict) or not isinstance(new_properties, dict):
                    raise ValueError("Expected object properties")
                removed = old_properties.keys() - new_properties.keys()
                changes.extend(
                    Change(method, route, "response_field_removed", field, status)
                    for field in sorted(removed)
                    if not resolve(old, old_properties[field]).get("writeOnly")
                )
            elif old_body is not None or new_body is not None:
                warnings.append(f"{method} {route} {status}: response JSON schemas are outside the supported subset")
    return changes, warnings
