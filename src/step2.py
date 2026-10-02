
import ast
import os
import re
import time
from pathlib import Path

from config import MAX_IMPORT_DEPTH
from frameworks import FRAMEWORKS


def _read_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def _build_index(root, extensions):
    by_basename = {}
    by_relpath = {}
    all_fpaths = set()
    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in extensions:
                continue
            fpath = os.path.join(dirpath, fname)
            all_fpaths.add(fpath)
            basename = os.path.splitext(fname)[0]
            by_basename.setdefault(basename, []).append(fpath)
            rel = os.path.relpath(fpath, root)
            rel_no_ext = os.path.splitext(rel)[0].replace("\\", "/")
            by_relpath[rel_no_ext] = fpath
    return by_basename, by_relpath, all_fpaths


_JAVA_IMPORT_RE = re.compile(r"import\s+(?:static\s+)?([\w.*]+);")
_KOTLIN_IMPORT_RE = re.compile(r"import\s+([\w.*]+)")


def _parse_java_imports(file_path):
    pattern = _KOTLIN_IMPORT_RE if file_path.endswith(".kt") else _JAVA_IMPORT_RE
    try:
        for m in pattern.finditer(_read_file(file_path)):
            yield m.group(1)
    except Exception:
        pass


def _resolve_java_import(imp, by_relpath, by_basename):
    key = imp.replace(".", "/")
    if key in by_relpath:
        return by_relpath[key]
    last = imp.rsplit(".", 1)[-1]
    candidates = by_basename.get(last, [])
    for c in candidates:
        if key in c.replace("\\", "/"):
            return c
    return candidates[0] if len(candidates) == 1 else None


def _clean_java_code(file_path):
    lines = _read_file(file_path).splitlines(keepends=True)
    cleaned = []
    skip = True
    for line in lines:
        stripped = line.strip()
        if skip and (stripped.startswith("package") or stripped.startswith("import")
                     or stripped.startswith("//") or stripped.startswith("/*")
                     or stripped.startswith("*") or stripped == ""):
            continue
        if skip and stripped and not stripped.startswith(("//", "/*", "*")):
            skip = False
        if not skip:
            cleaned.append(line)
    return "".join(cleaned)


def _referenced_siblings(file_path, extensions):
    directory = os.path.dirname(file_path)
    own = os.path.splitext(os.path.basename(file_path))[0]
    code = _read_file(file_path)
    siblings = []
    for name in os.listdir(directory):
        if os.path.splitext(name)[1].lower() not in extensions:
            continue
        simple = os.path.splitext(name)[0]
        if simple == own:
            continue
        path = os.path.join(directory, name)
        if os.path.isfile(path) and re.search(r"\b%s\b" % re.escape(simple), code):
            siblings.append(path)
    return siblings


_SUN_HANDLER_RE = re.compile(r"implements\s+\w*HttpHandler\b")
_HTTP_EXCHANGE_RE = re.compile(r"\bHttpExchange\b")
_PATH_ROUTING_RE = re.compile(
    r"(?:path|uri|url)\s*\.\s*(?:equals|startsWith|endsWith|contains|matches)\s*\(")


def is_sun_handler(file_path):
    return bool(_SUN_HANDLER_RE.search(_read_file(file_path)))


def _siblings_in(paths, extensions):
    known = set(paths)
    out = []
    for source in paths:
        directory = os.path.dirname(source)
        own = os.path.splitext(os.path.basename(source))[0]
        code = _read_file(source)
        for name in sorted(os.listdir(directory)):
            if os.path.splitext(name)[1].lower() not in extensions:
                continue
            simple = os.path.splitext(name)[0]
            if simple == own:
                continue
            candidate = os.path.join(directory, name)
            if candidate in known or not os.path.isfile(candidate):
                continue
            if re.search(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(simple), code):
                known.add(candidate)
                out.append(candidate)
    return out


def _resolve_sun_handler_deps(entry_path, root, extensions):
    resolved = {"entry_code_file": _clean_java_code(entry_path)}
    directory = os.path.dirname(entry_path)
    routing = []
    for name in sorted(os.listdir(directory)):
        if os.path.splitext(name)[1].lower() not in extensions:
            continue
        path = os.path.join(directory, name)
        if path == entry_path or not os.path.isfile(path):
            continue
        code = _read_file(path)
        if _HTTP_EXCHANGE_RE.search(code) and _PATH_ROUTING_RE.search(code):
            resolved[path] = _clean_java_code(path)
            routing.append(path)

    for extra in _siblings_in([entry_path] + routing, extensions):
        resolved[extra] = _clean_java_code(extra)
    return resolved


def _resolve_java_deps(entry_path, root, extensions):
    if is_sun_handler(entry_path):
        return _resolve_sun_handler_deps(entry_path, root, extensions)

    by_basename, by_relpath, _ = _build_index(root, extensions)
    resolved = {"entry_code_file": _clean_java_code(entry_path)}
    visited = {entry_path}
    queue = [(entry_path, 0)]

    while queue:
        current, depth = queue.pop(0)
        if depth >= MAX_IMPORT_DEPTH:
            continue

        candidates = list(_referenced_siblings(current, extensions))
        candidates += [_resolve_java_import(imp, by_relpath, by_basename)
                       for imp in _parse_java_imports(current)]
        for path in candidates:
            if path and path not in visited:
                visited.add(path)
                queue.append((path, depth + 1))
                resolved[path] = _clean_java_code(path)

        _add_extends_parent(current, depth, by_basename, extensions, visited, queue, resolved)
    return resolved


def _add_extends_parent(dep_path, depth, by_basename, extensions, visited, queue, resolved):
    try:
        code = _read_file(dep_path)
    except Exception:
        return
    m = re.search(r'class\s+\w+\s+extends\s+(\w+)', code)
    if not m:
        return
    parent_name = m.group(1)
    if parent_name in ('Object', 'Object()'):
        return
    candidates = by_basename.get(parent_name, [])
    for c in candidates:
        if c not in visited:
            visited.add(c)
            queue.append((c, depth + 1))
            resolved[c] = _clean_java_code(c)
            _add_extends_parent(c, depth + 1, by_basename, extensions, visited, queue, resolved)
            break


_CSHARP_USING_RE = re.compile(r"using\s+([\w.]+)\s*;")


def _parse_csharp_usings(file_path):
    try:
        for m in _CSHARP_USING_RE.finditer(_read_file(file_path)):
            yield m.group(1)
    except Exception:
        pass


def _resolve_csharp_using(ns, by_relpath, by_basename):
    key = ns.replace(".", "/")
    if key in by_relpath:
        return by_relpath[key]

    parts = ns.split(".")
    for i in range(1, len(parts)):
        suffix = "/".join(parts[i:])
        matches = sorted(p for p in by_relpath if p.startswith(suffix + "/"))
        if matches:
            return [by_relpath[p] for p in matches]

    last = ns.rsplit(".", 1)[-1]
    candidates = by_basename.get(last, [])
    for c in candidates:
        if key in c.replace("\\", "/"):
            return c
    return candidates[0] if len(candidates) == 1 else None


def _clean_csharp_code(file_path):
    lines = _read_file(file_path).splitlines(keepends=True)
    return "".join(l for l in lines if not l.strip().startswith("using "))


def _resolve_csharp_deps(entry_path, root):
    by_basename, by_relpath, _ = _build_index(root, {".cs"})
    resolved = {"entry_code_file": _clean_csharp_code(entry_path)}
    visited = {entry_path}
    queue = [(entry_path, 0)]

    while queue:
        current, depth = queue.pop(0)
        if depth >= MAX_IMPORT_DEPTH:
            continue
        for ns in _parse_csharp_usings(current):
            dep = _resolve_csharp_using(ns, by_relpath, by_basename)
            if not dep:
                continue
            if isinstance(dep, list):
                for d in dep:
                    if d not in visited:
                        visited.add(d)
                        queue.append((d, depth + 1))
                        resolved[d] = _clean_csharp_code(d)
            elif dep not in visited:
                visited.add(dep)
                queue.append((dep, depth + 1))
                resolved[dep] = _clean_csharp_code(dep)
    return resolved


def _parse_python_imports(file_path):
    try:
        node = ast.parse(_read_file(file_path), filename=file_path)
    except Exception:
        return
    for n in ast.walk(node):
        if isinstance(n, ast.ImportFrom):
            if n.module:
                yield (n.module, n.level)
                # `from libs import mlmmj` pulls in a submodule, and naming only
                # the package would stop the walk at libs/__init__.py.
                for alias in n.names:
                    if alias.name != "*":
                        yield (f"{n.module}.{alias.name}", n.level)
        elif isinstance(n, ast.Import):
            for alias in n.names:
                yield (alias.name, 0)


def _resolve_python_import(module, level, current_file, root, all_py):
    cur_dir = os.path.dirname(current_file)
    if level > 0:
        target_dir = cur_dir
        for _ in range(level - 1):
            target_dir = os.path.dirname(target_dir)
        candidates = [
            os.path.join(target_dir, module.replace(".", os.sep) + ".py"),
            os.path.join(target_dir, module.replace(".", os.sep), "__init__.py"),
        ]
    else:
        parts = module.split(".")
        candidates = [
            os.path.join(root, *parts) + ".py",
            os.path.join(root, *parts) + ".py.sample",
            os.path.join(root, *parts, "__init__.py"),
        ]
        for i in range(len(parts), 0, -1):
            partial = os.path.join(root, *parts[:i])
            candidates.append(partial + ".py")
            candidates.append(partial + ".py.sample")
            candidates.append(os.path.join(partial, "__init__.py"))
    for c in candidates:
        c = os.path.normpath(c)
        if c in all_py:
            return c
        # A settings module often ships as a template that the deployment copies
        # to .py, so the template is the only copy that exists in the source tree.
        # It is not part of all_py, which holds .py files only.
        if c.endswith(".py.sample") and os.path.isfile(c):
            return c
    return None


def _clean_python_code(file_path):
    lines = _read_file(file_path).splitlines(keepends=True)
    return "".join(l for l in lines
                   if not (l.lstrip().startswith("import ") or l.lstrip().startswith("from ")))


def _resolve_python_deps(entry_path, root):
    all_py = set()
    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            if fname.endswith(".py"):
                all_py.add(os.path.join(dirpath, fname))

    resolved = {"entry_code_file": _clean_python_code(entry_path)}
    visited = {entry_path}
    queue = [(entry_path, 0)]

    while queue:
        current, depth = queue.pop(0)
        if depth >= MAX_IMPORT_DEPTH:
            continue
        for module, level in _parse_python_imports(current):
            dep = _resolve_python_import(module, level, current, root, all_py)
            if dep and dep not in visited:
                visited.add(dep)
                queue.append((dep, depth + 1))
                resolved[dep] = _clean_python_code(dep)
    return resolved


_TS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[\w*\s{},]*)\s*from\s*['"]([^'"]+)['"]"""
    r"""|import\s+['"]([^'"]+)['"]"""
    r"""|require\s*\(\s*['"]([^'"]+)['"]\s*\))"""
)


def _parse_js_ts_imports(file_path):
    try:
        for m in _TS_IMPORT_RE.finditer(_read_file(file_path)):
            mod = m.group(1) or m.group(2) or m.group(3)
            if mod and mod.startswith("."):
                yield mod
    except Exception:
        pass


def _resolve_js_ts_import(mod, current_file, root):
    cur_dir = os.path.dirname(current_file)
    base = os.path.normpath(os.path.join(cur_dir, mod))
    for ext in (".ts", ".js", ".tsx", ".jsx"):
        if base.endswith(ext) and os.path.isfile(base):
            candidate = base
        else:
            candidate = base + ext
            if not os.path.isfile(candidate):
                candidate = os.path.join(base, "index" + ext)
                if not os.path.isfile(candidate):
                    continue
        if os.path.commonpath([os.path.abspath(candidate), os.path.abspath(root)]) == os.path.abspath(root):
            return candidate
    return None


def _clean_js_ts_code(file_path):
    lines = _read_file(file_path).splitlines(keepends=True)
    return "".join(l for l in lines
                   if not (l.lstrip().startswith("import ") or l.lstrip().startswith("export {")))


def _resolve_js_ts_deps(entry_path, root):
    resolved = {"entry_code_file": _clean_js_ts_code(entry_path)}
    visited = {entry_path}
    queue = [(entry_path, 0)]

    while queue:
        current, depth = queue.pop(0)
        if depth >= MAX_IMPORT_DEPTH:
            continue
        for mod in _parse_js_ts_imports(current):
            dep = _resolve_js_ts_import(mod, current, root)
            if dep and dep not in visited:
                visited.add(dep)
                queue.append((dep, depth + 1))
                resolved[dep] = _clean_js_ts_code(dep)
    return resolved


def _drop_excluded(deps, root, exclude_deps):
    """Remove dependencies that sit in a vendored or generated directory.

    A vendored copy of a framework is followed like any other local package, so
    it can bury the project's own code under tens of thousands of lines. The
    entry file itself is never dropped.
    """
    if not exclude_deps:
        return deps
    prefixes = []
    for name in exclude_deps:
        path = os.path.normpath(os.path.join(root, name.replace("\\", "/").strip("/")))
        prefixes.append(path + os.sep)

    kept = {"entry_code_file": deps.get("entry_code_file", "")}
    for path, code in deps.items():
        if path == "entry_code_file":
            continue
        norm = os.path.normpath(path)
        if not any(norm.startswith(prefix) for prefix in prefixes):
            kept[path] = code
    return kept


_LANG_HANDLERS = {
    "java":       lambda p, r: _resolve_java_deps(p, r, {".java"}),
    "kotlin":     lambda p, r: _resolve_java_deps(p, r, {".kt"}),
    "csharp":     lambda p, r: _resolve_csharp_deps(p, r),
    "python":     lambda p, r: _resolve_python_deps(p, r),
    "javascript": lambda p, r: _resolve_js_ts_deps(p, r),
    "typescript": lambda p, r: _resolve_js_ts_deps(p, r),
}

_NEXTJS_FRAMEWORKS = {"nextjs"}

_ADVICE_RE = re.compile(r"@(?:Rest)?ControllerAdvice(?![A-Za-z0-9_])")
_ADVICE_EXTENSIONS = {"java": {".java"}, "kotlin": {".kt"}}


def _advice_files(root, extensions):
    if not extensions:
        return []
    found = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if os.path.splitext(name)[1].lower() not in extensions:
                continue
            path = os.path.join(dirpath, name)
            if _ADVICE_RE.search(_read_file(path)):
                found.append(path)
    return found


def main(api, step1_files):
    fw = FRAMEWORKS[api["framework"]]
    lang = fw["language"]
    root = api["path"]
    start = time.time()

    is_nextjs = api["framework"] in _NEXTJS_FRAMEWORKS
    advice = _advice_files(root, _ADVICE_EXTENSIONS.get(lang, set()))
    entry_to_deps = {}
    total_deps = 0

    for entry in step1_files:
        fpath = entry["file_path"]
        if not os.path.isfile(fpath) or not any(
            fpath.endswith(ext) for ext in
            (".java", ".kt", ".cs", ".py", ".js", ".ts", ".jsx", ".tsx")
        ):
            continue

        if is_nextjs:
            deps = {"entry_code_file": _clean_js_ts_code(fpath)}
        else:
            handler = _LANG_HANDLERS.get(lang)
            if handler is None:
                raise NotImplementedError(f"No step2 handler for language '{lang}'")
            deps = handler(fpath, root)

        if deps:
            deps = _drop_excluded(deps, root, api.get("exclude_deps", []))
            for extra in advice:
                if extra != fpath and extra not in deps:
                    deps[extra] = _clean_java_code(extra)
            entry_to_deps[fpath] = deps
            total_deps += len(deps) - 1

    return {
        "task_id": None,
        "api_name": api["name"],
        "framework": api["framework"],
        "entry_to_deps": entry_to_deps,
        "duration_ms": round((time.time() - start) * 1000),
    }
