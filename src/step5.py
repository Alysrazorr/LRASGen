"""
Step 5 — Parameter constraint identification via LLM.

For each endpoint identified in Step 4, send the list of parameters (with
their basic info) back to the LLM to extract detailed constraints:
  - min / max (numeric range)
  - min_length / max_length (string length)
  - format (date, datetime, email, etc.)
  - enum / dictionary (allowed values)
  - default_value
  - require (mandatory flag)
"""

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import logger
from llm import chat
from step4 import _find_dto_file, _extract_dto_fields


_PROMPT_CONSTRAINT = """\
## Source Code

```
%s
```

## Questions

The endpoint %s (method: %s) has the following parameters already identified:

```
%s
```

For each parameter, extract constraint information from the source code:

1. If the type is string, what are min_length and max_length?
2. If the type is string and resembles a date or datetime, what is its format?
3. If the type is integer or number, what are min and max?
4. If the parameter has a fixed set of allowed values, what are the enum values?
5. If the parameter is a dictionary or map with known keys, what is the dictionary structure?
6. If the parameter has a default value, what is it?

## Notices

- Look for validation annotations: @Size, @Min, @Max, @Pattern, @Length, @NotEmpty, @NotBlank, @Range, @Digits, @Email, etc.
- Also check method-body validation: if (x < 0), if (len(s) > 128), assert, require, etc.
- For Django: check serializer fields for max_length, min_length, choices, default, etc.
- If a parameter has a class_name field, locate that class in the Related_code and extract constraints from its field annotations. The class fields share the same constraints across all endpoints that use it.

CRITICAL – what counts as explicit:
- DTO/entity class field annotations in Related_code (e.g. @NotNull, @Size(min=1,max=100), @Min(0), @Email, @Pattern) ARE explicit constraints and MUST be extracted.
- @ApiImplicitParam attributes (value, defaultValue, allowableValues) ARE explicit constraints.
- Method-body validation checks (if x < 0, assert len(s) > 128) ARE explicit constraints.

Do NOT infer constraints from:
- Comments, Javadoc, descriptions, or documentation text (e.g. \"WGS84 coordinates\" does NOT imply a format constraint).
- Parameter names or types alone (e.g. a param named \"timeout\" without annotations does not imply min/max).
- Framework defaults or conventions.
Only extract what is visibly defined in code annotations or validation checks.

## Rules

- You must extract information from the specified code to answer the questions.
- For parameters that have no constraints, include them with only their name.
- You must answer the questions according to the JSON format: %s."""


_SCHEMA_CONSTRAINT = {
    "type": "object",
    "properties": {
        "constraints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "parameter name (must match the name from the parameters list)"},
                    "min": {"description": "minimum numeric value"},
                    "max": {"description": "maximum numeric value"},
                    "min_length": {"description": "minimum string length"},
                    "max_length": {"description": "maximum string length"},
                    "format": {"type": "string", "description": "date, date-time, email, uri, uuid, etc."},
                    "enum": {"type": "array", "description": "list of allowed values"},
                    "dictionary": {"type": "array", "description": "key-value pairs for dictionary params"},
                    "default_value": {"description": "default value if not provided"},
                },
                "required": ["name"],
            },
        },
    },
    "required": ["constraints"],
}


_CONSTRAINT_KEYS = {"min", "max", "min_length", "max_length", "format", "enum", "dictionary", "default_value"}


def _param_has_constraints(p):
    """Check whether a param already carries constraint fields (e.g. from DTO expansion)."""
    for k in _CONSTRAINT_KEYS:
        v = p.get(k)
        if v is not None and v != "" and v != [] and v != {}:
            return True
    return False


def _process_constraints(args):
    """Extract constraints for one endpoint's parameters. For thread-pool use."""
    entry_path, deps, endpoint, params, provider, temperature, api_name = args[:7]
    cross_validate = args[7] if len(args) > 7 else False

    # Separate DTO-expanded params (already have constraints) from bare params
    rich_params = [p for p in params if _param_has_constraints(p)]
    bare_params = [p for p in params if not _param_has_constraints(p)]

    if not bare_params:
        return params, None

    codes = _assemble_codes(entry_path, deps)
    ep_name = f'{endpoint["http_method"]} "{endpoint["endpoint_path"]}"'
    method_name = endpoint["method_name"]

    param_list = json.dumps([
        {"name": p["name"], "type": p.get("type"), "position": p.get("position")}
        for p in bare_params
    ], indent=2)

    try:
        prompt = _PROMPT_CONSTRAINT % (codes, ep_name, method_name, param_list, str(_SCHEMA_CONSTRAINT))
        if cross_validate:
            from llm import cross_validate as cv
            r, _meta = cv([{"role": "user", "content": prompt}], temperature=temperature)
        else:
            r = chat([{"role": "user", "content": prompt}], provider=provider, temperature=temperature, max_retries=3)
        constraints = r.get("constraints", [])
        constraint_map = {}
        for c in constraints:
            name = c.get("name", "")
            constraint_map[name] = {
                k: v for k, v in c.items()
                if k != "name" and v is not None and v != "" and v != [] and v != {}
            }
        for p in bare_params:
            extra = constraint_map.get(p["name"], {})
            p.update(extra)
        # Recombine rich (DTO) params with enriched bare params
        return rich_params + bare_params, None
    except Exception as e:
        return rich_params + bare_params, str(e)


_DTO_CONSTRAINT_PROMPT = """\
## Source Code

```
%s
```

## Questions

The DTO class has the following fields:

```
%s
```

For each field, extract validation constraints from annotations and field declarations:

1. `@NotNull`, `@NotEmpty`, `@NotBlank` → require: "true"
2. `@Min(value)`, `@DecimalMin(value)` → min: value
3. `@Max(value)`, `@DecimalMax(value)` → max: value
4. `@Range(min=x, max=y)` → min: x, max: y
5. `@Size(min=x, max=y)`, `@Length(min=x, max=y)` → min_length: x, max_length: y
6. `@Pattern(regexp="...")` → format: the regexp
7. `@Email` → format: "email"
8. `@EachRange(min=x, max=y)` → min: x, max: y
9. `@EachPattern(regexp="...")` → format: the regexp
10. `@Positive` → min: 1, `@PositiveOrZero` → min: 0
11. `@Negative` → max: -1, `@NegativeOrZero` → max: 0
12. `@ApiModelProperty` with enumerated values → enum: [...]
13. default_value from field initializer (e.g. `= false`, `= 0`, `= DEFAULT_PAGE_SIZE`)

## Notice

- Only extract constraints from ANNOTATIONS and field initializers. Do NOT infer constraints from Javadoc, comments, field names, or type names.
- Only include fields that have constraints. Omit fields without any constraints.

## Rules

- You must extract information from the specified code to answer the questions.
- You must answer the questions according to the JSON format: %s.
- Only include fields that have constraints. Omit fields without any constraints."""


def _extract_dto_constraints(class_name, deps, provider, temperature):
    """Extract constraints for all fields of a DTO class hierarchy via one LLM call.
    Includes parent class source code so the LLM can resolve constant references."""
    import re
    # Collect full class hierarchy source code (parent first, child last)
    codes = []
    current = class_name
    seen = set()
    while current and current not in seen and current not in ('Object', 'Object()'):
        seen.add(current)
        code = _find_dto_file(current, deps)
        if code:
            # Strip package/import lines to save tokens
            code = re.sub(r'^package\s+.*?;\s*', '', code)
            code = re.sub(r'^import\s+.*?;\s*', '', code, flags=re.MULTILINE)
            code = code.strip()
            codes.insert(0, f"// {current}\n{code}")
        m = re.search(r'class\s+\w+\s+extends\s+(\w+)', code or '')
        current = m.group(1) if m else None

    full_code = '\n\n'.join(codes)

    fields = _extract_dto_fields(class_name, deps)
    if not fields:
        return {}

    field_list = json.dumps([{"name": f["name"], "type": f["type"]} for f in fields], indent=2)

    try:
        prompt = _DTO_CONSTRAINT_PROMPT % (full_code, field_list, str(_SCHEMA_CONSTRAINT))
        r = chat([{"role": "user", "content": prompt}], provider=provider, temperature=temperature, max_retries=3)
        raw = r.get("constraints", [])
    except Exception:
        return {}

    result = {}
    for c in raw:
        name = c.get("name", "")
        result[name] = {
            k: v for k, v in c.items()
            if k != "name" and v is not None and v != "" and v != [] and v != {}
        }
    return result


def _apply_dto_constraints(enriched_results, step2_map, provider, temperature):
    """Post-process: for all params with _class_name, extract DTO constraints
    once per class and write them into each matching param."""
    # Collect unique DTO classes
    dto_classes = set()
    for tid, endpoints in enriched_results.items():
        for ep in endpoints:
            for p in ep.get("parameters", []):
                cn = p.get("_class_name")
                if cn:
                    dto_classes.add(cn)

    if not dto_classes:
        return

    # Get one deps dict per task_id for filesystem DTO lookup
    task_deps = {}
    for tid in enriched_results:
        entry_to_deps = step2_map.get(tid, {}).get("entry_to_deps", {})
        if entry_to_deps:
            task_deps[tid] = next(iter(entry_to_deps.values()))

    if not dto_classes:
        return

    logger.info(f"Step5 DTO: extracting constraints for {len(dto_classes)} classes: {list(dto_classes)}")

    # Extract constraints for each unique DTO class (use any task's deps for filesystem access)
    any_deps = next(iter(task_deps.values())) if task_deps else {"entry_code_file": ""}
    constraints_cache = {}
    for cn in dto_classes:
        constraints_cache[cn] = _extract_dto_constraints(cn, any_deps, provider, temperature)

    # Apply to all matching params
    applied = 0
    for endpoints in enriched_results.values():
        for ep in endpoints:
            for p in ep.get("parameters", []):
                cn = p.get("_class_name")
                if cn and cn in constraints_cache:
                    fc = constraints_cache[cn].get(p["name"], {})
                    for ck in _CONSTRAINT_KEYS:
                        if ck in fc:
                            p[ck] = fc[ck]
                    if "require" in fc:
                        p["require"] = fc["require"]
                    applied += 1

    # Strip _class_name markers (no longer needed)
    for endpoints in enriched_results.values():
        for ep in endpoints:
            for p in ep.get("parameters", []):
                p.pop("_class_name", None)

    logger.info(f"Step5 DTO: applied constraints to {applied} params")


def _assemble_codes(entry_file_path, deps):
    codes = f'Entry_code({entry_file_path}):\n<<<\n{deps["entry_code_file"]}\n>>>\n'
    for key, code in deps.items():
        if key != "entry_code_file":
            codes += f'\nRelated_code({key}):\n<<<\n{code}\n>>>\n'
    return codes


def run_parallel(step4_results, step2_map, api_map, provider="deepseek", temperature=0.2, max_workers=10, cross_validate=False):
    """
    Enrich parameters with constraints for all endpoints.

    Args:
        step4_results: dict mapping task_id -> list of endpoint dicts (from step4)
        step2_map: dict mapping task_id -> step2_result (for code files)
        api_map: dict mapping task_id -> api dict (for framework info)
        cross_validate: if True, use 3-LLM voting per endpoint (Section 4.1)
    Returns:
        (enriched_results_by_task, total_constraints)
    """
    # Build an index to update: keyed by (task_id, source_file, method_name, path, http_method)
    ep_index = {}
    for tid, endpoints in step4_results.items():
        for ep in endpoints:
            key = (tid, ep.get("source_file", ""), ep.get("method_name", ""),
                   ep.get("endpoint_path", ""), ep.get("http_method", ""))
            ep_index[key] = ep

    # Also store the API name for reporting
    api_names = {}
    for tid, endpoints in step4_results.items():
        if endpoints:
            api_names[tid] = endpoints[0].get("api_name", tid)

    work_items = []
    for (tid, src, mn, ep_path, http_m), ep in ep_index.items():
        s2 = step2_map.get(tid, {})
        entry_to_deps = s2.get("entry_to_deps", {})
        entry_path = src
        deps = entry_to_deps.get(entry_path, {"entry_code_file": ""})
        params = ep.get("parameters", [])
        if not params:
            continue
        work_items.append((entry_path, deps, ep, params, provider, temperature, tid, cross_validate))

    if not work_items:
        logger.info("Step5: no parameters with constraints to extract")
        return step4_results, 0

    logger.info(f"Step5 dispatching {len(work_items)} endpoints to {max_workers} workers")

    done = 0
    total = len(work_items)
    total_constraints = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for entry_path, deps, ep, params, provider, temperature, tid, cv in work_items:
            key = (tid, ep.get("source_file", ""), ep.get("method_name", ""), ep.get("endpoint_path", ""), ep.get("http_method", ""))
            futures[pool.submit(_process_constraints,
                (entry_path, deps, ep, params, provider, temperature, tid, cv))] = key

        for fut in as_completed(futures):
            key = futures[fut]
            enriched_params, err = fut.result()
            done += 1
            # Update in-place
            if key in ep_index:
                ep_index[key]["parameters"] = enriched_params
                if err:
                    ep_index[key].setdefault("errors", []).append(f"constraints: {err}")
            if done % 50 == 0 or done == total:
                n_c = count_constraints_in(step4_results)
                logger.step("Step5", done, total, f"{n_c} constraints")

    # Post-process: extract constraints from DTO classes and apply to expanded params
    _apply_dto_constraints(step4_results, step2_map, provider, temperature)

    total_constraints = count_constraints_in(step4_results)
    return step4_results, total_constraints


def count_constraints_in(results_by_task):
    n = 0
    for endpoints in results_by_task.values():
        for ep in endpoints:
            for p in ep.get("parameters", []):
                for key in ["min", "max", "min_length", "max_length", "format", "enum", "dictionary", "default_value"]:
                    v = p.get(key)
                    if v is not None and v != "" and v != [] and v != {}:
                        n += 1
                req = p.get("require", False)
                if isinstance(req, bool) and req:
                    n += 1
                elif isinstance(req, str) and req.lower() == "true":
                    n += 1
    return n
