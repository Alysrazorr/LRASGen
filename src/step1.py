
import os
import re
import time
from pathlib import Path

from config import FLASK_IMPORT_MAX_DEPTH
from frameworks import FRAMEWORKS


def _build_result(api, files):
    return {
        "task_id": None,
        "api_name": api["name"],
        "framework": api["framework"],
        "scan_type": FRAMEWORKS[api["framework"]]["scan_type"],
        "files": files,
    }


_DEFAULT_EXCLUDE_BASENAMES = {
    'target',
    'build',
    '__pycache__',
    'node_modules',
    'dist',
    'out',
    'bin',
    '.git',
    '.gradle',
    '.idea',
    '.settings',
}


def _scan_by_regex(api):
    fw = FRAMEWORKS[api["framework"]]
    suffix = fw["suffix"]
    patterns = [re.compile(r) for r in fw["regex"]]
    root = api["path"]
    api_exclude_dirs = api.get("exclude_dirs") or []
    matched = []

    def _prune_dirnames(dirpath, dirnames):
        keep = []
        for d in dirnames:
            if d in _DEFAULT_EXCLUDE_BASENAMES:
                continue
            if d == 'test' and (os.path.basename(dirpath) == 'src'
                                or dirpath.replace('\\', '/').endswith('/src')):
                continue
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

    if not matched:
        for dirpath, _dirnames, filenames in os.walk(root):
            if "inflector.yaml" in filenames or "inflector.yml" in filenames:
                inflector_path = os.path.join(dirpath,
                    "inflector.yaml" if "inflector.yaml" in filenames else "inflector.yml")
                matched = _handle_inflector(inflector_path, root)
                break

    return matched


def _handle_inflector(inflector_path, project_root):
    import yaml
    matched = []
    try:
        with open(inflector_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        pkg = config.get("controllerPackage")
        if not pkg:
            return matched
        pkg_path = pkg.replace(".", "/")
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


def _handle_django(api):
    config_file = api.get("config_file")
    if not config_file:
        raise ValueError("Django requires 'config_file' pointing to urls.py")

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
    urls = api.get("urls")
    if not urls:
        raise ValueError("Web.py requires 'urls' (list of URL-pattern / controller pairs)")
    root = api["path"]
    matched = []

    for i in range(1, len(urls), 2):
        controller = urls[i]
        module_name = ".".join(controller.split(".")[:-1])
        file_name = controller.split(".")[-2] + ".py"
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
    seen = set()
    unique = []
    for m in matched:
        if m["file_path"] not in seen:
            seen.add(m["file_path"])
            unique.append(m)
    return unique


def _handle_nextjs(api):
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
                    rel = os.path.relpath(fpath, api_dir)
                    route = "/api/" + _nextjs_route_from_file(rel)
                    matched.append({
                        "file_path": fpath,
                        "matched_regex": None,
                        "matched_line": f"Next.js file route → {route}",
                    })
    return matched


def _nextjs_route_from_file(rel_path):
    no_ext = os.path.splitext(rel_path)[0].replace("\\", "/")
    parts = []
    for seg in no_ext.split("/"):
        seg = re.sub(r"\[\.\.\.(\w+)\]", r"{\1}+", seg)
        seg = re.sub(r"\[(\w+)\]", r"{\1}", seg)
        parts.append(seg)
    return "/".join(parts)


def _parse_python_imports(filepath):
    modules = set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = re.sub(r"#.*$", "", line).strip()
                if not line:
                    continue
                m = re.match(r"from\s+([\w.]+)\s+import", line)
                if m:
                    modules.add(m.group(1))
                    continue
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
    rel = modname.replace(".", os.sep)
    candidates = [
        os.path.join(project_root, rel + ".py"),
        os.path.join(project_root, rel),
    ]
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


# How a Flask app can announce a path. ".route(" covers @app.route, @bp.route
# and every other decorator shape; the rest are the registration calls a
# flask-restful app makes instead.
_ROUTE_DECL_RE = re.compile(
    r"\.route\s*\(|\.add_url_rule\s*\(|\.add_resource\s*\(|register_endpt\s*\("
)


def _declares_route(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return _ROUTE_DECL_RE.search(fh.read()) is not None
    except OSError:
        return False


def _handle_flask(api):
    config_file = api.get("config_file")
    if not config_file:
        raise ValueError("Flask requires 'config_file' pointing to __init__.py or app factory")

    project_root = os.path.dirname(os.path.abspath(config_file))
    all_py = {}
    for dirpath, _dirnames, filenames in os.walk(project_root):
        for fname in filenames:
            if fname.endswith(".py"):
                fpath = os.path.join(dirpath, fname)
                basename = os.path.splitext(fname)[0]
                all_py.setdefault(basename, []).append(fpath)
                rel = os.path.relpath(fpath, project_root)
                modpath = rel.replace(os.sep, ".").rsplit(".", 1)[0]
                all_py.setdefault(modpath, []).append(fpath)

    processed = set()
    to_process = [(config_file, 0)]
    # The file the walk starts from is the route table. A Flask app that uses
    # flask-restful, as Gramps does, registers every path in this one module and
    # its resource classes declare none, so listing only the files reached
    # through it left the registrations out of the prompt and the model was
    # reduced to guessing paths from class names.
    matched = [{
        "file_path": config_file,
        "matched_regex": None,
        "matched_line": "route registrations",
    }]

    while to_process:
        current, depth = to_process.pop(0)
        if current in processed:
            continue
        processed.add(current)
        if depth >= FLASK_IMPORT_MAX_DEPTH:
            continue
        modnames = _parse_python_imports(current)
        for modname in modnames:
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

    # Only a file that declares a path is an entry, because every entry costs a
    # call that asks for the endpoints defined in it. Being reachable from the
    # app factory is not the same as defining one: Gramps registers all 99 of its
    # paths in the file the walk starts from, so its 60 resource modules were
    # paying for a call each and answering with nothing, or with a path guessed
    # from the class name. The walk itself must still follow every import, since
    # a module without a route of its own can be the one that imports the module
    # that has them. Dropping a file here only drops its chance to be an entry:
    # it stays in the task as a dependency, so the classes it defines still reach
    # the steps that read parameters and constraints out of them.
    root = os.path.abspath(config_file)
    return [m for m in matched
            if os.path.abspath(m["file_path"]) == root
            or _declares_route(m["file_path"])]


_HANDLERS = {
    "django": _handle_django,
    "flask": _handle_flask,
    "tornado": _handle_tornado,
    "webpy": _handle_webpy,
    "nextjs": _handle_nextjs,
}


def main(api):
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
