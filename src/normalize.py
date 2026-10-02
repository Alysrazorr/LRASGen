
import re


def path(raw, strip_prefix=""):
    """Normalize an endpoint path for comparison.

    Path variable names carry no meaning for matching, so every placeholder
    collapses to "{}". ``strip_prefix`` drops a leading base-path segment; it is
    a parameter rather than module state so that callers probing different
    prefixes cannot affect one another.
    """
    if raw is None:
        return ""
    p = str(raw).strip().replace("\\", "/")
    p = re.sub(r"/+", "/", p)
    p = re.sub(r"\{([^}:]+):[^}]*\}", r"{\1}", p)
    p = re.sub(r"\{[^}]*\}", "{}", p)
    if strip_prefix:
        pre = "/" + strip_prefix.strip("/")
        if p == pre:
            p = "/"
        elif p.startswith(pre + "/"):
            p = p[len(pre):]
    p = p.rstrip("/")
    return p or "/"


def method(raw):
    return str(raw or "").strip().upper()


def parameter_name(raw):
    """Fold the naming styles that spell one parameter several ways.

    "sortBy", "sort_by" and "SORT_BY" name the same query key, so the difference
    is a naming convention and not a semantic one. This is a comparison rule: the
    pipeline keeps the name the source actually declares, because the name in a
    specification has to be the one the server accepts.
    """
    return re.sub(r"[_\-\s]", "", str(raw or "")).lower()


def status(raw):
    if raw is None:
        return ""
    s = str(raw).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


TYPE_MAP = {
    "string": "string", "str": "string", "char": "string", "character": "string",
    "uuid": "string", "date": "string", "localdate": "string", "datetime": "string",
    "localdatetime": "string", "instant": "string", "timestamp": "string",
    "zoneddatetime": "string", "offsetdatetime": "string", "httpmethod": "string",
    "multipartfile": "string", "file": "string",
    "int": "integer", "integer": "integer", "long": "integer", "short": "integer",
    "byte": "integer", "biginteger": "integer",
    "number": "number", "float": "number", "double": "number",
    "bigdecimal": "number", "decimal": "number",
    "bool": "boolean", "boolean": "boolean",
    "array": "array", "list": "array", "set": "array", "collection": "array",
    "iterable": "array", "treeset": "array", "hashset": "array",
    "linkedhashset": "array", "arraylist": "array", "linkedlist": "array",
    "object": "object", "map": "object", "dictionary": "object",
    "hashmap": "object", "linkedhashmap": "object", "treemap": "object",
}
TYPE_DEFAULT = "object"


def type_name(raw):
    if raw is None:
        return ""
    # Kotlin marks a nullable type with a trailing "?", which says nothing about
    # the kind of value, so it is dropped before the lookup.
    t = str(raw).strip().rstrip("?")
    if not t:
        return ""
    if t.endswith("[]"):
        return "array"
    m = re.match(r"^([A-Za-z_][\w.]*)<", t)
    if m and TYPE_MAP.get(m.group(1).lower()) == "array":
        return "array"
    return TYPE_MAP.get(t.split(".")[-1].lower(), TYPE_DEFAULT)


PIPELINE_CONSTRAINT_MAP = {
    "require": "required",
    "min": "min_value", "max": "max_value",
    "min_length": "min_length", "max_length": "max_length",
    "format": "format", "enum": "enum", "dictionary": "dictionary",
}

# Constraint fields that are their own kind: they are not folded into a shared
# category, but they still count as constraints.
KIND_OF_FIELD = dict(PIPELINE_CONSTRAINT_MAP)
KIND_OF_FIELD.update({
    "pattern": "pattern", "default_value": "default_value", "not_null": "not_null",
    "items": "items", "min_items": "min_items", "properties": "properties",
    "exclusiveMin": "exclusiveMin", "unique_items": "unique_items",
})

FIELD_OF_KIND = {kind: field for field, kind in KIND_OF_FIELD.items()}


def constraint_kinds(param):
    kinds = set()
    for field, value in param.items():
        kind = KIND_OF_FIELD.get(field)
        if kind is None:
            continue
        if value is None or value == "" or value == [] or value == {}:
            continue
        if field == "require" and str(value).strip().lower() != "true":
            continue
        kinds.add(kind)
    return sorted(kinds)


def endpoint_entities(result, strip_prefix=""):
    out = {}
    for e in result.get("endpoints", []):
        if not isinstance(e, dict):
            continue
        out.setdefault((path(e.get("endpoint_path"), strip_prefix),
                        method(e.get("http_method"))), e)
    return out


def rebuild_endpoints(entities):
    return {"endpoints": list(entities)}


def parameter_type(p):
    t = type_name(p.get("type"))
    if t == TYPE_DEFAULT and p.get("enum"):
        return "string"
    return t


def parameter_entities(result):
    out = {}
    for p in result.get("parameters", []):
        if not isinstance(p, dict):
            continue
        out.setdefault((str(p.get("name", "")).strip(), parameter_type(p)), p)
    return out


def rebuild_parameters(entities):
    return {"parameters": list(entities)}


def response_entities(result):
    out = {}
    for r in result.get("responses", []):
        if not isinstance(r, dict):
            continue
        out.setdefault((status(r.get("status_code")),), r)
    return out


def rebuild_responses(entities):
    return {"responses": list(entities)}


def constraint_entities(result):
    out = {}
    for c in result.get("constraints", []):
        if not isinstance(c, dict):
            continue
        name = str(c.get("name", "")).strip()
        for kind in constraint_kinds(c):
            field = FIELD_OF_KIND.get(kind)
            if field is None:
                continue
            out.setdefault((name, kind), {"name": name, field: c[field]})
    return out


def rebuild_constraints(entities):
    by_name = {}
    for entity in entities:
        name = entity["name"]
        merged = by_name.setdefault(name, {"name": name})
        merged.update({k: v for k, v in entity.items() if k != "name"})
    return {"constraints": list(by_name.values())}
