"""RQ2: the four identification tasks, counted for the pipeline and for the developer specs.

For every subject API the developer-provided specification is read out of
snapshot/developer_provided/ and the pipeline's own output is read out of
output/lrasgen_generated/, and the two are put through the same four entity keys
RQ1 uses. What comes out is one table: how many entities each side carries, per
task.

    task                     ours      dev
    Endpoint Methods         2515     2163
    ...

No true/false classification is involved and no cell is adjudicated by hand. The
developer-provided specifications are a comparison target, not a ground truth,
so there is no such thing as a false positive in them: a developer who omits an
entity has not made a mistake, they have documented less.

This script is a tool this report built, not a reconstruction of the authors'
own procedure. The paper says its ground truth and its comparison were produced
by authors analyzing the APIs by hand. Nothing here claims to re-run that.

    python scripts/evaluate_rq2.py
    python scripts/evaluate_rq2.py --only Actuator,CatWatch
    python scripts/evaluate_rq2.py --per-api evaluation/RQ2/rq2_per_api.csv
"""

import argparse
import csv
import io
import json
import os
import sys

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import evaluate_rq1 as E
from normalize import method, parameter_name, path, status, type_name

DEFAULT_SPECS = os.path.join(REPO, "specs", "developer_provided")
DEFAULT_ROOT = os.path.join(REPO, "output", "lrasgen_generated")
DEFAULT_GT = os.path.join(REPO, "GTa.xlsx")

TASKS = [("M", "Endpoint Methods"), ("P", "Endpoint Parameters"),
         ("C", "Parameter Constraints"), ("R", "Endpoint Responses")]

HTTP_METHODS = ("get", "post", "put", "delete", "patch", "head", "options", "trace")

# Where a constraint the developer wrote is spelled in a specification, and what
# the pipeline calls it. `pattern` is the spec's spelling of a format the
# pipeline reads off an annotation, so the two share one kind.
SPEC_CONSTRAINT_FIELDS = (
    ("minimum", "min_value"),
    ("maximum", "max_value"),
    ("minLength", "min_length"),
    ("maxLength", "max_length"),
    ("pattern", "format"),
    ("enum", "enum"),
)

# `format` is mostly a refinement of the type the developer already stated:
# int64 says how wide the integer is, not what values it accepts. The formats
# the pipeline records as a constraint are the ones that say how the value is
# written, and those are the ones counted here.
TYPE_REFINEMENT_FORMATS = {
    "int32", "int64", "float", "double", "byte", "binary", "decimal", "bigint",
}


def resolve(doc, node):
    """Follow a local $ref to the object it names, or return what was given."""
    seen = 0
    while isinstance(node, dict) and "$ref" in node and seen < 10:
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            return {}
        cur = doc
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return {}
        node = cur
        seen += 1
    return node if isinstance(node, dict) else {}


def schema_of(doc, prm):
    """The schema a parameter or a media type carries its value in."""
    sch = prm.get("schema")
    if isinstance(sch, dict):
        return resolve(doc, sch)
    if "content" in prm:
        for media in (prm.get("content") or {}).values():
            if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                return resolve(doc, media["schema"])
    # Swagger 2.0 writes the type on the parameter itself.
    return {k: prm[k] for k in
            ("type", "format", "items", "enum", "minimum", "maximum",
             "minLength", "maxLength", "pattern", "default") if k in prm}


def spec_type(doc, sch):
    """The kind of value a schema holds, in the vocabulary the keys use."""
    sch = resolve(doc, sch)
    if not sch:
        return ""
    if "type" in sch:
        return type_name(sch["type"])
    if "properties" in sch or "additionalProperties" in sch:
        return "object"
    if "items" in sch:
        return "array"
    if "allOf" in sch or "oneOf" in sch or "anyOf" in sch:
        return "object"
    return ""


def add_constraints(keys, doc, ep, name, sch, required):
    """Record the constraints a schema states, under the RQ1 kinds."""
    sch = resolve(doc, sch)
    folded = parameter_name(name)
    if required is True:
        keys["C"].add(ep + (folded, "required"))
    for field, kind in SPEC_CONSTRAINT_FIELDS:
        if sch.get(field) is not None:
            keys["C"].add(ep + (folded, kind))
    fmt = sch.get("format")
    if isinstance(fmt, str) and fmt and fmt not in TYPE_REFINEMENT_FORMATS:
        keys["C"].add(ep + (folded, "format"))


def body_properties(doc, op):
    """The parameters a request body declares, one level deep.

    The pipeline reports a body as the fields the request class declares, so the
    developer's body schema is opened the same way. A field whose own type is
    another object is left as that one field, again as the pipeline leaves it.
    """
    schema = None
    if isinstance(op.get("requestBody"), dict):
        body = resolve(doc, op["requestBody"])
        for media in (body.get("content") or {}).values():
            if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                schema = resolve(doc, media["schema"])
                break
    for prm in (op.get("parameters") or []):
        prm = resolve(doc, prm)
        if str(prm.get("in") or "").lower() == "body":
            schema = resolve(doc, prm.get("schema") or {})
            break
    if not isinstance(schema, dict):
        return []
    required = set(schema.get("required") or [])
    out = []
    for name, sub in (schema.get("properties") or {}).items():
        out.append((name, sub, name in required, "body"))
    return out


def spec_keys(api_dir):
    """The four key sets a developer-provided specification spells out."""
    keys = {t: set() for t, _ in TASKS}
    if not os.path.isdir(api_dir):
        return None
    files = sorted(f for f in os.listdir(api_dir) if f.lower().endswith(".json"))
    if not files:
        return None
    for fname in files:
        with io.open(os.path.join(api_dir, fname), encoding="utf-8") as fh:
            doc = json.load(fh)
        for raw_path, ops in (doc.get("paths") or {}).items():
            if not isinstance(ops, dict):
                continue
            for verb, op in ops.items():
                if verb.lower() not in HTTP_METHODS or not isinstance(op, dict):
                    continue
                ep = (path(raw_path), method(verb))
                keys["M"].add(ep)

                for prm in (op.get("parameters") or []):
                    prm = resolve(doc, prm)
                    name = str(prm.get("name") or "").strip()
                    if not name:
                        continue
                    sch = schema_of(doc, prm)
                    keys["P"].add(ep + (parameter_name(name), spec_type(doc, sch)))
                    add_constraints(keys, doc, ep, name, sch, prm.get("required"))
                    for item in [sch]:
                        if isinstance(item.get("items"), dict):
                            add_constraints(keys, doc, ep, name,
                                            item["items"], None)

                for name, sub, req, _pos in body_properties(doc, op):
                    keys["P"].add(ep + (parameter_name(name), spec_type(doc, sub)))
                    add_constraints(keys, doc, ep, name, sub, req)

                for code in (op.get("responses") or {}):
                    # Only a status the endpoint names. `default` answers
                    # whatever is not listed separately, and `5XX` names a range
                    # rather than a code, and neither can be matched against a
                    # response the pipeline reports.
                    code = str(code).strip()
                    if len(code) != 3 or not code.isdigit():
                        continue
                    keys["R"].add(ep + (status(code),))
    return keys


def align_prefix(dev, api_dir):
    """The base segment that puts the two sides of the comparison together.

    A developer's paths and the pipeline's paths can differ by a leading
    segment, the way /api/v1/pets and /pets do. The same trial RQ1 uses picks
    the one that lines the most entities up: every candidate is applied to both
    sides and the one with the most matches in common wins.
    """
    ours = E.load_pipeline(api_dir)
    if ours is None:
        return ""
    candidates = [""] + E.leading_segments(dev, ours)
    best, best_hits = "", -1
    for cand in candidates:
        got = E.load_pipeline(api_dir, cand)
        if got is None:
            continue
        hits = sum(len(strip_paths(dev, cand)[t] & got["keys"][t]) for t, _ in TASKS)
        if hits > best_hits:
            best, best_hits = cand, hits
    return best


def strip_paths(keys, prefix):
    if not prefix:
        return keys
    pre = "/" + prefix.strip("/")
    out = {t: set() for t, _ in TASKS}
    for t, _ in TASKS:
        for k in keys[t]:
            if k[0] == pre:
                out[t].add(("/",) + k[1:])
            elif k[0].startswith(pre + "/"):
                out[t].add((k[0][len(pre):],) + k[1:])
            else:
                out[t].add(k)
    return out


def gt_totals(gt_path):
    gt = E.load_gt(gt_path)
    out = {}
    for api, raw in gt.items():
        out[api] = {t: len(E.gt_keys(raw, t, "")[0]) for t, _ in TASKS}
    return out


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
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines).rstrip("\n") + "\n")
    return path


def ground_truth_totals(gt):
    """The ground truth's own count for each task: RQ2's denominator."""
    out = {t: 0 for t, _ in TASKS}
    for per_task in gt.values():
        for t, _ in TASKS:
            out[t] += per_task.get(t, 0)
    return out


def shares(totals, denom):
    """How much of the ground truth each side of the comparison is short by.

    The paper states RQ2 as the share of the ground truth that the pipeline
    recovered and the developer specifications did not, so the denominator is
    the ground truth's own count and not either side's.
    """
    out = {}
    for task, _ in TASKS:
        d = denom.get(task, 0)
        out[task] = (totals[task]["our"] - totals[task]["dev"]) / d if d else None
    return out


def summary_sentence(totals, denom):
    """The paper's RQ2 sentence, with this run's figures in it."""
    share = shares(totals, denom)
    labels = {"M": "endpoint methods", "P": "parameters",
              "C": "parameter constraints", "R": "responses"}
    clauses = []
    for task, _ in TASKS:
        if share[task] is None:
            continue
        value = share[task] * 100
        # The developer specifications can carry more of a task than the
        # pipeline did, and then the sentence has to say so rather than report
        # a negative quantity of "more".
        clauses.append("%.2f%% %s %s" % (abs(value),
                                         "more" if value >= 0 else "fewer",
                                         labels[task]))
    if not clauses:
        return "No task had a ground truth to measure against."
    known = [share[t] for t, _ in TASKS if share[t] is not None]
    average = sum(known) / len(known)
    body = ", ".join(clauses[:-1]) + ", and " + clauses[-1]
    return ("LRASGen recovers entities missing from developer-provided "
            "specifications: " + body
            + " (%.2f%% more entities on average)." % (average * 100))


def write_analysis(path, totals, denom, args):
    """What the run found, laid out in the order the paper states RQ2."""
    share = shares(totals, denom)
    lines = []
    lines.append("# RQ2: comparison against the developer-provided specifications")
    lines.append("")
    lines.append("`scripts/evaluate_rq2.py` reads the developer-provided "
                 "specifications under `%s` and the pipeline output under `%s`, "
                 "applies the same four keys to both sides, and counts how many "
                 "entities each one carries."
                 % (rel_path(args.specs), rel_path(args.output_root)))
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(summary_sentence(totals, denom))
    lines.append("")
    lines.append("## Per task")
    lines.append("")
    body = []
    for task, label in TASKS:
        d = denom.get(task, 0)
        o, v = totals[task]["our"], totals[task]["dev"]
        body.append([label, f"{o:,}", f"{v:,}", f"{o - v:+,}",
                     "-" if share[task] is None else "%.2f%%" % (share[task] * 100)])
    lines += md_table(["Task", "Ours", "Developer", "Difference",
                       "Relative to the ground truth"], body,
                      numeric=["Ours", "Developer", "Difference",
                               "Relative to the ground truth"])
    lines.append("")
    lines.append("The relative column divides the difference by the ground "
                 "truth's own count for the task (%s in total), which is the "
                 "quantity the paper reports. It does not divide by the "
                 "developer's count, because a specification that lists nothing "
                 "would make that ratio unbounded."
                 % ", ".join("%s %s" % (f"{denom[t]:,}", n) for t, n in
                             (("M", "methods"), ("P", "parameters"),
                              ("C", "constraints"), ("R", "responses"))))
    lines.append("")
    lines.append("## Reading")
    lines.append("")
    lines.append("The developer-provided specifications are a comparison target "
                 "and not a ground truth, so no entity on either side is "
                 "classified as right or wrong here. A developer who leaves an "
                 "entity out has documented less, not made a mistake, and a "
                 "positive difference counts what the pipeline reports and the "
                 "specification does not mention.")
    write_md(path, lines)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="RQ2: pipeline output vs developer specifications")
    ap.add_argument("--specs", default=DEFAULT_SPECS,
                    help="developer-provided specifications (default: %(default)s)")
    ap.add_argument("--output-root", default=DEFAULT_ROOT,
                    help="pipeline output root (default: %(default)s)")
    ap.add_argument("--gt", default=DEFAULT_GT,
                    help="ground truth whose totals are the denominator (default: %(default)s)")
    ap.add_argument("--out", default=os.path.join(REPO, "evaluation", "RQ2", "rq2_per_api.csv"),
                    help="where to write the table (default: %(default)s)")
    ap.add_argument("--analysis", default=None,
                    help="where the analysis document is written "
                         "(default: <out dir>/rq2_analysis.md)")
    ap.add_argument("--only", default=None, help="comma-separated API short names")
    args = ap.parse_args(argv)

    wanted = None
    if args.only:
        wanted = {n.strip().lower() for n in args.only.split(",") if n.strip()}

    gt = gt_totals(args.gt)

    totals = {t: {"our": 0, "dev": 0} for t, _ in TASKS}
    rows, missing_specs, missing_run = [], [], []
    for api in sorted(gt):
        if wanted is not None and api.lower() not in wanted:
            continue
        dev = spec_keys(os.path.join(args.specs, api))
        if dev is None:
            missing_specs.append(api)
            continue
        api_dir = os.path.join(args.output_root, api)
        loaded = E.load_pipeline(api_dir) if os.path.isdir(api_dir) else None
        if loaded is None:
            missing_run.append(api)
            continue
        best = align_prefix(dev, api_dir)
        dev = strip_paths(dev, best)
        ours = strip_paths(loaded["keys"], best)

        for task, label in TASKS:
            d, o = len(dev[task]), len(ours[task])
            totals[task]["dev"] += d
            totals[task]["our"] += o
            rows.append({"api": api, "task": task, "label": label,
                         "ours": o, "dev": d})

    # One file holds both readings: a row per API per task, then a row per task
    # totalling them. The API column says TOTAL on the rows that are totals, so
    # a reader can take either view out of the same table.
    out_dir = os.path.dirname(args.out)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with io.open(args.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["api", "task", "label", "ours", "dev"])
        w.writeheader()
        w.writerows(rows)
        for task, label in TASKS:
            w.writerow({"api": "TOTAL", "task": task, "label": label,
                        "ours": totals[task]["our"], "dev": totals[task]["dev"]})

    print("APIs compared   : %d" % len({r["api"] for r in rows}))
    if missing_specs:
        print("no developer spec: %s" % ", ".join(missing_specs))
    if missing_run:
        print("no pipeline run  : %s" % ", ".join(missing_run))
    print()
    print("%-24s %10s %10s" % ("task", "ours", "dev"))
    print("-" * 46)
    for task, label in TASKS:
        print("%-24s %10d %10d" % (label, totals[task]["our"], totals[task]["dev"]))

    analysis_path = (args.analysis
                     or os.path.join(os.path.dirname(args.out) or ".", "rq2_analysis.md"))
    write_analysis(analysis_path, totals, ground_truth_totals(gt), args)

    print()
    print("%d API rows + %d total rows : %s" % (len(rows), len(TASKS), args.out))
    print("analysis         : %s" % analysis_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
