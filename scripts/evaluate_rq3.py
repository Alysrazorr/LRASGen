"""RQ3: the four identification tasks, counted for the pipeline and for Respector.

The counting is RQ2's, applied to a different comparison target. Every entity
the pipeline reports and every entity Respector reports is put through the same
four keys RQ1 uses, and the two counts are laid side by side, per API and per
task.

    task                     ours      resp
    Endpoint Methods         1208      1143
    ...

Respector is a Java static-analysis tool and produces a result for 27 of the 53
subject APIs, so those 27 are the APIs with a row. The others are named in the
run and left out. No true/false classification is involved: Respector's output
is a comparison target, not a ground truth, so a result it omits is a result it
could not derive, not one it got wrong.

The figures the paper reports for RQ3 are the share of the pipeline's own
entities that Respector did not report, summed over all 53 APIs:

    (Ours - Resp) / Ours

The denominator is the pipeline's count over all 53, not over the 27 Respector
covers, which is what makes "LRASGen applies to all 53 APIs, whereas Respector
applies to only 27" a statement about the same figure.

Respector's output is regenerated from its official replication package and is
not produced here. See EVALUATION.md, section 7.

    python scripts/evaluate_rq3.py
    python scripts/evaluate_rq3.py --only Actuator,Digdag
"""

import argparse
import csv
import io
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
import evaluate_rq2 as E2

DEFAULT_RESPECTOR = os.path.join(REPO, "specs", "respector_generated")
DEFAULT_ROOT = os.path.join(REPO, "output", "lrasgen_generated")
DEFAULT_GT = os.path.join(REPO, "GTa.xlsx")

TASKS = E2.TASKS


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


def summary_sentence(whole, covered, n_all, n_resp):
    """The paper's RQ3 sentence, with this run's figures in it.

    The share is measured against the pipeline's own count over every API it
    covers, which is what makes the closing clause a statement about the same
    figure: Respector contributes nothing on the APIs it cannot analyse.
    """
    labels = {"M": "methods", "P": "parameters",
              "C": "constraints", "R": "responses"}
    clauses = []
    for task, _ in TASKS:
        o = whole.get(task, 0)
        if not o:
            continue
        clauses.append("%.2f%% (%s)" % ((o - covered[task]["resp"]) / o * 100,
                                        labels[task]))
    if not clauses:
        return "No task had a Respector result to compare against."
    body = ", ".join(clauses[:-1]) + ", and " + clauses[-1]
    return ("LRASGen outperforms Respector by " + body
            + ", and applies to all %d APIs, whereas Respector applies to only "
              "%d." % (n_all, n_resp))


def write_analysis(path, whole, covered, n_all, rows, args):
    """What the run found, laid out in the order the paper states RQ3."""
    n_resp = len({r["api"] for r in rows})
    lines = []
    lines.append("# RQ3: comparison against Respector")
    lines.append("")
    lines.append("`scripts/evaluate_rq3.py` reads Respector's output under `%s` and "
                 "the pipeline output under `%s`, applies the same four keys to "
                 "both sides, and counts how many entities each one carries."
                 % (rel_path(args.respector), rel_path(args.output_root)))
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(summary_sentence(whole, covered, n_all, n_resp))
    lines.append("")
    lines.append("## Per task")
    lines.append("")
    body = []
    for task, label in TASKS:
        o, r = whole.get(task, 0), covered[task]["resp"]
        body.append([label, f"{o:,}", f"{covered[task]['our']:,}", f"{r:,}",
                     "-" if not o else "%.2f%%" % ((o - r) / o * 100)])
    lines += md_table(["Task", "Ours (53 APIs)", "Ours (the %d)" % n_resp,
                       "Respector", "Outperforms by"], body,
                      numeric=["Ours (53 APIs)", "Ours (the %d)" % n_resp,
                               "Respector", "Outperforms by"])
    lines.append("")
    lines.append("The share is the pipeline's count over all %d APIs minus "
                 "Respector's count, divided by the pipeline's count. The "
                 "denominator covers every API because the pipeline covers every "
                 "API: Respector contributes nothing on the APIs it cannot "
                 "analyse, so its column is empty there and the difference is "
                 "the whole of what the pipeline reported on those." % n_all)
    lines.append("")

    lines.append("## The APIs Respector covers")
    lines.append("")
    lines.append("Respector is a Java static-analysis tool. It produced a result "
                 "for %d of the %d subject APIs:" % (n_resp, n_all))
    lines.append("")
    names = sorted({r["api"] for r in rows})
    for i in range(0, len(names), 6):
        lines.append("- " + ", ".join(names[i:i + 6]))
    lines.append("")

    lines.append("## Reading")
    lines.append("")
    lines.append("Respector's output is a comparison target and not a ground "
                 "truth, so no entity on either side is classified as right or "
                 "wrong here. A result Respector omits is one it could not "
                 "derive from the source it analyses, and the gap on the APIs it "
                 "does cover is where the two approaches read the same code "
                 "differently. The constraint column is the widest gap, which "
                 "follows from what each side can see: Respector derives "
                 "constraints from what the project compiles into the API, and "
                 "the pipeline reads them off the handler, the annotations, and "
                 "the classes the request names.")
    write_md(path, lines)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="RQ3: pipeline output vs Respector output")
    ap.add_argument("--respector", default=DEFAULT_RESPECTOR,
                    help="Respector's own output (default: %(default)s)")
    ap.add_argument("--output-root", default=DEFAULT_ROOT,
                    help="pipeline output root (default: %(default)s)")
    ap.add_argument("--gt", default=DEFAULT_GT,
                    help="the ground truth whose sheet list names the subject APIs "
                         "(default: %(default)s)")
    ap.add_argument("--out", default=os.path.join(REPO, "evaluation", "RQ3", "rq3_per_api.csv"),
                    help="where to write the table (default: %(default)s)")
    ap.add_argument("--analysis", default=None,
                    help="where the analysis document is written "
                         "(default: <out dir>/rq3_analysis.md)")
    ap.add_argument("--only", default=None, help="comma-separated API short names")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.respector):
        print("error: Respector output not found: %s" % args.respector, file=sys.stderr)
        print("Regenerate it from Respector's replication package; see EVALUATION.md "
              "section 7.", file=sys.stderr)
        return 1

    wanted = None
    if args.only:
        wanted = {n.strip().lower() for n in args.only.split(",") if n.strip()}

    covered = {t: {"our": 0, "resp": 0} for t, _ in TASKS}   # the APIs with a row
    whole = {t: 0 for t, _ in TASKS}                          # the pipeline over all
    n_all = 0
    rows, missing_resp, missing_run = [], [], []

    for api in sorted(E.load_gt(args.gt)):
        if wanted is not None and api.lower() not in wanted:
            continue

        api_dir = os.path.join(args.output_root, api)
        loaded = E.load_pipeline(api_dir) if os.path.isdir(api_dir) else None
        if loaded is None:
            missing_run.append(api)
            continue
        n_all += 1
        for task, _ in TASKS:
            whole[task] += len(loaded["keys"][task])

        resp = E2.spec_keys(os.path.join(args.respector, api))
        if resp is None:
            missing_resp.append(api)
            continue

        best = E2.align_prefix(resp, api_dir)
        resp = E2.strip_paths(resp, best)
        ours = E2.strip_paths(loaded["keys"], best)

        for task, label in TASKS:
            o, r = len(ours[task]), len(resp[task])
            covered[task]["our"] += o
            covered[task]["resp"] += r
            rows.append({"api": api, "task": task, "label": label,
                         "ours": o, "resp": r})

    out_dir = os.path.dirname(args.out)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with io.open(args.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["api", "task", "label", "ours", "resp"])
        w.writeheader()
        w.writerows(rows)
        for task, label in TASKS:
            w.writerow({"api": "TOTAL", "task": task, "label": label,
                        "ours": covered[task]["our"], "resp": covered[task]["resp"]})

    n_apis = len({r["api"] for r in rows})
    print("APIs with Respector output : %d" % n_apis)
    if missing_resp:
        print("no Respector output       : %s" % ", ".join(missing_resp))
    if missing_run:
        print("no pipeline run           : %s" % ", ".join(missing_run))
    print()
    print("%-24s %10s %10s" % ("task", "ours", "resp"))
    print("-" * 46)
    for task, label in TASKS:
        print("%-24s %10d %10d" % (label, covered[task]["our"], covered[task]["resp"]))

    # What the paper reports: the share of the pipeline's entities, over all 53
    # APIs, that Respector did not report. Respector contributes nothing on the
    # APIs it cannot analyse, so its column is zero there.
    print()
    print("RQ3, over all %d APIs: (Ours - Resp) / Ours" % n_all)
    print("%-24s %10s %10s %10s" % ("task", "Ours", "Resp", "by"))
    print("-" * 58)
    for task, label in TASKS:
        o = whole[task]
        r = covered[task]["resp"]
        pct = (o - r) / o * 100 if o else 0.0
        print("%-24s %10d %10d %9.2f%%" % (label, o, r, pct))

    analysis_path = (args.analysis
                     or os.path.join(os.path.dirname(args.out) or ".", "rq3_analysis.md"))
    write_analysis(analysis_path, whole, covered, n_all, rows, args)

    print()
    print("%d API rows + %d total rows : %s" % (len(rows), len(TASKS), args.out))
    print("analysis         : %s" % analysis_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
