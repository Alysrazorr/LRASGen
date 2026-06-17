"""
Step 3 — Endpoint identification via LLM.

For each entry file (and its deps) from Step 2, send the cleaned source code
to an LLM and extract the list of REST endpoints: path, HTTP method, method
name, summary, description, and source line number.
"""

import ast
import os
import re
import time

from llm import chat


_PROMPT = """\
## Source Code

```
%s
```

## Questions

1. What endpoints are defined in the "Entry_code" part of the source code? Extract endpoints strictly within the scope of "Entry_code".
2. What is the path of each endpoint?
3. What is the HTTP method of each endpoint?
4. What is the summary of each endpoint?
5. What is the description of each endpoint?
6. What is the line number in the source file where the endpoint method is defined?

## Notices

- One "path" and one "HTTP method" are considered as one "endpoint". If several HTTP methods are marked on one function, list them separately.
- For the Django framework, do not forget configurations in commonViewSet.
- Route parameter expansion: When a route contains a path parameter whose concrete values are enumerated in the Related_code (e.g. via switch-case, if-else chains, or enum lookups), create a SEPARATE endpoint entry for EACH concrete value. For example, if the entry code defines router.post("/object/:type", ...) and the related code shows switch(type) { case "item": ... case "folder": ... }, list /object/item and /object/folder as two separate POST endpoints. Only use a single parameterized route when no concrete values can be found in the provided code.
- For Jersey/JAX-RS sub-resource expansion:
  1. A method annotated with @Path but WITHOUT an HTTP method annotation (@GET/@POST/@PUT/@DELETE/@PATCH/@HEAD/@OPTIONS) is a sub-resource locator. It routes to a sub-resource class and is NOT an endpoint itself.
  2. For each sub-resource locator, identify its return type (the sub-resource class), then find that class in the Related_code.
  3. Extract all actual endpoints from the sub-resource class: methods that have an HTTP method annotation. Combine the sub-resource locator's @Path as the prefix, then append the sub-resource method's @Path (if any). The sub-resource class may have NO class-level @Path — its full path is inherited from the locator method.
  4. Recursively expand: if the sub-resource class contains further sub-resource locators, follow steps 2-4 for each.
  5. Also check parent classes (via "extends") of the sub-resource class for any additional HTTP-annotated methods — these also produce endpoints under the combined path.
  6. This rule applies to all JAX-RS frameworks (Jersey, JDK, Spring Boot with JAX-RS annotations).
- For Python and JavaScript frameworks (Flask, Django, Tornado, Web.py, Express, NestJS, Koa): if multiple classes are defined in the same file, prefix the method name with the class name (e.g. "GrampsObjectResource.get" instead of just "get") so that each endpoint method is uniquely identifiable.

## Rules

- You must extract information from the specified code to answer the questions.
- You must answer the questions according to the JSON format: %s."""


# JSON schema for structured output
_SCHEMA = {
    "type": "object",
    "properties": {
        "endpoints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "endpoint_path": {"type": "string", "description": "URI path, e.g. /api/users/{id}"},
                    "http_method": {"type": "string", "description": "GET, POST, PUT, DELETE, PATCH, etc."},
                    "method_name": {"type": "string", "description": "function/method name, e.g. getUser"},
                    "summary": {"type": "string", "description": "short summary"},
                    "description": {"type": "string", "description": "detailed description"},
                    "line_number": {"type": "integer", "description": "line number where the endpoint method is defined"},
                },
                "required": ["endpoint_path", "http_method", "method_name"],
            },
        },
    },
    "required": ["endpoints"],
}


_JAXRS_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}


def _resolve_constants(code):
    """Extract String constant definitions from Java code. Returns {NAME: "value"}."""
    constants = {}
    for m in re.finditer(
        r'(?:public\s+)?(?:static\s+)?(?:final\s+)?String\s+(\w+)\s*=\s*"([^"]+)"\s*;',
        code,
    ):
        constants[m.group(1)] = m.group(2)
    return constants


def _extract_path_value(ann_block, constants):
    """
    Extract the path value from a @Path annotation block.
    Handles both @Path("literal") and @Path(CONSTANT).
    """
    m = re.search(r'@Path\("([^"]+)"\)', ann_block)
    if m:
        return m.group(1)
    m = re.search(r'@Path\((\w+)\)', ann_block)
    if m and m.group(1) in constants:
        return constants[m.group(1)]
    return ""


def _expand_sub_resources(entry_code, deps):
    """
    Pre-process JAX-RS entry code: detect sub-resource locator methods and
    inline the referenced sub-resource classes so the LLM can see the full
    endpoint chain without guessing.

    A sub-resource locator is a method with @Path but NO HTTP method annotation
    (e.g. @Path("{id}") public SubResource getSub()).  The actual endpoints
    live inside SubResource, which may have no class-level @Path.
    """
    if not deps or len(deps) <= 1:
        return entry_code

    # Index dep classes by simple class name
    dep_classes = {}
    for dep_path, dep_code in deps.items():
        if dep_path == "entry_code_file":
            continue
        for m in re.finditer(r"(?:public\s+)?class\s+(\w+)", dep_code):
            dep_classes[m.group(1)] = dep_code

    if not dep_classes:
        return entry_code

    # Resolve constants in entry_code for @Path(CONSTANT) references
    entry_constants = _resolve_constants(entry_code)

    expanded = entry_code
    seen = set()

    def _expand(code, path_prefix):
        nonlocal expanded
        local_constants = _resolve_constants(code)
        all_constants = {**entry_constants, **local_constants}
        for m in re.finditer(
            r"((?:@\w+(?:\([^)]*\))?\s*)+)"     # annotation block
            r"(public|protected|private)\s+"
            r"(?:static\s+)?(?:final\s+)?"
            r"(\w+)\s+"                           # return type (group 3)
            r"(\w+)\s*\(",                         # method name  (group 4)
            code,
        ):
            ann_block = m.group(1)
            return_type = m.group(3)
            method_name = m.group(4)

            has_path = "@Path" in ann_block
            has_http = any(f"@{a}" in ann_block for a in _JAXRS_HTTP_METHODS)

            if has_path and not has_http:
                sub_path = _extract_path_value(ann_block, all_constants)
                if not sub_path:
                    continue
                full_prefix = f"{path_prefix}/{sub_path}".replace("//", "/")

                if return_type in dep_classes and return_type not in seen:
                    sub_code = dep_classes[return_type]
                    # Skip only if the sub-resource has a CLASS-LEVEL @Path
                    # (right before "class ClassName"), meaning it is already a
                    # stand-alone entry file. Method-level @Path annotations inside
                    # the class body do NOT make it an entry file.
                    if re.search(r'@Path\([^)]+\)\s*\n\s*public\s+class\s+\w+', sub_code):
                        continue
                    seen.add(return_type)
                    header = (
                        f"\n// ===== SUB-RESOURCE: {return_type} (reached via "
                        f'"{method_name}()" -> prefix "{full_prefix}") =====\n'
                        f"// IMPORTANT: {return_type} has NO class-level @Path.\n"
                        f'// All its endpoints inherit the prefix "{full_prefix}".\n'
                    )
                    expanded += header + sub_code
                    # Recurse into sub-resource for further sub-resource locators
                    _expand(sub_code, full_prefix)

    _expand(entry_code, "")
    return expanded


def _assemble_codes(entry_file_path, deps):
    """Format the entry code + related dependency codes for the prompt."""
    codes = f'Entry_code({entry_file_path}):\n<<<\n{deps["entry_code_file"]}\n>>>\n'
    for key, code in deps.items():
        if key != "entry_code_file":
            codes += f'\nRelated_code({key}):\n<<<\n{code}\n>>>\n'
    return codes


_PY_CLASS_FRAMEWORKS = {"flask", "django", "tornado", "webpy"}


def _resolve_py_method_names(entry_file_path, raw_endpoints):
    """For Python class-based frameworks, prefix method names with class name."""
    if not entry_file_path.endswith('.py'):
        return raw_endpoints
    try:
        with open(entry_file_path, 'r', encoding='utf-8', errors='replace') as f:
            source = f.read()
    except Exception:
        return raw_endpoints

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return raw_endpoints

    # Build map: method_name -> class_name (for file-level unique methods)
    method_to_class = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    method_to_class[item.name] = node.name

    for ep in raw_endpoints:
        mn = ep.get('method_name', '')
        if mn in method_to_class:
            ep['method_name'] = f"{method_to_class[mn]}.{mn}"

    return raw_endpoints


def _extract_endpoints(entry_file_path, deps, provider, temperature, cross_validate=False):
    """Send one entry file + deps to LLM, parse endpoint list."""
    # Pre-process: expand JAX-RS sub-resource chains so the LLM sees the full
    # endpoint hierarchy in one flattened code block.
    if entry_file_path.endswith(".java"):
        deps["entry_code_file"] = _expand_sub_resources(
            deps["entry_code_file"], deps
        )
    codes = _assemble_codes(entry_file_path, deps)
    schema_str = str(_SCHEMA).replace("'", '"')
    prompt = _PROMPT % (codes, schema_str)

    if cross_validate:
        from llm import cross_validate as cv
        response, meta = cv([{"role": "user", "content": prompt}], temperature=temperature)
    else:
        response = chat(
            [{"role": "user", "content": prompt}],
            provider=provider,
            temperature=temperature,
            max_retries=3,
        )

    raw_endpoints = response.get("endpoints", [])
    # Resolve class-prefixed method names for Python class-based frameworks
    raw_endpoints = _resolve_py_method_names(entry_file_path, raw_endpoints)
    # normalise + dedup by (path, method)
    endpoints = []
    seen = set()
    for ep in raw_endpoints:
        path = ep.get("endpoint_path", "").strip()
        method = ep.get("http_method", "").upper().strip()
        # Normalise path: strip trailing slash, collapse double slashes
        path = path.rstrip("/")
        path = re.sub(r'/+', '/', path)
        if not path.startswith("/"):
            path = "/" + path
        # Normalise Tornado regex groups to {param} syntax
        # (?P<name>[^/]+) → {name}, ([^/]+) → {param}, (.*) → {path}
        path = re.sub(r'\(\?P<(\w+)>[^)]+\)', r'{\1}', path)
        path = re.sub(r'\(\[\^/\]\+\)', r'{param}', path)
        path = re.sub(r'\(\.\*\)', r'{path}', path)
        key = (path, method)
        if key in seen:
            continue
        seen.add(key)
        endpoints.append({
            "endpoint_path": path,
            "http_method": method,
            "method_name": ep.get("method_name", ""),
            "summary": ep.get("summary"),
            "description": ep.get("description"),
            "line_number": ep.get("line_number"),
            "source_file": entry_file_path,
        })
    return endpoints



def main(api, step2_result, provider="openrouter", temperature=0.2, cross_validate=False):
    """
    Identify endpoints for all entry files via LLM.

    Args:
        api: dict with name, framework, etc.
        step2_result: dict from step2 with "entry_to_deps"
        cross_validate: if True, use 3-LLM voting (Section 4.1)

    Returns:
        dict ready to save as step3_endpoints.json
    """
    framework = api["framework"]
    entry_to_deps = step2_result.get("entry_to_deps", {})
    start = time.time()
    cv_mode = cross_validate

    # For Django, also load the urls.py content so the LLM can see router.register() calls
    extra_context = None
    if framework == "django" and "config_file" in api:
        cf = api["config_file"]
        if os.path.isfile(cf):
            with open(cf, "r", encoding="utf-8") as f:
                extra_context = f"# Django URL configuration ({cf}):\n{f.read()}\n"

    all_endpoints = []
    seen = set()
    llm_calls = 0

    for entry_file_path, deps in entry_to_deps.items():
        fname = os.path.basename(entry_file_path)
        print(f"    processing entry: {fname}")
        try:
            if extra_context:
                deps = dict(deps)
                deps["entry_code_file"] = extra_context + "\n" + deps["entry_code_file"]
            endpoints = _extract_endpoints(entry_file_path, deps, provider, temperature,
                                           cross_validate=cv_mode)
            # cross-file dedup
            for ep in endpoints:
                key = (ep["endpoint_path"], ep["http_method"])
                if key not in seen:
                    seen.add(key)
                    all_endpoints.append(ep)
            llm_calls += 1
        except Exception as e:
            print(f"    [ERROR] {entry_file_path}: {e}")
            continue

    # Tornado: keep only /api/ routes (filter out static/infra/websocket handlers)
    if framework == "tornado":
        all_endpoints = [ep for ep in all_endpoints
                         if ep["endpoint_path"].startswith("/api/")
                         or ep["endpoint_path"] == "/api"]

    return {
        "task_id": None,
        "api_name": api["name"],
        "framework": framework,
        "endpoints": all_endpoints,
        "duration_ms": round((time.time() - start) * 1000),
    }
