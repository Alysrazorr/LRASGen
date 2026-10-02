
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
        "--api-path", type=str, required=True,
        help="Absolute path to the project root of one subject API."
    )
    parser.add_argument(
        "--framework", type=str, required=True,
        choices=list(FRAMEWORKS.keys()),
        help="Framework used by the API."
    )
    parser.add_argument(
        "--config-file", type=str, default=None,
        help="Absolute path to the framework-specific configuration file. "
             "Required by Django (urls.py) and Flask (__init__.py)."
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
        "--url-context", type=str, default=None,
        help="Routes that live outside the handlers, for frameworks that declare "
             "them separately. The text is injected into the step-3 prompt as is."
    )
    parser.add_argument(
        "--exclude-deps", type=str, default=None,
        help="Comma-separated directories, relative to --api-path, whose files are "
             "left out of the dependency set that reaches the prompts."
    )
    parser.add_argument(
        "--exclude-dirs", type=str, default=None,
        help="Comma-separated directories to skip when scanning for endpoint "
             "entry files, given relative to --api-path."
    )
    parser.add_argument(
        "--output-dir", type=str, required=True,
        help="Absolute path of the directory this API's output is written to."
    )
    return parser.parse_args(argv)


def resolve_path(raw):
    return str(Path(raw).resolve())


def make_task_id(api):
    name = api["name"].lower()
    name = name.replace(" (*)", "").replace("(*)", "")
    name = name.replace(" ", "-")
    for ch in r'<>:"/\|?*':
        name = name.replace(ch, "")
    return name


def save_json(data, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_step_output(task_dir, step_name, data):
    filepath = os.path.join(task_dir, f"{step_name}.json")
    save_json(data, filepath)
    print(f"  → {filepath}")


def run_single(api, args):
    task_id = make_task_id(api)
    task_dir = resolve_path(args.output_dir)
    run_started = time.time()
    logger.info(f"Processing {api['name']} ({api['framework']})")

    llm.reset_usage()
    step1_result = step1_main(api)
    step1_result["task_id"] = task_id
    step1_result["tokens"] = llm.get_usage()
    write_step_output(task_dir, "step1_entry_files", step1_result)

    if not step1_result.get("files"):
        logger.warn("No entry files found — skipping.")
        return None

    step2_result = step2_main(api, step1_result["files"])
    step2_result["task_id"] = task_id
    step2_result["tokens"] = llm.get_usage()
    write_step_output(task_dir, "step2_code_files", step2_result)

    if not step2_result.get("entry_to_deps"):
        logger.warn("No code files extracted — skipping.")
        return None

    llm.reset_usage()
    step3_result = step3_main(api, step2_result)
    step3_result["task_id"] = task_id
    step3_result["tokens"] = llm.get_usage()
    write_step_output(task_dir, "step3_endpoints", step3_result)

    llm.reset_usage()
    t0 = time.time()
    step4_tasks = [{"api": api, "step2_result": step2_result, "step3_result": step3_result,
                     "task_id": task_id, "task_dir": task_dir}]
    results_by_task, _, _ = step4_parallel(step4_tasks)
    entry_results = results_by_task.get(task_id, [])
    step4_ms = round((time.time() - t0) * 1000)
    step4_result = {
        "task_id": task_id, "api_name": api["name"], "framework": api["framework"],
        "endpoints": entry_results,
        "duration_ms": step4_ms,
        "tokens": llm.get_usage(),
    }
    write_step_output(task_dir, "step4_details", step4_result)

    llm.reset_usage()
    t0 = time.time()
    step5_results, tc = step5_parallel(
        {task_id: entry_results},
        {task_id: step2_result},
        {task_id: api})
    step5_ms = round((time.time() - t0) * 1000)
    step4_result["endpoints"] = step5_results.get(task_id, entry_results)
    step4_result["duration_ms"] = step5_ms
    step4_result["tokens"] = llm.get_usage()
    step4_result["timings"] = {
        "step1_ms": step1_result.get("duration_ms", 0),
        "step2_ms": step2_result.get("duration_ms", 0),
        "step3_ms": step3_result.get("duration_ms", 0),
        "step4_ms": step4_ms,
        "step5_ms": step5_ms,
        "total_ms": round((time.time() - run_started) * 1000),
    }
    write_step_output(task_dir, "step5_constraints", step4_result)

    oas_path = step6_main(api, step4_result, output_dir=task_dir)

    neps = len(step3_result["endpoints"])
    nparams = sum(len(r["parameters"]) for r in step4_result["endpoints"])
    nresps = sum(len(r["responses"]) for r in step4_result["endpoints"])
    logger.info(f"Done: {neps} eps, {nparams} params, {tc} constraints, {nresps} resps, OAS={oas_path}")
    return task_dir


def main(argv=None):
    args = parse_args(argv)

    api_full_path = resolve_path(args.api_path)
    logger.info(f"API path: {api_full_path}")

    api = {
        "name": Path(api_full_path).name,
        "path": api_full_path,
        "framework": args.framework,
    }
    if args.config_file:
        api["config_file"] = resolve_path(args.config_file)
    if args.keyword:
        api["keyword"] = args.keyword
    if args.urls:
        api["urls"] = [u.strip() for u in args.urls.split(",")]
    if args.url_context:
        api["url_context"] = args.url_context
    if args.exclude_deps:
        api["exclude_deps"] = [d.strip() for d in args.exclude_deps.split(",")
                               if d.strip()]
    if args.exclude_dirs:
        api["exclude_dirs"] = [d.strip().replace("\\", "/").strip("/")
                               for d in args.exclude_dirs.split(",") if d.strip()]

    result = run_single(api, args)
    ok = 1 if result else 0
    logger.info(f"Done. {ok}/1 succeeded.")


if __name__ == "__main__":
    main()
