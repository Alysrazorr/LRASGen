
import json
import os
import re

import logger


def _safe_type(t):
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
    # "required" is a list of names in OpenAPI 3.1, so a body with no required
    # field omits it rather than carrying a null, and a name that reaches the
    # list twice is recorded once.
    schema = {"type": "object", "properties": props}
    if required_list:
        schema["required"] = list(dict.fromkeys(required_list))
    return {
        "required": len(required_list) > 0,
        "content": {"application/json": {"schema": schema}},
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


def _walk_schemas(node, where=""):
    """Yield every schema object the document carries, with its location."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "schema" and isinstance(value, dict):
                yield where, value
            yield from _walk_schemas(value, f"{where}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _walk_schemas(value, f"{where}/{i}")


def validate_oas(oas):
    """Check the generated document against the OpenAPI 3.1 schema vocabulary.

    Each schema object the document carries is checked against the OpenAPI 3.1
    dialect, together with the fields the document itself has to carry. Returns
    the problems found, so an empty list means the document is compliant.
    """
    from openapi_schema_validator import OAS31Validator

    problems = []
    for field in ("openapi", "info", "paths"):
        if field not in oas:
            problems.append(f"missing required field: {field}")
    if oas.get("openapi") != "3.1.1":
        problems.append(f"openapi is {oas.get('openapi')!r}, expected '3.1.1'")
    for where, schema in _walk_schemas(oas):
        try:
            OAS31Validator.check_schema(schema)
        except Exception as exc:
            problems.append(f"{where}: {exc}")
    return problems


def main(api, step_result, output_dir=None):
    oas = generate_oas(api, step_result)

    problems = validate_oas(oas)
    if problems:
        logger.warn(f"OAS compliance check found {len(problems)} problem(s) in "
                    f"{api['name']}: {'; '.join(problems[:3])}")
    else:
        logger.info(f"OAS compliance check passed for {api['name']}.")

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, "generated_oas.json")
    else:
        filepath = "generated_oas.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(oas, f, ensure_ascii=False, indent=2)

    return filepath
