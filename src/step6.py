"""
Step 6 — OAS assembly.

Programmatically assemble the endpoint, parameter, response, and constraint
data from Steps 3-5 into a valid OpenAPI 3.1.1 specification.
"""

import json
import os
import re


def _safe_type(t):
    """Normalise parameter types to valid OpenAPI types."""
    if not t:
        return "string"
    t = str(t).lower()
    type_map = {
        "int": "integer", "integer": "integer", "long": "integer",
        "float": "number", "double": "number", "number": "number",
        "bool": "boolean", "boolean": "boolean",
        "str": "string", "string": "string",
        "object": "object", "array": "array",
        "nestedrequest": "object", "body": "object",
        "file": "string",
    }
    return type_map.get(t, "string")


def _clean_path(path):
    if not path:
        return "/"
    p = path.strip()
    if not p.startswith("/"):
        p = "/" + p
    p = p.rstrip("/")
    return p if p else "/"


def _build_operation_id(method, path):
    parts = [s for s in path.strip("/").split("/") if s and not s.startswith("{")]
    if parts:
        base = "".join(w.capitalize() for w in re.split(r"[-_]", parts[-1]))
    else:
        base = "Root"
    prefixes = {"get": "get", "post": "create", "put": "update", "patch": "patch",
                "delete": "delete", "head": "head", "options": "options"}
    prefix = prefixes.get(method.lower(), method.lower())
    return prefix + base if parts else prefix


def _build_parameter(param):
    schema = {"type": _safe_type(param.get("type"))}
    if param.get("description"):
        schema["description"] = param.get("description")
    if param.get("format"):
        schema["format"] = param.get("format")
    try:
        if param.get("min") is not None:
            schema["minimum"] = float(param["min"])
    except (ValueError, TypeError):
        pass
    try:
        if param.get("max") is not None:
            schema["maximum"] = float(param["max"])
    except (ValueError, TypeError):
        pass
    try:
        if param.get("min_length") is not None:
            schema["minLength"] = int(param["min_length"])
    except (ValueError, TypeError):
        pass
    try:
        if param.get("max_length") is not None:
            schema["maxLength"] = int(param["max_length"])
    except (ValueError, TypeError):
        pass
    if param.get("default_value") is not None:
        schema["default"] = param.get("default_value")
    if param.get("enum"):
        if isinstance(param["enum"], list):
            schema["enum"] = param["enum"]
        elif isinstance(param["enum"], str):
            schema["enum"] = [x.strip() for x in param["enum"].split(",") if x.strip()]
    if param.get("dictionary"):
        if isinstance(param["dictionary"], list):
            schema["enum"] = [str(x) for x in param["dictionary"]]
    position = str(param.get("position", "query")).lower()
    if position == "body":
        return None
    required = str(param.get("require", "false")).lower() == "true"
    return {
        "name": param.get("name", "unknown"),
        "in": position,
        "required": required,
        "description": param.get("description"),
        "schema": schema,
    }


def _build_request_body(params):
    body_params = [p for p in params if str(p.get("position", "")).lower() == "body"]
    if not body_params:
        return None
    props = {}
    required_list = []
    for p in body_params:
        name = p.get("name", "body")
        props[name] = {
            "type": _safe_type(p.get("type")),
            "description": p.get("description"),
        }
        if str(p.get("require", "false")).lower() == "true":
            required_list.append(name)
    return {
        "required": len(required_list) > 0,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": props,
                    "required": required_list if required_list else None,
                }
            }
        },
    }


def _build_responses(responses):
    if not responses:
        return {"200": {"description": "Successful response"}}
    result = {}
    for r in responses:
        code = str(r.get("status_code", "200"))
        entry = {"description": r.get("description", "")}
        schema = r.get("data_schema")
        if schema:
            if isinstance(schema, str):
                try:
                    schema = json.loads(schema)
                except Exception:
                    schema = None
            if schema and isinstance(schema, (list, dict)):
                entry["content"] = {"application/json": {"schema": _normalise_schema(schema)}}
        if "content" not in entry and r.get("description"):
            pass
        result[code] = entry
    if "200" not in result:
        result["200"] = {"description": "Successful response"}
    return result


def _normalise_schema(schema):
    if isinstance(schema, list):
        props = {}
        for item in schema:
            if isinstance(item, dict):
                name = item.get("name", "unknown")
                inner = item.get("schema", item.get("properties", {}))
                if isinstance(inner, dict):
                    props[name] = {"type": _safe_type(str(inner)) if not isinstance(inner, dict) else "string",
                                   "description": str(inner) if not isinstance(inner, dict) else str(inner)}
        return {"type": "object", "properties": props} if props else {"type": "object"}
    if isinstance(schema, dict):
        return schema
    return {"type": "object"}


def generate_oas(api, step_result):
    oas = {
        "openapi": "3.1.1",
        "info": {
            "title": api["name"] + " API",
            "description": f"LRASGen-generated specification for {api['name']} ({api['framework']}).",
            "version": "1.0.0",
        },
        "servers": [{"url": "/"}],
        "paths": {},
        "components": {"schemas": {}},
    }

    for ep in step_result.get("endpoints", []):
        path = _clean_path(ep.get("endpoint_path", "/"))
        method = str(ep.get("http_method", "get")).lower()
        if method not in ("get", "post", "put", "delete", "patch", "head", "options"):
            continue

        params = ep.get("parameters", [])
        responses = ep.get("responses", [])

        openapi_params = []
        for p in params:
            built = _build_parameter(p)
            if built:
                openapi_params.append(built)

        operation = {
            "operationId": _build_operation_id(method, path),
            "summary": ep.get("summary"),
            "description": ep.get("description"),
            "parameters": openapi_params if openapi_params else [],
            "responses": _build_responses(responses),
        }

        body = _build_request_body(params)
        if body:
            operation["requestBody"] = body

        if path not in oas["paths"]:
            oas["paths"][path] = {}
        oas["paths"][path][method] = operation

    for path in list(oas["paths"].keys()):
        for method in list(oas["paths"][path].keys()):
            if not oas["paths"][path][method].get("parameters"):
                del oas["paths"][path][method]["parameters"]
            if not oas["paths"][path][method].get("responses"):
                oas["paths"][path][method]["responses"] = {"200": {"description": "Successful response"}}

    if not oas["components"]["schemas"]:
        del oas["components"]

    return oas


def main(api, step_result, output_dir=None, enable_validate=False):
    oas = generate_oas(api, step_result)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, "generated_oas.json")
    else:
        filepath = "generated_oas.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(oas, f, ensure_ascii=False, indent=2)

    if enable_validate:
        _validate_oas(filepath)

    return filepath


def _validate_oas(oas_path):
    """Validate generated OAS against OpenAPI 3.1.1 schema (Section 4.1, OAS compliance check)."""
    try:
        from openapi_schema_validator import validate
        with open(oas_path, "r", encoding="utf-8") as f:
            oas = json.load(f)
        validate(oas, "3.1.1")
        print(f"  OAS compliance check: PASSED ({oas_path})")
    except Exception as e:
        print(f"  OAS compliance check: FAILED — {str(e)[:300]}")
