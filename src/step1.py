"""
Step 1 — Identify endpoint entry files.

For each API, finds the source files that contain REST endpoint definitions.
Supports two scan strategies:

  "regex"   — walk directory tree, match by suffix + content regex
  "special" — framework-specific logic (Django urls.py dispatch,
              Tornado handler list, Web.py URL routing, Next.js file routing)
"""

import os
import re
import time
from pathlib import Path

from frameworks import FRAMEWORKS


# ---------------------------------------------------------------------------
# output helpers
# ---------------------------------------------------------------------------
def _build_result(api, files):
    return {
        "task_id": None,
        "api_name": api["name"],
        "framework": api["framework"],
        "scan_type": FRAMEWORKS[api["framework"]]["scan_type"],
        "files": files,
    }


# ---------------------------------------------------------------------------
# generic regex scan
# ---------------------------------------------------------------------------
# Directories excluded from scanning for ALL APIs. Basename-only: any directory
# with one of these names is skipped, regardless of depth.
_DEFAULT_EXCLUDE_BASENAMES = {
    'target',           # Maven build output
    'build',            # Gradle build output
    '__pycache__',      # Python bytecode cache
    'node_modules',     # JS dependencies
    'dist',             # distribution / build output
    'out',              # build output
    'bin',              # binary / script output
    '.git',             # version control
    '.gradle',          # Gradle cache
    '.idea',            # JetBrains IDE config
    '.settings',        # Eclipse IDE config
}


def _scan_by_regex(api):
    """Walk the API root directory, match files by suffix + content regex."""
    fw = FRAMEWORKS[api["framework"]]
    suffix = fw["suffix"]
    patterns = [re.compile(r) for r in fw["regex"]]
    root = api["path"]
    api_exclude_dirs = api.get("exclude_dirs") or []
    matched = []

    def _prune_dirnames(dirpath, dirnames):
        """Remove globally-excluded and API-specific directories in-place."""
        keep = []
        for d in dirnames:
            # global basename excludes
            if d in _DEFAULT_EXCLUDE_BASENAMES:
                continue
            # src/test → exclude (basename is 'test', parent is 'src' or ends with '/src')
            if d == 'test' and (os.path.basename(dirpath) == 'src'
                                or dirpath.replace('\\', '/').endswith('/src')):
                continue
            # API-specific path-prefix excludes
            rel = os.path.relpath(os.path.join(dirpath, d), root).replace("\\", "/")
            excluded = False
            for pat in api_exclude_dirs:
                if rel == pat or rel.startswith(pat + "/"):
                    excluded = True
                    break
            if not excluded:
                keep.append(d)
        dirnames[:] = keep

    def _is_excluded(dirpath):
        rel = os.path.relpath(dirpath, root).replace("\\", "/")
        # check if dirpath itself matches an API-specific exclude
        for pat in api_exclude_dirs:
            if rel == pat or rel.startswith(pat + "/"):
                return True
        return False

    for dirpath, dirnames, filenames in os.walk(root):
        _prune_dirnames(dirpath, dirnames)
        if _is_excluded(dirpath):
            continue
        for fname in filenames:
            if not fname.endswith(suffix):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                continue
            for pat in patterns:
                m = pat.search(content)
                if m:
                    pos = m.start()
                    line_start = content.rfind("\n", 0, pos) + 1
                    line_end = content.find("\n", pos)
                    if line_end == -1:
                        line_end = len(content)
                    matched_line = content[line_start:line_end].strip()
                    matched.append({
                        "file_path": fpath,
                        "matched_regex": pat.pattern,
                        "matched_line": matched_line,
                    })
                    break

    # Fallback for Swagger Inflector: no annotations → parse inflector.yaml to
    # find the controller package, then return its Java files as entry files.
    if not matched:
        for dirpath, _dirnames, filenames in os.walk(root):
            if "inflector.yaml" in filenames or "inflector.yml" in filenames:
                inflector_path = os.path.join(dirpath,
                    "inflector.yaml" if "inflector.yaml" in filenames else "inflector.yml")
                matched = _handle_inflector(inflector_path, root)
                break

    return matched


def _handle_inflector(inflector_path, project_root):
    """Parse inflector.yaml, find controller package files."""
    import yaml
    matched = []
    try:
        with open(inflector_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        pkg = config.get("controllerPackage")
        if not pkg:
            return matched
        # convert dotted package to a path fragment with forward slashes
        pkg_path = pkg.replace(".", "/")
        # find java files under the controller package directory
        for dirpath, _dirnames, filenames in os.walk(project_root):
            if pkg_path in dirpath.replace("\\", "/"):
                for fname in filenames:
                    if fname.endswith(".java"):
                        fpath = os.path.join(dirpath, fname)
                        matched.append({
                            "file_path": fpath,
                            "matched_regex": None,
                            "matched_line": f"Swagger Inflector controller ({pkg})",
                        })
    except Exception:
        pass
    return matched


# ---------------------------------------------------------------------------
# framework-specific handlers
# ---------------------------------------------------------------------------
def _handle_django(api):
    """
    Django: read urls.py, parse import statements, resolve to file paths.

    Django endpoints are dispatched via urlpatterns in urls.py — the actual
    handler code lives in the imported view modules. The project root is the
    parent of the directory containing urls.py (because Django imports use the
    project package name as the top-level module, e.g. 'pokemon_v2.api').
    """
    config_file = api.get("config_file")
    if not config_file:
        raise ValueError("Django requires 'config_file' pointing to urls.py")

    # the directory containing urls.py is the Django project package;
    # project root is its parent
    urls_dir = os.path.dirname(os.path.abspath(config_file))
    project_root = os.path.dirname(urls_dir)
    imports = _parse_python_imports(config_file)
    matched = []

    for modname in imports:
        fpath = _resolve_python_module(modname, project_root)
        if fpath:
            matched.append({
                "file_path": fpath,
                "matched_regex": None,
                "matched_line": f"imported as '{modname}' from urls.py",
            })
    return matched


def _handle_tornado(api):
    """
    Tornado: search for files containing a keyword (e.g. 'default_handlers = [').

    Tornado apps register handlers in lists; the keyword identifies the file
    that defines the handler-to-class mapping.
    """
    keyword = api.get("keyword")
    if not keyword:
        raise ValueError("Tornado requires 'keyword' (e.g. 'default_handlers = [')")
    root = api["path"]
    matched = []

    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                continue
            if keyword in content:
                # find the matching line
                idx = content.find(keyword)
                line_start = content.rfind("\n", 0, idx) + 1
                line_end = content.find("\n", idx)
                if line_end == -1:
                    line_end = len(content)
                matched_line = content[line_start:line_end].strip()
                matched.append({
                    "file_path": fpath,
                    "matched_regex": keyword,
                    "matched_line": matched_line,
                })
    return matched


def _handle_webpy(api):
    """
    Web.py: extract controller class names from the URL routing list,
    resolve them to .py file paths.
    """
    urls = api.get("urls")
    if not urls:
        raise ValueError("Web.py requires 'urls' (list of URL-pattern / controller pairs)")
    root = api["path"]
    matched = []

    # urls = ['/api/(%s)$', 'controllers.profile.Profile', '/api/...', ...]
    for i in range(1, len(urls), 2):
        controller = urls[i]  # e.g. 'controllers.profile.Profile'
        module_name = ".".join(controller.split(".")[:-1])  # 'controllers.profile'
        file_name = controller.split(".")[-2] + ".py"        # 'profile.py'
        # walk project to find the file
        for dirpath, _dirnames, filenames in os.walk(root):
            for fname in filenames:
                if fname == file_name:
                    fpath = os.path.join(dirpath, fname)
                    if module_name.replace(".", os.sep) in fpath:
                        matched.append({
                            "file_path": fpath,
                            "matched_regex": None,
                            "matched_line": f"controller '{controller}' from urls",
                        })
    # deduplicate
    seen = set()
    unique = []
    for m in matched:
        if m["file_path"] not in seen:
            seen.add(m["file_path"])
            unique.append(m)
    return unique


def _handle_nextjs(api):
    """
    Next.js: collect all files under pages/api/ or app/api/ (file-based routing).

    Each .js/.ts/.jsx/.tsx file under these directories IS an endpoint handler.
    """
    root = api["path"]
    api_dirs = [
        os.path.join(root, "pages", "api"),
        os.path.join(root, "app", "api"),
        os.path.join(root, "src", "pages", "api"),
        os.path.join(root, "src", "app", "api"),
    ]
    extensions = {".js", ".ts", ".jsx", ".tsx"}
    matched = []

    for api_dir in api_dirs:
        if not os.path.isdir(api_dir):
            continue
        for dirpath, _dirnames, filenames in os.walk(api_dir):
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in extensions:
                    fpath = os.path.join(dirpath, fname)
                    # derive route from path relative to api_dir
                    rel = os.path.relpath(fpath, api_dir)
                    route = "/api/" + _nextjs_route_from_file(rel)
                    matched.append({
                        "file_path": fpath,
                        "matched_regex": None,
                        "matched_line": f"Next.js file route → {route}",
                    })
    return matched


def _nextjs_route_from_file(rel_path):
    """
    Convert a Next.js API file path to its route pattern.
    Examples:
      hello.js          → hello
      users/[id].js     → users/{id}
      items/[...slug].js → items/{slug}+
    """
    # strip extension
    no_ext = os.path.splitext(rel_path)[0].replace("\\", "/")
    # replace [param] with {param}, [...catch] with {catch}+
    parts = []
    for seg in no_ext.split("/"):
        seg = re.sub(r"\[\.\.\.(\w+)\]", r"{\1}+", seg)
        seg = re.sub(r"\[(\w+)\]", r"{\1}", seg)
        parts.append(seg)
    return "/".join(parts)


# ---------------------------------------------------------------------------
# python import helpers (Django)
# ---------------------------------------------------------------------------
def _parse_python_imports(filepath):
    """Extract module names from 'import X' and 'from X import ...' statements."""
    modules = set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = re.sub(r"#.*$", "", line).strip()
                if not line:
                    continue
                # from X import ...
                m = re.match(r"from\s+([\w.]+)\s+import", line)
                if m:
                    modules.add(m.group(1))
                    continue
                # import X, Y, Z
                m = re.match(r"import\s+(.+)", line)
                if m:
                    for name in m.group(1).split(","):
                        name = name.strip()
                        if name:
                            modules.add(name)
    except Exception:
        pass
    return modules


def _resolve_python_module(modname, project_root):
    """Resolve a dotted Python module name to a concrete file/directory path."""
    rel = modname.replace(".", os.sep)
    candidates = [
        os.path.join(project_root, rel + ".py"),
        os.path.join(project_root, rel),
    ]
    # also try partial resolution (e.g. 'a.b.c' → project_root/a/b.py)
    parts = modname.split(".")
    for i in range(len(parts), 0, -1):
        partial = os.path.join(project_root, *parts[:i])
        if os.path.isfile(partial + ".py"):
            candidates.append(partial + ".py")
        if os.path.isdir(partial):
            candidates.append(partial)
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


# ---------------------------------------------------------------------------
# dispatcher
# ---------------------------------------------------------------------------
def _handle_flask(api):
    """
    Flask: find all Python files imported (directly or transitively) from
    the config file. This handles Flask's diverse routing styles
    (@app.route, Blueprint, Flask-RESTful, etc.) by casting a wide net.
    """
    config_file = api.get("config_file")
    if not config_file:
        raise ValueError("Flask requires 'config_file' pointing to __init__.py or app factory")

    project_root = os.path.dirname(os.path.abspath(config_file))
    # collect all .py files in the project
    all_py = {}
    for dirpath, _dirnames, filenames in os.walk(project_root):
        for fname in filenames:
            if fname.endswith(".py"):
                fpath = os.path.join(dirpath, fname)
                # index by both basename (without ext) and full module path
                basename = os.path.splitext(fname)[0]
                all_py.setdefault(basename, []).append(fpath)
                # also index by path-from-root for dotted-module matching
                rel = os.path.relpath(fpath, project_root)
                modpath = rel.replace(os.sep, ".").rsplit(".", 1)[0]
                all_py.setdefault(modpath, []).append(fpath)

    # recursively find imports from the config file (BFS with depth limit)
    MAX_FLASK_IMPORT_DEPTH = 2
    processed = set()
    to_process = [(config_file, 0)]  # (file_path, depth)
    matched = []

    while to_process:
        current, depth = to_process.pop(0)
        if current in processed:
            continue
        processed.add(current)
        if depth >= MAX_FLASK_IMPORT_DEPTH:
            continue
        modnames = _parse_python_imports(current)
        for modname in modnames:
            # try exact module path match first
            key = modname
            if key in all_py:
                for p in all_py[key]:
                    if p not in processed:
                        to_process.append((p, depth + 1))
                        matched.append({
                            "file_path": p,
                            "matched_regex": None,
                            "matched_line": f"imported as '{modname}' from {os.path.basename(current)}",
                        })
            # try last-segment match
            last_seg = modname.split(".")[-1]
            if last_seg in all_py and last_seg not in (key,):
                for p in all_py[last_seg]:
                    if p not in processed:
                        to_process.append((p, depth + 1))
                        matched.append({
                            "file_path": p,
                            "matched_regex": None,
                            "matched_line": f"imported as '{modname}' from {os.path.basename(current)}",
                        })
    return matched


_HANDLERS = {
    "django": _handle_django,
    "flask": _handle_flask,
    "tornado": _handle_tornado,
    "webpy": _handle_webpy,
    "nextjs": _handle_nextjs,
}


def main(api):
    """
    Identify endpoint entry files for an API.

    Args:
        api: dict with keys name, path, framework, and optionally
             config_file, keyword, urls.

    Returns:
        dict with keys task_id, api_name, framework, scan_type, files, file_count.
    """
    fw = FRAMEWORKS[api["framework"]]
    scan_type = fw["scan_type"]
    start = time.time()

    if scan_type == "special":
        handler = _HANDLERS.get(api["framework"])
        if handler is None:
            raise NotImplementedError(
                f"No step1 handler for framework '{api['framework']}'"
            )
        try:
            files = handler(api)
        except Exception as e:
            print(f"  [WARN] {api['framework']} handler failed: {e}")
            files = []
    else:
        files = _scan_by_regex(api)

    result = _build_result(api, files)
    result["duration_ms"] = round((time.time() - start) * 1000)
    return result
