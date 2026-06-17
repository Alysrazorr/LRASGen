"""
Step 2 — Code extraction and cleaning.

For each endpoint entry file: resolve imports, keep only those that can be
found inside the project root directory, recurse (unlimited depth), read and
clean source code.
"""

import ast
import os
import re
import time
from pathlib import Path

from frameworks import FRAMEWORKS

_MAX_DEPTH = 99  # effectively unlimited, like the original code


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _read_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def _build_index(root, extensions):
    """
    Index all project files by (a) basename without extension, and
    (b) path relative to root (dotted → path with slashes, no extension).
    Returns (by_basename, by_relpath, all_fpaths).
    """
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


# ---------------------------------------------------------------------------
# Java / Kotlin
# ---------------------------------------------------------------------------
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
    """Try to resolve a Java/Kotlin import to a file inside the project."""
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


def _resolve_java_deps(entry_path, root, extensions):
    by_basename, by_relpath, _ = _build_index(root, extensions)
    resolved = {"entry_code_file": _clean_java_code(entry_path)}
    visited = {entry_path}
    queue = [(entry_path, 0)]

    # Also include same-package files: classes in the same directory are
    # referenced without an import statement (e.g. JDK HttpHandler pattern).
    entry_dir = os.path.dirname(entry_path)
    for fname in os.listdir(entry_dir):
        fpath = os.path.join(entry_dir, fname)
        ext = os.path.splitext(fname)[1].lower()
        if ext in extensions and os.path.isfile(fpath) and fpath not in visited:
            visited.add(fpath)
            queue.append((fpath, 1))
            resolved[fpath] = _clean_java_code(fpath)

    _JAVA_EXTENDS_RE = re.compile(r'class\s+\w+\s+extends\s+(\w+)')

    while queue:
        current, depth = queue.pop(0)
        if depth >= _MAX_DEPTH:
            continue
        for imp in _parse_java_imports(current):
            dep = _resolve_java_import(imp, by_relpath, by_basename)
            if dep and dep not in visited:
                visited.add(dep)
                queue.append((dep, depth + 1))
                resolved[dep] = _clean_java_code(dep)
                # Also include same-package files (classes referenced without imports,
                # e.g. parent classes via extends, sub-resources via factory pattern)
                dep_dir = os.path.dirname(dep)
                for fname in os.listdir(dep_dir):
                    fpath = os.path.join(dep_dir, fname)
                    ext = os.path.splitext(fname)[1].lower()
                    if ext in extensions and os.path.isfile(fpath) and fpath not in visited:
                        visited.add(fpath)
                        queue.append((fpath, depth + 1))
                        resolved[fpath] = _clean_java_code(fpath)
                # Also resolve parent class chain (extends)
                _add_extends_parent(dep, depth, by_basename, extensions, visited, queue, resolved)
    return resolved


def _add_extends_parent(dep_path, depth, by_basename, extensions, visited, queue, resolved):
    """If the given Java file extends a parent class in the project, add it."""
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
            # Recurse: parent might also extend something
            _add_extends_parent(c, depth + 1, by_basename, extensions, visited, queue, resolved)
            break  # Only take the first match


# ---------------------------------------------------------------------------
# C#
# ---------------------------------------------------------------------------
_CSHARP_USING_RE = re.compile(r"using\s+([\w.]+)\s*;")


def _parse_csharp_usings(file_path):
    try:
        for m in _CSHARP_USING_RE.finditer(_read_file(file_path)):
            yield m.group(1)
    except Exception:
        pass


def _resolve_csharp_using(ns, by_relpath, by_basename):
    """Resolve a C# using namespace to file paths.

    Returns a single path, or a list of paths when the namespace maps to a
    directory containing multiple files.
    """
    key = ns.replace(".", "/")
    if key in by_relpath:
        return by_relpath[key]

    # Try progressive suffix: strip project-name prefix segments.
    # e.g. "Bit.Api.Models.Request" → try "Api/Models/Request",
    # "Models/Request" — matching files under that directory.
    parts = ns.split(".")
    for i in range(1, len(parts)):
        suffix = "/".join(parts[i:])
        matches = sorted(p for p in by_relpath if p.startswith(suffix + "/"))
        if matches:
            return [by_relpath[p] for p in matches]

    # Basename fallback: last namespace segment as a file name.
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
        if depth >= _MAX_DEPTH:
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


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------
def _parse_python_imports(file_path):
    """Yield (module, level) for non-stdlib imports."""
    try:
        node = ast.parse(_read_file(file_path), filename=file_path)
    except Exception:
        return
    for n in ast.walk(node):
        if isinstance(n, ast.ImportFrom):
            if n.module:
                yield (n.module, n.level)
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
            os.path.join(root, *parts, "__init__.py"),
        ]
        for i in range(len(parts), 0, -1):
            partial = os.path.join(root, *parts[:i])
            candidates.append(partial + ".py")
            candidates.append(os.path.join(partial, "__init__.py"))
    for c in candidates:
        c = os.path.normpath(c)
        if c in all_py:
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
        if depth >= _MAX_DEPTH:
            continue
        for module, level in _parse_python_imports(current):
            dep = _resolve_python_import(module, level, current, root, all_py)
            if dep and dep not in visited:
                visited.add(dep)
                queue.append((dep, depth + 1))
                resolved[dep] = _clean_python_code(dep)
    return resolved


# ---------------------------------------------------------------------------
# TypeScript / JavaScript — only relative imports (./ or ../)
# ---------------------------------------------------------------------------
_TS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[\w*\s{},]*)\s*from\s*['"]([^'"]+)['"]"""
    r"""|import\s+['"]([^'"]+)['"]"""
    r"""|require\s*\(\s*['"]([^'"]+)['"]\s*\))"""
)


def _parse_js_ts_imports(file_path):
    """Only relative imports (./ or ../) point to project files."""
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
        # Ensure the resolved file is within the project root directory
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
        if depth >= _MAX_DEPTH:
            continue
        for mod in _parse_js_ts_imports(current):
            dep = _resolve_js_ts_import(mod, current, root)
            if dep and dep not in visited:
                visited.add(dep)
                queue.append((dep, depth + 1))
                resolved[dep] = _clean_js_ts_code(dep)
    return resolved


# ---------------------------------------------------------------------------
# dispatcher
# ---------------------------------------------------------------------------
_LANG_HANDLERS = {
    "java":       lambda p, r: _resolve_java_deps(p, r, {".java"}),
    "kotlin":     lambda p, r: _resolve_java_deps(p, r, {".kt"}),
    "csharp":     lambda p, r: _resolve_csharp_deps(p, r),
    "python":     lambda p, r: _resolve_python_deps(p, r),
    "javascript": lambda p, r: _resolve_js_ts_deps(p, r),
    "typescript": lambda p, r: _resolve_js_ts_deps(p, r),
}

_NEXTJS_FRAMEWORKS = {"nextjs"}


def main(api, step1_files):
    fw = FRAMEWORKS[api["framework"]]
    lang = fw["language"]
    root = api["path"]
    start = time.time()

    is_nextjs = api["framework"] in _NEXTJS_FRAMEWORKS
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
            entry_to_deps[fpath] = deps
            total_deps += len(deps) - 1

    return {
        "task_id": None,
        "api_name": api["name"],
        "framework": api["framework"],
        "entry_to_deps": entry_to_deps,
        "duration_ms": round((time.time() - start) * 1000),
    }
