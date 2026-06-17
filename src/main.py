"""
LRASGen — LLM-based RESTful API Specification Generation

Entry point. Single API mode:

  python main.py --root-path ./datasets --api-path catwatch --framework spring-boot
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import logger
import llm
from frameworks import FRAMEWORKS
from step1 import main as step1_main
from step2 import main as step2_main
from step3 import main as step3_main
from step4 import run_parallel as step4_parallel
from step5 import run_parallel as step5_parallel
from step6 import main as step6_main


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="LRASGen — LLM-based RESTful API Specification Generation"
    )
    parser.add_argument(
        "--root-path", type=str, default=None,
        help="Root directory for API source datasets."
    )
    parser.add_argument(
        "--api-path", type=str, default=None,
        help="Path to the API source code root (relative to --root-path, or absolute)."
    )
    parser.add_argument(
        "--framework", type=str, default=None,
        choices=list(FRAMEWORKS.keys()),
        help="Framework used by the API. Auto-detected if not specified."
    )
    parser.add_argument(
        "--config-file", type=str, default=None,
        help="Framework-specific configuration file (relative to --root-path, or absolute)."
    )
    parser.add_argument(
        "--keyword", type=str, default=None,
        help="Framework-specific search keyword (e.g. Tornado handler list)."
    )
    parser.add_argument(
        "--urls", type=str, default=None,
        help="Web.py URL routing list, comma-separated (pattern,controller pairs)."
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Directory for intermediate output (default: src/output/)."
    )
    parser.add_argument(
        "--output-name", type=str, default=None,
        help="Override output subdirectory name (default: derived from --api-path)."
    )
    parser.add_argument(
        "--llm", type=str, default="deepseek",
        choices=["gpt", "deepseek", "gemini", "all"],
        help="LLM provider (default: deepseek)."
    )
    parser.add_argument(
        "--temperature", type=float, default=0.2,
        help="LLM temperature (default: 0.2)."
    )
    parser.add_argument(
        "--enable-validate", type=str, default="false",
        choices=["true", "false"],
        help="Enable OAS compliance check via openapi-schema-validator (default: false)."
    )
    parser.add_argument(
        "--enable-cross-validation", type=str, default="false",
        choices=["true", "false"],
        help="Enable cross-validation with 3 LLMs and voting (default: false)."
    )
    return parser.parse_args(argv)


def resolve_path(raw, root):
    p = Path(raw)
    if p.is_absolute():
        return str(p)
    return str(Path(root) / p)


def make_task_id(api):
    name = api["name"].lower()
    name = name.replace(" (*)", "").replace("(*)", "")
    name = name.replace(" ", "-")
    for ch in r'<>:"/\|?*':
        name = name.replace(ch, "")
    return name


def get_output_dir(args):
    if args.output_dir:
        return Path(args.output_dir)
    return _SCRIPT_DIR.parent / "output"


def save_json(data, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_step_output(task_dir, step_name, data):
    filepath = os.path.join(task_dir, f"{step_name}.json")
    save_json(data, filepath)
    print(f"  → {filepath}")


def run_single(api, args):
    """Process a single API through the full pipeline."""
    task_id = make_task_id(api)
    task_dir = os.path.join(get_output_dir(args), task_id)
    logger.info(f"Processing {api['name']} ({api['framework']})")

    # step1
    llm.reset_usage()
    step1_result = step1_main(api)
    step1_result["task_id"] = task_id
    step1_result["tokens"] = llm.get_usage()
    write_step_output(task_dir, "step1_entry_files", step1_result)

    if not step1_result.get("files"):
        logger.warn("No entry files found — skipping.")
        return None

    # step2
    step2_result = step2_main(api, step1_result["files"])
    step2_result["task_id"] = task_id
    step2_result["tokens"] = llm.get_usage()
    write_step_output(task_dir, "step2_code_files", step2_result)

    if not step2_result.get("entry_to_deps"):
        logger.warn("No code files extracted — skipping.")
        return None

    # step3
    llm.reset_usage()
    step3_result = step3_main(api, step2_result, provider=args.llm, temperature=args.temperature,
                              cross_validate=(args.enable_cross_validation == "true"))
    step3_result["task_id"] = task_id
    step3_result["tokens"] = llm.get_usage()
    write_step_output(task_dir, "step3_endpoints", step3_result)

    # step4: parameters + responses
    llm.reset_usage()
    t0 = time.time()
    step4_tasks = [{"api": api, "step2_result": step2_result, "step3_result": step3_result,
                     "task_id": task_id, "task_dir": task_dir}]
    results_by_task, tp, tr = step4_parallel(step4_tasks, provider=args.llm, temperature=args.temperature,
                                               cross_validate=(args.enable_cross_validation == "true"))
    entry_results = results_by_task.get(task_id, [])
    step4_result = {
        "task_id": task_id, "api_name": api["name"], "framework": api["framework"],
        "endpoints": entry_results,
        "duration_ms": round((time.time() - t0) * 1000),
        "tokens": llm.get_usage(),
    }
    write_step_output(task_dir, "step4_details", step4_result)

    # step5: parameter constraints
    llm.reset_usage()
    t0 = time.time()
    step5_results, tc = step5_parallel(
        {task_id: entry_results},
        {task_id: step2_result},
        {task_id: api},
        provider=args.llm, temperature=args.temperature,
        cross_validate=(args.enable_cross_validation == "true"))
    step4_result["endpoints"] = step5_results.get(task_id, entry_results)
    step4_result["duration_ms"] = round((time.time() - t0) * 1000)
    step4_result["tokens"] = llm.get_usage()
    write_step_output(task_dir, "step5_constraints", step4_result)

    # step6: OAS assembly
    oas_path = step6_main(api, step4_result, output_dir=task_dir,
                          enable_validate=(args.enable_validate == "true"))

    neps = len(step3_result["endpoints"])
    nparams = sum(len(r["parameters"]) for r in step4_result["endpoints"])
    nresps = sum(len(r["responses"]) for r in step4_result["endpoints"])
    logger.info(f"Done: {neps} eps, {nparams} params, {tc} constraints, {nresps} resps, OAS={oas_path}")
    return task_dir


def detect_framework(api_path):
    """Auto-detect framework from project files."""
    p = Path(api_path)
    # Walk up to find project root markers
    for parent in [p] + list(p.parents):
        # JVM
        if (parent / "pom.xml").exists():
            return "spring-boot"
        if (parent / "build.gradle").exists() or (parent / "build.gradle.kts").exists():
            return "spring-boot"
        if (parent / ".csproj").exists() or list(parent.glob("*.csproj")):
            return "aspnetcore"

        # Python
        if (parent / "setup.py").exists() or (parent / "setup.cfg").exists() or \
           (parent / "pyproject.toml").exists():
            # Try to determine specific framework from deps
            for req_file in ["requirements.txt", "Pipfile", "Pipfile.lock"]:
                req_path = parent / req_file
                if req_path.exists():
                    req_text = req_path.read_text(encoding="utf-8")
                    if "tornado" in req_text.lower():
                        return "tornado"
                    if "flask" in req_text.lower():
                        return "flask"
                    if "django" in req_text.lower():
                        return "django"
                    if "web.py" in req_text.lower():
                        return "webpy"
                    break
            return "flask"  # most Python projects

        if (parent / "requirements.txt").exists():
            req_text = (parent / "requirements.txt").read_text(encoding="utf-8")
            if "tornado" in req_text.lower():
                return "tornado"
            if "flask" in req_text.lower():
                return "flask"
            if "django" in req_text.lower():
                return "django"
            if "web.py" in req_text.lower():
                return "webpy"
            return "flask"

        if (parent / "manage.py").exists():
            return "django"

        # Node.js / TypeScript
        if (parent / "package.json").exists():
            pkg = json.load(open(parent / "package.json", encoding="utf-8"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "@nestjs/core" in deps or "@nestjs/common" in deps:
                return "nestjs"
            if "tornado" in deps:
                return "tornado"
            if "koa" in deps or "koa-router" in deps:
                return "koa"
            if "express" in deps:
                return "express"
            return "express"  # most likely for JS/TS projects

        # stop at dataset root
        if parent.name == "datasets" or parent == parent.parent:
            break

    # If no project files found at or above the api path, check one level
    # of subdirectories (e.g. monorepos like cyclotron-master/cyclotron-svc)
    if p.is_dir():
        for sub in p.iterdir():
            if sub.is_dir():
                result = detect_framework(str(sub))
                if result:
                    return result
    return None


def main(argv=None):
    args = parse_args(argv)

    if not args.api_path:
        print("Error: --api-path is required.")
        sys.exit(1)

    root_path = args.root_path if args.root_path else str(_SCRIPT_DIR)
    root_path = str(Path(root_path).resolve())
    if not os.path.isabs(root_path):
        root_path = str(Path(root_path).resolve())
    logger.info(f"Root path: {root_path}")

    api_full_path = resolve_path(args.api_path, root_path)
    if not os.path.isabs(api_full_path):
        api_full_path = str(Path(api_full_path).resolve())

    framework = args.framework or detect_framework(api_full_path)
    if not framework:
        print(f"Error: could not auto-detect framework for '{api_full_path}'. Please specify --framework.")
        sys.exit(1)

    api = {
        "name": args.output_name or Path(api_full_path).name,
        "path": api_full_path,
        "framework": framework,
    }
    if args.config_file:
        api["config_file"] = resolve_path(args.config_file, root_path)
    if args.keyword:
        api["keyword"] = args.keyword
    if args.urls:
        api["urls"] = [u.strip() for u in args.urls.split(",")]

    result = run_single(api, args)
    ok = 1 if result else 0
    logger.info(f"Done. {ok}/1 succeeded.")


if __name__ == "__main__":
    main()
