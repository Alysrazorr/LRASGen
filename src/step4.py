"""
Step 4 — Parameter and response identification via LLM.

For each endpoint identified in Step 3, make two LLM calls:
  1. Identify parameters (name, type, position, required, description)
  2. Identify responses (status code, description, data schema)

Framework-specific hints are prepended to help the LLM find implicit params.
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import logger
from llm import chat


# ---------------------------------------------------------------------------
# framework-specific hints for parameter identification
# ---------------------------------------------------------------------------
_FRAMEWORK_HINTS = {
    "django": """
[Django REST Framework hints]
- DRF ModelViewSet/ReadOnlyModelViewSet list endpoints auto-generate pagination params: limit, offset
- DRF ViewSets support ordering params via ordering_fields attribute — add "ordering" query param
- Check method bodies for self.request.GET.get('name'), self.request.query_params.get('name')
- Check self.kwargs for URL path params (e.g., self.kwargs['pk'] for detail endpoints)
- Check serializer_class fields — each serializer field may be a writable body param on POST/PUT/PATCH
""",
    "flask": """
[Flask hints]
- Check route decorators for <type:variable> URL patterns (path params)
- @use_args() decorator: each method's @use_args dict defines its exact query parameters with types and validation. Extract only those parameters.
- Check method bodies for request.args.get(), request.form.get(), request.json.get(), request.get_json()
- Check for Flask-RESTful reqparse.RequestParser definitions
""",
    "tornado": """
[Tornado hints]
- IMPORTANT: Tornado handlers have EMPTY method signatures (def get(self), def post(self))
- Check method bodies for self.get_argument('name'), self.get_query_argument('name')
- Check for self.get_body_argument('name'), self.request.body
- URL path params come from regex groups in handler registration, NOT from method signatures
- Check for self.path_args, self.path_kwargs
""",
    "express": """
[Express hints]
- Check for req.params (URL path params), req.query (query string params)
- Check for req.body (POST/PUT body), req.headers (header params)
- Check route definitions for :param patterns (e.g., /api/users/:id)
""",
    "nestjs": """
[NestJS hints]
- Check for @Param(), @Query(), @Body(), @Headers() decorators
- Check DTO class definitions for class-validator decorators (@IsString, @IsInt, etc.)
- Check for @ApiParam(), @ApiQuery() Swagger decorators
""",
    "aspnetcore": """
[ASP.NET Core hints]
- Check for [FromQuery], [FromRoute], [FromBody], [FromHeader], [FromForm] attributes
- Check for [Required], [StringLength], [Range] validation attributes on model properties
- Check action method parameters and their types
""",
    "webpy": """
[Web.py hints]
- Check method bodies for web.input() to get query/form params
- Check URL routing patterns for regex groups (e.g., '/(\\d+)')
- Check for web.data() for raw request body
""",
    "jersey": """
[JAX-RS / Jersey hints]
- IMPORTANT: Many JAX-RS resource methods have no explicit @QueryParam parameters.
  Query/pagination/filter parameters are injected through context objects accessed
  via getters like getPagination(), getFilter(), getUser(), etc.
- When you see a getter call in the method body (e.g. getPagination(),
  getFilter()), this indicates that the endpoint accepts parameters defined by
  the getter's return type. Find the return type in Related_code, expand its
  fields, and treat each field as a query parameter with the field's declared
  type. Do NOT invent parameter names — only use fields actually declared in the
  return type's source code.
- Check for @BeanParam — these are injected DTO beans whose fields become
  individual query/path/header/form parameters. Treat each field as a separate
  parameter with the bean's class as the type.
- @Context parameters (UriInfo, HttpHeaders, SecurityContext, etc.) are
  framework-injected — set type to FRAMEWORK-INJECTED.
""",
}


# ---------------------------------------------------------------------------
# prompt templates
# ---------------------------------------------------------------------------
_PROMPT_PARAM = """\
## Source Code

```
%s
```

## Questions

1. In the source code, there is an endpoint: %s, and its method name is: %s. What parameters does this endpoint accept?
2. For each parameter, provide: name, type, require ("true" or "false"), position (path, query, header, body, or form), and description.
3. If an annotation gives the parameter an alias (e.g. @RequestParam("foo")), use the annotation value as the parameter name, not the variable name.
4. If the method uses a @use_args() decorator, extract parameters ONLY from that decorator's dict — each key is a parameter with a type and optional constraints. Do NOT include parameters from other methods' decorators or from request.args.get() calls.
5. If the endpoint does not contain any parameters, return an empty array.

## Notice — What is an API parameter

- An API parameter is a value sent by the API client in the HTTP request: path variables (/users/{id}), query string parameters (?page=1), HTTP headers, request body, or form data.
- If a method parameter is NOT sent by the client but is injected by the server-side framework or container (e.g. authentication context, request wrapper, binding result, session, model, or any object the framework constructs internally), set its type to "FRAMEWORK-INJECTED". Do NOT expand such parameters and do NOT include any nested fields for them.
- If a parameter's type is a custom class that IS sent by the client (e.g. AlbumRequest, LoginRequest, PostRequest), write its exact simple class name as the type — not "object". Do NOT expand nested fields; we will handle expansion in post-processing.
- For standard types (String, Integer, int, Long, long, Boolean, boolean, Float, float, Double, double, BigDecimal, Date, LocalDate, DateTime, Instant, UUID, etc.), use the conventional short name (string, integer, boolean, number).

## Notice — When is a parameter required?

- Path variables ({id}, {userId}, etc.) are ALWAYS required. Set require to "true" for every path parameter.
- For query parameters, form fields, and headers: set require to "false" unless you see EXPLICIT annotation-based evidence that the parameter is mandatory. Explicit evidence includes ONLY:
  * @NotNull, @NotBlank, @NotEmpty directly on the parameter
  * required=true in the parameter's binding annotation (e.g. @RequestParam(required=true))
  * @Valid or @Validated on the parameter type (for body parameters)
- Do NOT assume a parameter is required just because the framework has a default behavior (e.g. Spring @RequestParam defaults to required=true — ignore this default). Only annotations count.
- For body parameters (@RequestBody): set require to "true" if there is a @Valid or @Validated annotation on the parameter. Otherwise, set require to "false".
- When in doubt, default to "false".

## Rules

- You must extract information from the specified code to answer the questions.
- You must answer the questions according to the JSON format: %s.
- %s"""


_PROMPT_RESP = """\
## Source Code

```
%s
```

## Questions

1. In the source code, there is an endpoint: %s, and its method name is: %s. What responses does this endpoint return?
2. For each response, provide: status code and description.
3. If the response contains data, save its structure in the "data_schema" field. If the data has a name, put it in "data_schema > name". Each field is a <name, type> pair in "data_schema > schema".
4. If the response contains an exception description, fill in the "exception" field.
5. If the exception is unclear, it may not be included.
6. Go through all return branches in the source code.
7. If the endpoint does not return any responses, return an empty array.

## Notice — What counts as a response

- Include responses that are explicitly defined in the source code:
  * A return statement that creates a response (return ResponseEntity, return Response, return new XxxResponse, etc.)
  * An explicit throw/catch/ExceptionHandler that produces an error response
- Every endpoint must have at least one success response (200, 201, 202, 204, 302).
- Standard error responses from declared security or path-variable patterns:
  * If the controller class or method has @PreAuthorize, @Secured, or @RolesAllowed,
    include 401 (Unauthorized) and/or 403 (Forbidden) as appropriate.
  * If the endpoint has @PathVariable parameters whose value is used to look up
    a resource (database/service call), include 404 (Not Found).
- Do NOT infer responses from validation annotations (@Valid, @Transactional).
- For each status code, return at most ONE response entry.

## Rules

- You must extract information from the specified code to answer the questions.
- You must answer the questions according to the JSON format: %s."""


# ---------------------------------------------------------------------------
# JSON schemas for structured output
# ---------------------------------------------------------------------------
_SCHEMA_PARAM = {
    "type": "object",
    "properties": {
        "parameters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "parameter name (use annotation alias if present)"},
                    "type": {"type": "string", "description": "data type: string, integer, number, boolean, or the exact simple class name for custom types"},
                    "require": {"type": "string", "description": "'true' if required, 'false' if optional"},
                    "position": {"type": "string", "description": "path, query, header, body, or form"},
                    "description": {"type": "string"},
                },
                "required": ["name", "type"],
            },
        },
    },
    "required": ["parameters"],
}

_SCHEMA_RESP = {
    "type": "object",
    "properties": {
        "responses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "status_code": {"type": "integer"},
                    "description": {"type": "string"},
                    "data_schema": {"type": "array"},
                },
            },
        },
    },
    "required": ["responses"],
}


# ---------------------------------------------------------------------------
# Post-processing: expand class_name markers into individual fields
# ---------------------------------------------------------------------------
import re as _re_mod

_JAVA_FIELD_RE = _re_mod.compile(
    r'(?:public|protected|private)\s+'
    r'(?!(?:static\s+final|final\s+static)\s+)'  # skip static final constants
    r'(?:(?:static\s+)?(?:final\s+)?)?'
    r'(\w+(?:\.\w+)*(?:<[^>]+>)?)\s+(\w+)\s*[=;]')


# C# property regex: public Type Name { get; set; } or { get; private set; }
_CS_PROP_RE = _re_mod.compile(
    r'public\s+([\w.]+(?:<[\w.,\s]+>)?(?:\?)?)\s+'
    r'(\w+)\s*\{[^}]*get[^}]*\}'
)


def _find_dto_file(class_name, deps):
    """Find a DTO source file: search in deps (Java .java, C# .cs, Kotlin .kt)."""
    for ext in ('.java', '.cs', '.kt'):
        target = class_name + ext
        for key in deps:
            if os.path.basename(key) == target:
                return deps[key]
    return None


def _extract_dto_fields(class_name, deps, visited=None):
    """Extract all field/property names and types from a DTO class (Java or C#)."""
    if visited is None:
        visited = set()
    if class_name in visited:
        return []
    visited.add(class_name)

    code = _find_dto_file(class_name, deps)
    if not code:
        return []

    is_csharp = 'namespace ' in code and ('class ' in code) and not ('import ' in code)

    if is_csharp:
        fields = _extract_cs_properties(class_name, code, deps, visited)
    elif _is_kotlin_code(code):
        fields = _extract_kotlin_fields(class_name, code, deps, visited)
    else:
        if _re_mod.search(r'\brecord\s+\w+', code):
            fields = _extract_record_components(class_name, code, deps, visited)
        else:
            fields = _extract_java_fields(class_name, code, deps, visited)

    return list(fields.values())


_RECORD_COMPONENT_RE = _re_mod.compile(
    r'(\w+(?:\.\w+)*(?:<[^>]+>)?)\s+(\w+)'
)

# Kotlin detection: has 'package' (not 'namespace') and uses val/var patterns
def _is_kotlin_code(code):
    return bool(_re_mod.search(r'\b(val|var)\s+\w+\s*:', code))


_KOTLIN_PARAM_RE = _re_mod.compile(
    r'(?:@\w+(?:\s*\([^)]*\))?\s+)*'   # skip annotations
    r'(?:override\s+)?'                  # skip override keyword
    r'(?:val|var)\s+'                    # val or var keyword
    r'(\w+)\s*:\s*'                      # name : type
    r'([\w.?]+(?:<[^>]+>)?)'            # type (with optional generics)
    r'(?:\s*[=)])'                       # end with = or ) (or ,)
)


def _extract_kotlin_fields(class_name, code, deps, visited):
    """Extract constructor/class parameters from a Kotlin class.
    Handles data class, regular class with primary constructor, and enum class."""
    fields = {}

    # Find class inheritence: class Foo : BaseFoo(args) or class Foo(args) : BaseFoo
    class_match = _re_mod.search(
        r'(?:data\s+)?class\s+\w+\s*(?:\([^)]*\))?\s*(?::\s*(\w+))?',
        code
    )
    parent = class_match.group(1) if class_match and class_match.group(1) else None
    if parent and parent not in ('Object', 'object', 'Any'):
        for pf in _extract_dto_fields(parent, deps, visited):
            fields[pf['name']] = pf

    # Find the primary constructor parens
    m = _re_mod.search(r'\)', code)
    if not m:
        return fields

    paren_start = None
    depth_count = 0
    for i in range(m.start() - 1, -1, -1):
        if code[i] == ')':
            depth_count += 1
        elif code[i] == '(':
            depth_count -= 1
            if depth_count < 0:
                paren_start = i
                break

    if paren_start is None:
        return fields

    params_str = code[paren_start + 1 : m.start()]
    # Process param by param (split by commas accounting for generics)
    bracket_depth = 0
    current = ''
    for ch in params_str + ',':
        if ch == '<': bracket_depth += 1
        elif ch == '>': bracket_depth -= 1
        if ch == ',' and bracket_depth == 0:
            current = current.strip()
            # Try to match val/var pattern
            pm = _re_mod.search(r'\b(?:val|var)\s+(\w+)\s*:\s*([\w.?]+(?:<[^>]+>)?)', current)
            if pm:
                fname = pm.group(1)
                ftype_raw = pm.group(2)
                ftype = _re_mod.sub(r'<.*>', '', ftype_raw)
                if not fname.startswith('_'):
                    fields[fname] = {'name': fname, 'type': ftype}
            current = ''
        else:
            current += ch

    return fields


def _extract_record_components(class_name, code, deps, visited):
    """Extract fields from a Java record. Record components are declared as
    constructor-style parameters inside the parentheses."""
    fields = {}

    # Match record components inside the parentheses: record Foo(Type1 a, Type2 b, ...)
    m = _re_mod.search(r'\)', code)
    if not m:
        return fields

    # Walk back from just before the closing paren to find matching opening paren
    paren_start = None
    depth = 0
    for i in range(m.start() - 1, -1, -1):
        if code[i] == ')':
            depth += 1
        elif code[i] == '(':
            depth -= 1
            if depth < 0:
                paren_start = i
                break

    if paren_start is None:
        return fields

    components_str = code[paren_start + 1 : m.start()]

    for cm in _RECORD_COMPONENT_RE.finditer(components_str):
        ftype = _re_mod.sub(r'<.*>', '', cm.group(1))
        fname = cm.group(2)
        if fname.isupper() and '_' in fname:
            continue
        if not fname.startswith('_') and not fname.startswith('serial'):
            fields[fname] = {'name': fname, 'type': ftype}

    return fields


def _extract_java_fields(class_name, code, deps, visited):
    """Extract fields from a Java class, including inherited fields."""
    fields = {}
    class_match = _re_mod.search(r'class\s+\w+\s+extends\s+(\w+)', code)
    parent = class_match.group(1) if class_match else None
    if parent and parent not in ('Object', 'Object()'):
        for pf in _extract_dto_fields(parent, deps, visited):
            fields[pf['name']] = pf

    for m in _JAVA_FIELD_RE.finditer(code):
        ftype = _re_mod.sub(r'<.*>', '', m.group(1))
        fname = m.group(2)
        if fname.isupper() and '_' in fname:
            continue
        if not fname.startswith('_') and not fname.startswith('serial'):
            fields[fname] = {'name': fname, 'type': ftype}

    return fields


def _extract_cs_properties(class_name, code, deps, visited):
    """Extract auto-properties from a C# class, including inherited properties."""
    fields = {}
    # C# inheritance: class X : BaseClass, IInterface
    class_match = _re_mod.search(r'class\s+\w+\s*:\s*(\w+)', code)
    parent = class_match.group(1) if class_match else None
    if parent and parent not in ('Object', 'object'):
        for pf in _extract_dto_fields(parent, deps, visited):
            fields[pf['name']] = pf

    for m in _CS_PROP_RE.finditer(code):
        ftype = _re_mod.sub(r'<.*>', '', m.group(1))
        fname = m.group(2)
        if fname.isupper() and '_' in fname:
            continue
        if not fname.startswith('_'):
            fields[fname] = {'name': fname, 'type': ftype}

    return fields


_DTO_TAG_RE = _re_mod.compile(r'\[(?:DTO|class):(\w+)\]')


def _expand_dto_params(params, deps, max_depth=5):
    """Recursively expand DTO params by checking whether the param's *type*
    matches a known class in deps (i.e. a .java or .cs file exists for it).

    Expansion order (per endpoint):
      1. For each param, check if ``type`` is a known DTO class.
      2. If yes, call _extract_dto_fields() to get the class's first-level
         fields (inheritance is resolved inside that function).
      3. Replace the param with the expanded fields, each carrying
         ``_class_name`` = the parent DTO name and ``_depth`` = expansion depth.
      4. Recursively check each expanded field's type — if that type is also
         a known DTO, expand it too (depth + 1).

    A ``visited`` set per recursive branch prevents infinite loops from
    circular back-references (e.g. User → Address → User).
    """
    result = []
    for p in params:
        result.extend(_try_expand_param(p, deps, visited=set(), depth=0, max_depth=max_depth))
    return result


def _try_expand_param(p, deps, visited, depth, max_depth):
    """Try to expand a single param into its DTO fields.

    Returns a list — either the expanded fields (if the type is a known DTO
    and depth < max_depth) or the original param (if not expandable).

    ``_depth`` is set ONLY when a field is first created during expansion,
    recording which expansion level it was produced at.  It is never
    overwritten afterwards so that a primitive field that originated from
    depth-0 expansion keeps _depth=0 even though the recursive check may
    visit it at a deeper call level.
    """
    type_name = (p.get("type") or "").strip()
    # Strip generics for primitive/container checks: List<Foo> → List
    type_clean = _re_mod.sub(r'<[^>]*>', '', type_name).strip()
    # Ensure _depth is set on the original param the first time we see it
    p.setdefault("_depth", depth)

    # Skip standard types and already-visited classes (cycle detection)
    if not type_name or type_clean in _PRIMITIVE_TYPES or depth >= max_depth:
        return [p]

    if type_name in visited:
        return [p]

    # Find DTO file using the cleaned type (without generics)
    dto_file = _find_dto_file(type_clean, deps)
    if not dto_file:
        return [p]

    visited.add(type_name)
    fields = _extract_dto_fields(type_name, deps)
    if not fields:
        return [p]

    result = []
    for f in fields:
        is_nested_dto = bool(_find_dto_file(f["type"], deps)) and f["type"] not in _PRIMITIVE_TYPES

        # DTO fields default to "false" — step5 annotation extraction
        # sets require="true" only for fields with @NotNull/@NotBlank

        field_param = {
            "name": f["name"],
            "type": f["type"],
            "_class_name": type_name,
            "_depth": depth,        # the expansion level this field was produced at
            "require": "false",
            "position": p.get("position", "query"),
            "description": p.get("description", ""),
        }
        # Always keep the field param itself (counts as 1 for P statistics)
        result.append(field_param)

        # Recursively expand nested DTO fields IF the type is a known DTO
        if is_nested_dto:
            nested_result = _try_expand_param(
                dict(field_param), deps, visited=set(visited), depth=depth + 1, max_depth=max_depth
            )
            result.extend(nested_result)
    return result


# Standard / primitive types that should NOT trigger DTO expansion
_PRIMITIVE_TYPES = {
    "string", "String", "integer", "Integer", "int", "Int",
    "long", "Long", "boolean", "Boolean", "bool", "Bool",
    "float", "Float", "double", "Double", "number", "Number",
    "BigDecimal", "Date", "LocalDate", "LocalDateTime", "DateTime",
    "Instant", "UUID", "array", "Array", "List", "Collection",
    "Map", "Dictionary", "Set", "MutableSet", "MutableList",
    "object", "Object",
    "IEnumerable", "IList", "IDictionary", "Enum", "enum",
    "", "void",
}


_FLASK_TYPE_MAP = {
    "Integer": "integer", "Str": "string", "Boolean": "boolean",
    "Float": "number", "Decimal": "number", "DateTime": "string",
    "DelimitedList": "array", "List": "array", "Dict": "object",
    "Raw": "string", "Nested": "object",
}


def _resolve_flask_use_args(entry_path, class_name, method_name):
    """Parse a Python file to extract params from @use_args decorator on a specific method."""
    try:
        with open(entry_path, 'r', encoding='utf-8', errors='replace') as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception:
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    for decorator in item.decorator_list:
                        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name) and decorator.func.id == 'use_args':
                            if decorator.args and isinstance(decorator.args[0], ast.Dict):
                                params = []
                                for key_node, value_node in zip(decorator.args[0].keys, decorator.args[0].values):
                                    name = key_node.value if isinstance(key_node, ast.Constant) else None
                                    if not name: continue
                                    ftype = "string"
                                    if isinstance(value_node, ast.Call) and isinstance(value_node.func, ast.Attribute):
                                        ftype = _FLASK_TYPE_MAP.get(value_node.func.attr, "string")
                                    params.append({"name": name, "type": ftype, "require": "false", "position": "query", "description": ""})
                                return params
    return None


# ---------------------------------------------------------------------------
# code assembly
# ---------------------------------------------------------------------------
def _extract_implicit_params(entry_code, deps):
    """Scan deps for getParameter("name") calls when entry uses HttpServletRequest."""
    if "HttpServletRequest" not in entry_code:
        return None
    params = set()
    for key, code in deps.items():
        if key == "entry_code_file":
            continue
        for m in _re_mod.findall(r'getParameter(?:Values)?\("([^"]+)"\)', code):
            params.add(m)
    if not params:
        return None
    return sorted(params)


def _assemble_codes(entry_file_path, deps):
    codes = f'Entry_code({entry_file_path}):\n<<<\n{deps["entry_code_file"]}\n>>>\n'
    for key, code in deps.items():
        if key != "entry_code_file":
            codes += f'\nRelated_code({key}):\n<<<\n{code}\n>>>\n'
    return codes


# ---------------------------------------------------------------------------
# single endpoint processing
# ---------------------------------------------------------------------------
def _dedup_params(params, endpoint_path):
    """Deduplicate parameters within one endpoint.

    - Path params: deduplicated by (slot, _class_name, name).
    - Other params: deduplicated by (position, _class_name, name).

    The _class_name prevents accidental deduplication between different
    DTOs that happen to have identically-named fields at the same position
    (e.g. AlbumRequest.id vs User.id — they are different parameters).
    """
    path_slots = {}
    for m in _re_mod.finditer(r'\{(\w+)\}', endpoint_path):
        path_slots[m.group(1)] = len(path_slots)

    seen = set()
    result = []
    for p in params:
        pos = p.get("position", "")
        name = p.get("name", "")
        cn = p.get("_class_name", "")
        if pos == "path":
            slot = path_slots.get(name)
            key = ("path", slot, cn) if slot is not None else ("path", name, cn)
        else:
            key = (pos, cn, name)
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


def _process_endpoint(args):
    """Process parameters + responses for one endpoint. For thread-pool use."""
    entry_path, deps, endpoint, provider, temperature, api_name = args[:6]
    cross_validate = args[7] if len(args) > 7 else False
    framework = endpoint.get("framework", "")

    codes = _assemble_codes(entry_path, deps)
    ep_name = f'{endpoint["http_method"]} "{endpoint["endpoint_path"]}"'
    method_name = endpoint["method_name"]
    params = []
    responses = []
    errors = []

    # framework hint for this API
    hint = _FRAMEWORK_HINTS.get(framework, "")

    # If the entry uses HttpServletRequest, pre-scan executor classes for
    # implicit query parameters and inject them as an explicit hint.
    implicit = _extract_implicit_params(deps.get("entry_code_file", ""), deps)
    if implicit:
        hint += (
            f"\n[Implicit HttpServletRequest params]\n"
            f"The entry code uses HttpServletRequest. The following query parameters "
            f"are read via getParameter() in executor/service classes found in "
            f"Related_code. Review each endpoint and include the parameters "
            f"that are applicable: {', '.join(implicit)}.\n"
        )

    # --- parameters ---
    # For Flask class-based views: pre-resolve @use_args params deterministically
    if framework == "flask" and "." in method_name:
        parts = method_name.rsplit(".", 1)
        resolved = _resolve_flask_use_args(entry_path, parts[0], parts[1])
        if resolved:
            params = resolved

    if not params:
        try:
            prompt = _PROMPT_PARAM % (codes, ep_name, method_name, str(_SCHEMA_PARAM), hint)
            if cross_validate:
                from llm import cross_validate as cv
                r, _meta = cv([{"role": "user", "content": prompt}], temperature=temperature)
            else:
                r = chat([{"role": "user", "content": prompt}], provider=provider, temperature=temperature, max_retries=3)
            raw = r.get("parameters", [])
            for p in raw:
                flat = {
                    "name": p.get("name"),
                    "type": p.get("type"),
                    "require": p.get("require", "false"),
                    "position": p.get("position"),
                    "description": p.get("description"),
                }
                params.append(flat)
                for nested in p.get("nested_parameters") or []:
                    nested["position"] = nested.get("position", p.get("position", "body"))
                    params.append({
                        "name": nested.get("name"),
                        "type": nested.get("type"),
                        "require": nested.get("require", "false"),
                        "position": nested.get("position"),
                        "description": nested.get("description"),
                    })
        except Exception as e:
            errors.append(f"params: {e}")

    # --- responses ---
    try:
        prompt = _PROMPT_RESP % (codes, ep_name, method_name, str(_SCHEMA_RESP))
        if cross_validate:
            from llm import cross_validate as cv
            r, _meta = cv([{"role": "user", "content": prompt}], temperature=temperature)
        else:
            r = chat([{"role": "user", "content": prompt}], provider=provider, temperature=temperature, max_retries=3)
        for resp in r.get("responses", []):
            responses.append({
                "status_code": resp.get("status_code"),
                "description": resp.get("description"),
                "data_schema": resp.get("data_schema"),
            })
    except Exception as e:
        errors.append(f"responses: {e}")

    # dedup responses by status_code (keep first)
    seen_sc = set()
    deduped_resp = []
    for r in responses:
        sc = r.get("status_code")
        if sc not in seen_sc:
            seen_sc.add(sc)
            deduped_resp.append(r)
    responses = deduped_resp

    # filter out framework-injected parameters before DTO expansion
    params = [p for p in params if p.get("type") != "FRAMEWORK-INJECTED"]

    # post-process: expand DTO markers into individual fields
    params = _expand_dto_params(params, deps)
    # dedup: remove duplicate params, path-by-position, others by (position, name)
    params = _dedup_params(params, endpoint["endpoint_path"])

    return {
        "endpoint_path": endpoint["endpoint_path"],
        "http_method": endpoint["http_method"],
        "method_name": endpoint["method_name"],
        "source_file": endpoint.get("source_file"),
        "parameters": params,
        "responses": responses,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# parallel runner
# ---------------------------------------------------------------------------
def run_parallel(tasks, provider="deepseek", temperature=0.2, max_workers=10, cross_validate=False):
    """
    Process all endpoints across all APIs in parallel.

    Args:
        tasks: list of dicts with {api, step2_result, step3_result, task_id}
        cross_validate: if True, use 3-LLM voting per endpoint (Section 4.1)
    Returns:
        (results_by_task, total_params, total_resps)
    """
    work_items = []
    for t in tasks:
        api = t["api"]
        s2 = t["step2_result"]
        s3 = t["step3_result"]
        tid = t["task_id"]
        entry_to_deps = s2.get("entry_to_deps", {})
        for ep in s3.get("endpoints", []):
            entry_path = ep.get("source_file", "")
            deps = entry_to_deps.get(entry_path, {"entry_code_file": ""})
            # tag endpoint with framework info for hint lookup
            ep_with_fw = dict(ep)
            ep_with_fw["framework"] = api["framework"]
            work_items.append((entry_path, deps, ep_with_fw, provider, temperature, api["name"], tid, cross_validate))

    cv_label = " [cross-validate]" if cross_validate else ""
    logger.info(f"Step4 dispatching {len(work_items)} endpoints x 2 = {len(work_items)*2} LLM calls{cv_label} to {max_workers} workers")

    results_by_task = {}
    done = 0
    total = len(work_items)
    total_params = 0
    total_resps = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_process_endpoint, (ep, deps, endpoint, provider, temperature, name, tid, cv)): (tid, ep)
            for ep, deps, endpoint, provider, temperature, name, tid, cv in work_items
        }
        for fut in as_completed(futures):
            tid, ep_path = futures[fut]
            r = fut.result()
            done += 1
            results_by_task.setdefault(tid, []).append(r)
            total_params += len(r["parameters"])
            total_resps += len(r["responses"])
            if done % 20 == 0 or done == total:
                logger.step("Step4", done, total, f"{total_params} params, {total_resps} responses")

    return results_by_task, total_params, total_resps
