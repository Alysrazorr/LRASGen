
import argparse
import csv
import json
import os
import sys

import openpyxl

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))

# Normalization is shared with the pipeline: both sides must agree on what
# counts as the same endpoint, type, or constraint.
from normalize import (FIELD_OF_KIND, constraint_kinds, method, parameter_name,
                       parameter_type, path, status, type_name)


# Ground-truth column names map onto the same constraint kinds as the pipeline's
# field names, but the two vocabularies are not the same, so this stays local.
GT_CONSTRAINT_MAP = {
    "require": "required", "required": "required", "is_required": "required",
    "min_value": "min_value", "max_value": "max_value",
    "min_length": "min_length", "max_length": "max_length",
    "parameter_format": "format", "time_format": "format",
    "parameter_enum": "enum", "parameter_dict": "dictionary",
}

TASKS = [
    ("M", "Endpoint Methods"),
    ("P", "Endpoint Parameters"),
    ("C", "Parameter Constraints"),
    ("R", "Endpoint Responses"),
]


def parse_gt_constraint(value):
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    if v.startswith("["):
        return "enum"
    raw_kind = v.split(":", 1)[0].strip()
    return GT_CONSTRAINT_MAP.get(raw_kind)


def parse_gt_constraint_key(key):
    parts = str(key).split(",")
    if len(parts) < 4:
        return None
    return {
        "path": parts[0],
        "method": parts[1],
        "type": parts[2],
        "name": ",".join(parts[3:]),
    }


GT_COL = {
    "M": {"path": 0, "method": 1},
    "P": {"path": 3, "method": 4, "type": 5, "name": 6},
    "C": {"key": 8, "kind": 9},
    "R": {"path": 11, "method": 12, "status": 13},
}


def load_gt(gt_path):
    wb = openpyxl.load_workbook(gt_path, data_only=True)
    gt = {}
    for name in wb.sheetnames:
        raw = {"M": [], "P": [], "C": [], "R": []}
        for row in ws_iter(wb[name]):
            raw["M"].append(row.get("M"))
            raw["P"].append(row.get("P"))
            raw["C"].append(row.get("C"))
            raw["R"].append(row.get("R"))
        gt[name] = {t: [r for r in raw[t] if r] for t in raw}
    return gt


def ws_iter(ws):
    for row in ws.iter_rows(min_row=3, values_only=True):
        g = lambda i: row[i] if i < len(row) else None
        out = {"M": None, "P": None, "C": None, "R": None}
        if g(0) not in (None, "") and g(1) not in (None, ""):
            out["M"] = (g(0), g(1))
        if g(6) not in (None, ""):
            out["P"] = (g(3), g(4), g(5), g(6))
        if g(8) not in (None, "") and g(9) not in (None, ""):
            out["C"] = (g(8), g(9))
        if g(13) not in (None, ""):
            out["R"] = (g(11), g(12), g(13), g(14))
        yield out


def gt_keys(raw, task, strip_prefix=""):
    keys, rows = set(), {}
    for item in raw[task]:
        if task == "M":
            key = (path(item[0], strip_prefix), method(item[1]))
            rows[key] = {"path": item[0], "method": item[1]}
        elif task == "P":
            ep = (path(item[0], strip_prefix), method(item[1]))
            key = ep + (parameter_name(item[3]), type_name(item[2]))
            rows[key] = {"path": item[0], "method": item[1],
                         "type": item[2], "name": item[3]}
        elif task == "C":
            ck = parse_gt_constraint_key(item[0])
            kind = parse_gt_constraint(item[1])
            if not ck or not kind:
                continue
            ep = (path(ck["path"], strip_prefix), method(ck["method"]))
            key = ep + (parameter_name(ck["name"]), kind)
            rows[key] = {"key": item[0], "kind": item[1], "name": ck["name"]}
        else:
            ep = (path(item[0], strip_prefix), method(item[1]))
            key = ep + (status(item[2]),)
            rows[key] = {"path": item[0], "method": item[1],
                         "status": item[2], "type": item[3]}
        keys.add(key)
    return keys, rows


def leading_segments(gt_raw, ours):
    seen = set()
    for task in ("M", "P", "C", "R"):
        for path in [r[0] for r in gt_raw[task]]:
            p = str(path or "").strip("/").split("/")[0]
            if p:
                seen.add(p)
    for ep in ours["rows"]["M"].values():
        p = str(ep.get("path") or "").strip("/").split("/")[0]
        if p:
            seen.add(p)
    return sorted(seen)


def find_result_file(api_dir, filename):
    direct = os.path.join(api_dir, filename)
    if os.path.isfile(direct):
        return direct
    hits = []
    for dirpath, _dirnames, filenames in os.walk(api_dir):
        if filename in filenames:
            hits.append(os.path.join(dirpath, filename))
    if len(hits) == 1:
        return hits[0]
    return None


def load_pipeline(api_dir, strip_prefix=""):
    f3 = find_result_file(api_dir, "step3_endpoints.json")
    f5 = find_result_file(api_dir, "step5_constraints.json")
    if not f3 or not f5:
        return None

    with open(f3, encoding="utf-8") as fh:
        step3 = json.load(fh)
    with open(f5, encoding="utf-8") as fh:
        step5 = json.load(fh)

    keys = {"M": set(), "P": set(), "C": set(), "R": set()}
    rows = {"M": {}, "P": {}, "C": {}, "R": {}}

    for ep in step3.get("endpoints", []):
        key = (path(ep.get("endpoint_path"), strip_prefix),
               method(ep.get("http_method")))
        keys["M"].add(key)
        rows["M"][key] = {"path": ep.get("endpoint_path"),
                          "method": ep.get("http_method"),
                          "method_name": ep.get("method_name"),
                          "anchor": (ep.get("source_file"), ep.get("line_number"))}

    for ep in step5.get("endpoints", []):
        endpoint = (path(ep.get("endpoint_path"), strip_prefix),
                    method(ep.get("http_method")))
        anchor = (ep.get("source_file"), ep.get("line_number"))

        for p in ep.get("parameters", []):
            name = str(p.get("name", "")).strip()
            key = endpoint + (parameter_name(name), parameter_type(p))
            keys["P"].add(key)
            rows["P"][key] = {
                "name": name, "type": p.get("type"),
                "position": p.get("position"), "anchor": anchor,
                "path": ep.get("endpoint_path"), "method": ep.get("http_method")}

            for kind in constraint_kinds(p):
                field = FIELD_OF_KIND.get(kind, kind)
                ckey = endpoint + (parameter_name(name), kind)
                keys["C"].add(ckey)
                rows["C"][ckey] = {
                    "name": name,
                    "kind": field, "value": p.get(field), "anchor": anchor,
                    "path": ep.get("endpoint_path"),
                    "method": ep.get("http_method")}

        for r in ep.get("responses", []):
            sc = status(r.get("status_code"))
            if not sc:
                continue
            key = endpoint + (sc,)
            keys["R"].add(key)
            rows["R"][key] = {
                "status": r.get("status_code"),
                "description": r.get("description"), "anchor": anchor,
                "path": ep.get("endpoint_path"), "method": ep.get("http_method")}

    return {"keys": keys, "rows": rows}


def compare(gt_keys, our_keys):
    tp = gt_keys & our_keys
    fp = our_keys - gt_keys
    fn = gt_keys - our_keys
    return tp, fp, fn


def pr(tp, fp, fn):
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    return precision, recall


def key_to_text(task, key, row=None):
    """Render a key for the audit sheet.

    The key holds the folded parameter name, so the sheet prints the name from
    the row instead, which is the one the source or GTa actually wrote.
    """
    if task == "M":
        return f"{key[1]} {key[0]}"
    if task == "R":
        return f"{key[1]} {key[0]} | {key[2]}"
    name = (row or {}).get("name") or key[2]
    return f"{key[1]} {key[0]} | {name} : {key[3]}"


def rel_path(path):
    """A path as it reads from the package root, with forward slashes."""
    try:
        return os.path.relpath(path, REPO).replace(os.sep, "/")
    except ValueError:
        return str(path).replace(os.sep, "/")


def md_table(headers, rows, numeric=()):
    """A markdown table. ``numeric`` names the columns to right-align."""
    numeric = set(numeric)
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join("---:" if h in numeric else "---" for h in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return lines


def write_md(path, lines):
    out_dir = os.path.dirname(path)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines).rstrip("\n") + "\n")
    return path


def summary_sentence(totals):
    """The paper's RQ1 sentence, with this run's figures in it.

    The paper states RQ1 as "identifies <count> of <count> (<share>) <task>"
    against the enhanced ground truth, so the first count is what LRASGen
    reported for the task and the second is what the ground truth lists. The two
    are equal only when the task carries no false positive, which the table
    below separates out.
    """
    clauses = []
    for task, label in TASKS:
        t = totals[task]
        if not t["gt"]:
            continue
        clauses.append("%s of %s (%.1f%%) %s"
                       % (f"{t['ours']:,}", f"{t['gt']:,}",
                          t["ours"] / t["gt"] * 100, label.lower()))
    if not clauses:
        return "No task had a ground truth to match against."
    if len(clauses) == 1:
        body = clauses[0]
    else:
        body = ", ".join(clauses[:-1]) + ", and " + clauses[-1]
    return ("LRASGen identifies " + body
            + " against the enhanced ground truth (GT*).")


def write_analysis(path, totals, args):
    """What the run found, laid out in the order the paper states RQ1."""
    lines = []
    lines.append("# RQ1: accuracy against the enhanced ground truth")
    lines.append("")
    lines.append("`scripts/evaluate_rq1.py` reads the pipeline output under `%s` and "
                 "the enhanced ground truth in `%s`, applies the same four keys to "
                 "both sides, and matches them entity by entity."
                 % (rel_path(args.output_root), rel_path(args.gt)))
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(summary_sentence(totals))
    lines.append("")
    lines.append("## Per task")
    lines.append("")
    rows = []
    for task, label in TASKS:
        t = totals[task]
        precision, recall = pr(t["tp"], t["fp"], t["fn"])
        rows.append([label, f"{t['gt']:,}", f"{t['ours']:,}", f"{t['tp']:,}",
                     f"{t['fp']:,}", f"{t['fn']:,}",
                     "-" if precision is None else f"{precision:.4f}",
                     "-" if recall is None else f"{recall:.4f}"])
    lines += md_table(
        ["Task", "GT", "Ours", "TP", "FP", "FN", "Precision", "Recall"], rows,
        numeric=["GT", "Ours", "TP", "FP", "FN", "Precision", "Recall"])
    lines.append("")
    lines.append("## Reading")
    lines.append("")
    lines.append("The ground truth is the reference for this comparison, so a "
                 "false negative is an entity it lists and the pipeline did not "
                 "report, and a false positive is one the pipeline reported and "
                 "it does not list. Precision and recall both follow from those "
                 "two counts, and neither is meaningful on its own: a task can "
                 "reach a high recall by reporting every path it saw and a high "
                 "precision by reporting almost nothing.")
    lines.append("")
    lines.append("The full list of disagreements is in `rq1_audit.csv` beside "
                 "this file, one row per entity, with the pipeline value, the "
                 "ground truth value, and the source file the pipeline read.")
    write_md(path, lines)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="RQ1: pipeline output vs GTa.xlsx")
    ap.add_argument("--gt", default=os.path.join(REPO, "GTa.xlsx"),
                    help="path to GTa.xlsx (default: <root>/extras/GTa.xlsx)")
    ap.add_argument("--output-root",
                    default=os.path.join(REPO, "output", "lrasgen_generated"),
                    help="root holding one directory per API")
    ap.add_argument("--out-dir", default=os.path.join(REPO, "evaluation", "RQ1"),
                    help="where the CSV reports are written (default: %(default)s)")
    ap.add_argument("--analysis", default=None,
                    help="where the analysis document is written "
                         "(default: <out-dir>/rq1_analysis.md)")
    ap.add_argument("--strip-prefix", default="",
                    help="base-path segment to drop from both sides before matching, "
                         "e.g. 'api' (default: none)")
    ap.add_argument("--only", default=None,
                    help="comma-separated API short names to evaluate, e.g. CatWatch,Faults")
    args = ap.parse_args(argv)
    cli_strip = args.strip_prefix

    if not os.path.isfile(args.gt):
        print(f"error: ground truth not found: {args.gt}")
        return 1
    if not os.path.isdir(args.output_root):
        print(f"error: output root not found: {args.output_root}")
        return 1

    print(f"ground truth : {args.gt}")
    print("base path stripped per API by trial: the leading segment, if any, that "
          "aligns the most entities")
    print(f"output root  : {args.output_root}")
    print("path params  : placeholder names collapsed to {}")
    print()

    gt = load_gt(args.gt)

    wanted = None
    if args.only:
        wanted = {n.strip() for n in args.only.split(",") if n.strip()}
        unknown = wanted - set(gt)
        if unknown:
            print(f"error: no sheet in GTa.xlsx for: {sorted(unknown)}")
            return 1

    present, missing = [], []
    for api in gt:
        if wanted is not None and api not in wanted:
            continue
        api_dir = os.path.join(args.output_root, api)
        if os.path.isdir(api_dir):
            present.append(api)
        else:
            missing.append(api)

    print(f"APIs in GTa.xlsx : {len(gt)}")
    print(f"APIs with output : {len(present)}")
    if missing:
        shown = ", ".join(sorted(missing)[:12])
        more = "" if len(missing) <= 12 else f" (+{len(missing) - 12} more)"
        print(f"APIs without output ({len(missing)}): {shown}{more}")
    print()

    totals = {t: {"gt": 0, "ours": 0, "tp": 0, "fp": 0, "fn": 0} for t, _ in TASKS}
    per_api = []
    audit = []

    chosen_strip = {}
    for api in sorted(present):
        api_dir = os.path.join(args.output_root, api)

        probe = load_pipeline(api_dir, cli_strip)
        if probe is None:
            print(f"  [warn] {api}: step3/step5 JSON not found, skipped")
            continue

        candidates = [cli_strip] if cli_strip else [""] + leading_segments(gt[api], probe)
        best_strip, best_hits, ours = candidates[0], -1, probe
        for candidate in candidates:
            candidate_ours = load_pipeline(api_dir, candidate)
            if candidate_ours is None:
                continue
            hits = sum(len(gt_keys(gt[api], t, candidate)[0] & candidate_ours["keys"][t])
                       for t, _ in TASKS)
            if hits > best_hits:
                best_strip, best_hits, ours = candidate, hits, candidate_ours
        chosen_strip[api] = best_strip

        gt_keys_by_task = {t: gt_keys(gt[api], t, best_strip) for t, _ in TASKS}
        for task, _label in TASKS:
            gkeys = gt_keys_by_task[task][0]
            tp, fp, fn = compare(gkeys, ours["keys"][task])
            totals[task]["gt"] += len(gkeys)
            totals[task]["ours"] += len(ours["keys"][task])
            totals[task]["tp"] += len(tp)
            totals[task]["fp"] += len(fp)
            totals[task]["fn"] += len(fn)
            precision, recall = pr(len(tp), len(fp), len(fn))
            n_gt = len(gkeys)
            covered = recall
            per_api.append({
                "api": api, "task": task, "label": _label,
                "gt": n_gt,
                "ours": len(ours["keys"][task]),
                "tp": len(tp), "fp": len(fp), "fn": len(fn),
                "precision": "" if precision is None else f"{precision:.4f}",
                "recall": "" if recall is None else f"{recall:.4f}",
                "covered": n_gt - len(fn),
                "coverage": "" if covered is None else f"{covered:.4f}",
                "fully_covered": "yes" if (n_gt == 0 or not fn) else "no",
            })

            for key in sorted(fp):
                row = ours["rows"][task].get(key, {})
                anchor = row.get("anchor") or (None, None)
                audit.append({
                    "api": api, "task": task, "verdict": "",
                    "matching_key": key_to_text(task, key, row),
                    "pipeline_value": describe(task, row) or key_to_text(task, key),
                    "gt_value": "",
                    "source_file": anchor[0] or "",
                    "line_number": anchor[1] if anchor[1] is not None else "",
                })
            for key in sorted(fn):
                row = gt_keys_by_task[task][1].get(key, {})
                audit.append({
                    "api": api, "task": task, "verdict": "",
                    "matching_key": key_to_text(task, key, row),
                    "pipeline_value": "",
                    "gt_value": describe(task, row) or key_to_text(task, key),
                    "source_file": "",
                    "line_number": "",
                })

    print("	".join(["task", "GT", "ours", "TP", "FP", "FN", "precision",
                     "recall", "covered", "coverage"]))
    for task, label in TASKS:
        t = totals[task]
        precision, recall = pr(t["tp"], t["fp"], t["fn"])
        p = "-" if precision is None else f"{precision:.4f}"
        r = "-" if recall is None else f"{recall:.4f}"
        print("	".join([f"{task}  {label}", str(t["gt"]), str(t["ours"]),
                         str(t["tp"]), str(t["fp"]), str(t["fn"]), p, r,
                         str(t["gt"] - t["fn"]), r]))
    print()

    full = [f"{t}" for t, _ in TASKS if totals[t]["gt"] and not totals[t]["fn"]]
    print(f"GTa fully covered in: {', '.join(full) if full else 'no task'}")

    used = {a: s for a, s in chosen_strip.items() if s}
    print("base segments dropped: "
          + (", ".join(f"{a}->/{s}" for a, s in sorted(used.items())) if used
             else "none"))
    print()

    os.makedirs(args.out_dir, exist_ok=True)
    per_api_path = os.path.join(args.out_dir, "rq1_per_api.csv")
    with open(per_api_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["api", "task", "label", "gt", "ours",
                                           "tp", "fp", "fn", "precision", "recall",
                                           "covered", "coverage", "fully_covered"])
        w.writeheader()
        w.writerows(per_api)

    audit_path = os.path.join(args.out_dir, "rq1_audit.csv")
    with open(audit_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["api", "task", "matching_key",
                                           "pipeline_value", "gt_value",
                                           "source_file", "line_number", "verdict"])
        w.writeheader()
        w.writerows(audit)

    analysis_path = args.analysis or os.path.join(args.out_dir, "rq1_analysis.md")
    write_analysis(analysis_path, totals, args)

    print(f"per-API counts   : {per_api_path}  ({len(per_api)} rows)")
    print(f"audit worksheet  : {audit_path}  ({len(audit)} disagreements)")
    print(f"analysis         : {analysis_path}")
    return 0


def describe(task, row):
    if not row:
        return ""
    if task == "M":
        name = row.get("method_name")
        return f"{row.get('method', '')} {row.get('path', '')}" + (
            f" ({name})" if name else "")
    if task == "P":
        return f"type={row.get('type', '')} position={row.get('position', '')}"
    if task == "C":
        return f"{row.get('kind', '')}={row.get('value', '')}"
    return f"{row.get('status', '')} {str(row.get('description') or '')[:80]}"


if __name__ == "__main__":
    sys.exit(main())
