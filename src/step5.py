
import json
import os
import re

import logger
from config import STEP5_MAX_WORKERS
import llm
from llm import ask
from normalize import constraint_entities, rebuild_constraints
from step4 import _find_dto_file, _extract_dto_fields

# The constraint fields a parameter can carry. The pass that asked a model for
# them one endpoint at a time is gone, but the DTO pass still reads them back
# off the answer, so the vocabulary stays here.
_CONSTRAINT_KEYS = {"min", "max", "min_length", "max_length", "format", "enum",
                    "dictionary"}

# The shape the DTO answer takes, shown to the model as the format to follow.
_EXAMPLE_CONSTRAINT = {
    "constraints": [
        {
            "name": "str_param",
            "require": "true",
            "max_length": "128",
            "min_length": "16",
            "format": "yyyy-mm-dd hh24:mi:ss",
            "enum": ["enum1", "enum2", "enum3"],
        },
        {
            "name": "num_param",
            "min": 2,
            "max": 16,
        },
    ],
}


_DTO_CONSTRAINT_PROMPT = """\
## Source Code

```
%s
```

## Questions

In the source code, there is a DTO class whose fields are:
```
%s
```

Read Source Code, and answer the following questions for every field in that list:
    What is the field's name, field's type, field's description and whether the field is required?
    If the field's type is string, what is its length range?
    If the field's type is string and resembles a date or datetime format, what is its possible date-format placeholders?
    If the field's type is integer, what is its value range?
    If the field is an enumeration or dictionary, what is the enumeration value or dictionary value?

## How to read the annotations

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

## Rules

- You must answer every question for every field, one entry per field.
- Write a constraint only where the code states it, and leave the field out everywhere else. The annotations listed above and a field initializer are what state one; a value the code never mentions is not a property of the field, so do not supply it from the field's type or from what such a value usually looks like.
- You must extract information from the specified code to answer the questions.
- You must answer the questions according to the JSON format: %s."""


def _extract_dto_constraints(class_name, deps):
    import re
    codes = []
    current = class_name
    seen = set()
    while current and current not in seen and current not in ('Object', 'Object()'):
        seen.add(current)
        code = _find_dto_file(current, deps)
        if code:
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
        prompt = _DTO_CONSTRAINT_PROMPT % (full_code, field_list,
                                           json.dumps(_EXAMPLE_CONSTRAINT, indent=4))
        r, _ = ask([{"role": "user", "content": prompt}],
                   extract=constraint_entities, rebuild=rebuild_constraints)
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


def _apply_dto_constraints(enriched_results, step2_map):
    dto_classes = set()
    for tid, endpoints in enriched_results.items():
        for ep in endpoints:
            for p in ep.get("parameters", []):
                cn = p.get("_class_name")
                if cn:
                    dto_classes.add(cn)

    if not dto_classes:
        return

    task_deps = {}
    for tid in enriched_results:
        entry_to_deps = step2_map.get(tid, {}).get("entry_to_deps", {})
        if entry_to_deps:
            task_deps[tid] = next(iter(entry_to_deps.values()))

    if not dto_classes:
        return

    logger.info(f"Step5 DTO: extracting constraints for {len(dto_classes)} classes: {list(dto_classes)}")

    any_deps = next(iter(task_deps.values())) if task_deps else {"entry_code_file": ""}
    constraints_cache = {}
    for cn in dto_classes:
        constraints_cache[cn] = _extract_dto_constraints(cn, any_deps)

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


def run_parallel(step4_results, step2_map, api_map, max_workers=STEP5_MAX_WORKERS):
    """Add the constraints a parameter's class declares.

    The per-endpoint constraint pass is gone: step4 asks each parameter for its
    constraints alongside the parameter itself, in the same call that has the
    handler in front of it. The DTO pass stays because it reads a different
    source, the class the parameter is typed as, which the handler never shows.
    """
    # The parameters already carry what the handler's own code states, because
    # step4 asks for the parameter and its constraints in one call. What is left
    # to add is what the handler does not show: a parameter whose type is a
    # class takes its constraints from that class, and the class has to be read
    # on its own.
    _apply_dto_constraints(step4_results, step2_map)

    total_constraints = count_constraints_in(step4_results)
    return step4_results, total_constraints


def count_constraints_in(results_by_task):
    n = 0
    for endpoints in results_by_task.values():
        for ep in endpoints:
            for p in ep.get("parameters", []):
                for key in ["min", "max", "min_length", "max_length", "format", "enum", "dictionary"]:
                    v = p.get(key)
                    if v is not None and v != "" and v != [] and v != {}:
                        n += 1
                req = p.get("require", False)
                if isinstance(req, bool) and req:
                    n += 1
                elif isinstance(req, str) and req.lower() == "true":
                    n += 1
    return n
