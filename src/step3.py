
import ast
import os
import re
import time

import llm
from llm import ask
from normalize import endpoint_entities, rebuild_endpoints
from step2 import is_sun_handler


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


_SUN_PROMPT = """\
## Source Code

```
%s
```

## Questions

The code above is a com.sun.net.httpserver handler together with the helpers it
routes to. Such a handler routes requests imperatively, without annotations.
Identify every REST endpoint it serves.

1. What is the path of each endpoint?
2. What is the HTTP method of each endpoint?
3. What is the summary of each endpoint?
4. What is the description of each endpoint?
5. What is the line number at which the endpoint is dispatched?

## Notices

- Path patterns appear as string comparisons on the request path:
  * `path.equals("languages")` or `pathWithoutVersion.equals("check")` is an exact sub-path.
  * `path.startsWith("/v2/...")` is a prefix match.
  * A base prefix removed earlier with `.substring("/v2/".length())` is part of the path.
- The HTTP method comes from a `httpExchange.getRequestMethod()` check, or from what the handler does with the request: reading a body means POST, PUT or PATCH; reading no body means GET.
- Follow delegation. A call such as `apiV2.handleRequest(pathWithoutVersion, ...)` forwards the path to a helper, and the helper's own if-else chain on the path parameter holds the remaining endpoints. The helper is in the source above.
- Reconstruct each full path by combining the base prefix with the sub-path.

## Rules

- You must extract information from the specified code to answer the questions.
- You must answer the questions according to the JSON format: %s."""


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
    constants = {}
    for m in re.finditer(
        r'(?:public\s+)?(?:static\s+)?(?:final\s+)?String\s+(\w+)\s*=\s*"([^"]+)"\s*;',
        code,
    ):
        constants[m.group(1)] = m.group(2)
    return constants


def _extract_path_value(ann_block, constants):
    m = re.search(r'@Path\("([^"]+)"\)', ann_block)
    if m:
        return m.group(1)
    m = re.search(r'@Path\((\w+)\)', ann_block)
    if m and m.group(1) in constants:
        return constants[m.group(1)]
    return ""


def _expand_sub_resources(entry_code, deps):
    if not deps or len(deps) <= 1:
        return entry_code

    dep_classes = {}
    for dep_path, dep_code in deps.items():
        if dep_path == "entry_code_file":
            continue
        for m in re.finditer(r"(?:public\s+)?class\s+(\w+)", dep_code):
            dep_classes[m.group(1)] = dep_code

    if not dep_classes:
        return entry_code

    entry_constants = _resolve_constants(entry_code)

    expanded = entry_code
    seen = set()

    def _expand(code, path_prefix):
        nonlocal expanded
        local_constants = _resolve_constants(code)
        all_constants = {**entry_constants, **local_constants}
        for m in re.finditer(
            r"((?:@\w+(?:\([^)]*\))?\s*)+)"
            r"(public|protected|private)\s+"
            r"(?:static\s+)?(?:final\s+)?"
            r"(\w+)\s+"
            r"(\w+)\s*\(",
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
                    _expand(sub_code, full_prefix)

    _expand(entry_code, "")
    return expanded


def _assemble_codes(entry_file_path, deps):
    codes = f'Entry_code({entry_file_path}):\n<<<\n{deps["entry_code_file"]}\n>>>\n'
    for key, code in deps.items():
        if key != "entry_code_file":
            codes += f'\nRelated_code({key}):\n<<<\n{code}\n>>>\n'
    return codes


_PY_CLASS_FRAMEWORKS = {"flask", "django", "tornado", "webpy"}


def _resolve_py_method_names(entry_file_path, raw_endpoints):
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


def build_prompt(template, codes, framework):
    """Render the endpoint prompt, with the framework's own rules when it has any.

    A framework with no rules gets the template rendered exactly as it would be
    without this function, so adding a rule for one framework cannot move the
    others.
    """
    prompt = template % (codes, str(_SCHEMA).replace("'", '"'))
    hint = _FRAMEWORK_ROUTE_HINTS.get(framework, "")
    if hint and template is _PROMPT:
        prompt = prompt.replace("\n## Rules\n", f"\n{hint}\n## Rules\n", 1)
    return prompt


def _extract_endpoints(entry_file_path, deps, framework):
    if entry_file_path.endswith(".java"):
        deps["entry_code_file"] = _expand_sub_resources(
            deps["entry_code_file"], deps
        )
    codes = _assemble_codes(entry_file_path, deps)
    template = _SUN_PROMPT if is_sun_handler(entry_file_path) else _PROMPT
    prompt = build_prompt(template, codes, framework)

    response, meta = ask([{"role": "user", "content": prompt}],
                         extract=endpoint_entities, rebuild=rebuild_endpoints)

    raw_endpoints = response.get("endpoints", [])
    raw_endpoints = _resolve_py_method_names(entry_file_path, raw_endpoints)
    endpoints = []
    seen = set()
    for ep in raw_endpoints:
        path = ep.get("endpoint_path", "").strip()
        method = ep.get("http_method", "").upper().strip()
        path = path.rstrip("/")
        path = re.sub(r'/+', '/', path)
        if not path.startswith("/"):
            path = "/" + path
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
    return endpoints, meta


_JS_ROUTE_FRAMEWORKS = {"express", "koa", "nestjs"}

# Frameworks whose paths are declared with JAX-RS annotations, where a resource
# class can be reached through a locator in another class.
_JAXRS_FRAMEWORKS = {"jersey"}

_CLASS_PATH_RE = re.compile(
    r'@Path\(\s*([^)]*?)\s*\)\s*(?:@\w+(?:\([^)]*\))?\s*)*'
    r'public\s+(?:abstract\s+)?class\s+(\w+)', re.S)
_LOCATOR_RE = re.compile(
    r'@Path\(\s*([^)]*?)\s*\)\s*(?:@\w+(?:\([^)]*\))?\s*)*'
    r'public\s+([\w<>.]+)\s+(\w+)\s*\(')
_JAVA_STRING_CONST_RE = re.compile(r'\bString\s+(\w+)\s*=\s*"([^"]*)"')

_MOUNT_CONTEXT = """\
# Where this resource class is mounted

A JAX-RS resource class declares its paths relative to where it is mounted. Only
a class that carries a class level @Path is mounted on its own; every other
resource class is returned by a locator method in another class, so its mount
point cannot be read from this class alone. %s is mounted at:

%s

Report each endpoint's path as the full path a client calls, including the mount
point. Where more than one mount point is listed, the class serves each of its
endpoints at every one of them, so report each endpoint once per mount point.
"""


def _java_literal(raw, local, shared):
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    return local.get(raw, shared.get(raw, raw))


def jaxrs_mounts(root):
    """Map every resource class under root to the paths it is mounted at.

    A class read on its own shows only its own @Path values, which is why an
    entry processed standalone once emitted /{username}/friends for an API that
    serves /users/{username}/friends. Walking the locator chain recovers the
    missing prefix.
    """
    files, shared = {}, {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            if not fname.endswith(".java"):
                continue
            path = os.path.join(dirpath, fname)
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            files[os.path.splitext(fname)[0]] = text
            for name, value in _JAVA_STRING_CONST_RE.findall(text):
                shared.setdefault(name, value)

    class_path, locators = {}, {}
    for owner, text in files.items():
        local = dict(_JAVA_STRING_CONST_RE.findall(text))
        for raw, cls in _CLASS_PATH_RE.findall(text):
            class_path[cls] = _java_literal(raw, local, shared)
        for raw, ret, _method in _LOCATOR_RE.findall(text):
            ret = ret.split("<")[0].split(".")[-1]
            if ret not in files:
                continue
            locators.setdefault(ret, []).append(
                (owner, _java_literal(raw, local, shared)))

    def walk(cls, seen):
        if cls in seen:
            return []
        out = []
        own = class_path.get(cls)
        if own:
            out.append(own)
        for parent, segment in locators.get(cls, []):
            for base in walk(parent, seen | {cls}):
                joined = (base.rstrip("/") + "/" + segment).replace("//", "/")
                out.append(joined or "/")
        return out

    return {cls: sorted(set(walk(cls, frozenset()))) for cls in files}


# Rules that only hold for one framework. They are inserted into the endpoint
# prompt for that framework alone, and the insertion is skipped when there is no
# rule, so every other framework gets the prompt byte for byte as before. That
# matters because the endpoint prompt is shared: an edit that reached all 53
# APIs would be indistinguishable from the run-to-run drift the model already
# shows, and could not be shown to leave the other APIs alone.
_FRAMEWORK_ROUTE_HINTS = {
    "express": """\
## Framework notice

- Express gives a path a catch-all for the methods it does not support, written
  as app.all(path, handler) beside that path's real routes, where the handler
  only rejects the request. That registration is not an operation of the API:
  it serves no request of its own, so do not list it as an endpoint.
""",
}


def _brace_path_params(path):
    """Rewrite Express-style ":name" segments as OpenAPI "{name}" templates.

    Express, Koa and NestJS declare a path variable with a leading colon, which
    OpenAPI does not recognise: a consumer reading "/articles/:slug" sees one
    literal segment rather than a variable. The optional "(...)" that Express
    allows after the name is a route constraint and carries no path meaning.
    """
    return re.sub(r":([A-Za-z_]\w*)(?:\([^)]*\))?", r"{\1}", path)


def main(api, step2_result):
    framework = api["framework"]
    entry_to_deps = step2_result.get("entry_to_deps", {})
    start = time.time()

    # Django is handed a file and reads the route table out of it. Web.py is
    # handed the routes themselves on the command line, so the text arrives
    # ready to inject and nothing here has to parse it.
    extra_context = api.get("url_context")
    if extra_context is None and framework == "django" and "config_file" in api:
        cf = api["config_file"]
        if os.path.isfile(cf):
            with open(cf, "r", encoding="utf-8") as f:
                extra_context = f"# Django URL configuration ({cf}):\n{f.read()}\n"

    all_endpoints = []
    seen = set()
    llm_calls = 0
    errors = []

    mounts = {}
    if framework in _JAXRS_FRAMEWORKS:
        mounts = jaxrs_mounts(api["path"])
        rooted = sum(1 for v in mounts.values() if v)
        print(f"    JAX-RS mounts: resolved {len(mounts)} classes, "
              f"{rooted} with a mount point")

    for entry_file_path, deps in entry_to_deps.items():
        fname = os.path.basename(entry_file_path)
        print(f"    processing entry: {fname}")
        try:
            context = extra_context
            entry_mounts = mounts.get(os.path.splitext(fname)[0]) if mounts else None
            if entry_mounts:
                block = _MOUNT_CONTEXT % (
                    os.path.splitext(fname)[0],
                    "\n".join(f"- {m}" for m in entry_mounts))
                context = (block + "\n" + context) if context else block
            if context:
                deps = dict(deps)
                deps["entry_code_file"] = context + "\n" + deps["entry_code_file"]
            endpoints, _ = _extract_endpoints(entry_file_path, deps, framework)
            if framework in _JS_ROUTE_FRAMEWORKS:
                for ep in endpoints:
                    ep["endpoint_path"] = _brace_path_params(ep["endpoint_path"])
            for ep in endpoints:
                key = (ep["endpoint_path"], ep["http_method"])
                if key not in seen:
                    seen.add(key)
                    all_endpoints.append(ep)
            if not endpoints:
                errors.append({"entry_file": entry_file_path,
                               "error": "the model returned an empty endpoint list"})
                print(f"    [EMPTY] {fname}: model returned no endpoints")
            llm_calls += 1
        except Exception as e:
            errors.append({"entry_file": entry_file_path, "error": str(e)})
            print(f"    [ERROR] {entry_file_path}: {e}")
            continue

    if framework == "tornado":
        all_endpoints = [ep for ep in all_endpoints
                         if ep["endpoint_path"].startswith("/api/")
                         or ep["endpoint_path"] == "/api"]

    return {
        "task_id": None,
        "api_name": api["name"],
        "framework": framework,
        "endpoints": all_endpoints,
        "errors": errors,
        "duration_ms": round((time.time() - start) * 1000),
    }
