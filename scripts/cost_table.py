"""Build the runtime / token / cost table for the 53 subject APIs.

Reads the pipeline output written by `run_all_apis` under
output/lrasgen_generated/<API>/ and emits the table in the layout the response
letter specifies:

    one row per API, three model groups of (tokens, WC time, USD cost),
    plus a Total row and an Average row.

Per-model tokens and USD costs come from the `tokens.by_model` field that
`src/llm.py` writes into every step file. WC time is the time spent inside that
model's own calls; older output that carries no per-model timing falls back to
the step's wall-clock time, which then appears in all three columns.

Usage:
    python scripts/cost_table.py
    python scripts/cost_table.py --root output/lrasgen_generated --out output
"""

import argparse
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Provider key -> display name, in the column order of the table.
MODELS = [
    ("gpt", "GPT-5.4-mini"),
    ("deepseek", "DeepSeek V4 Flash"),
    ("gemini", "Gemini 3.1 Flash Lite"),
]

STEPS = ("step3_endpoints", "step4_details", "step5_constraints")


def api_order():
    """Short names in Table 1 order, read from MANIFEST.md; folder names if absent."""
    manifest = os.path.join(REPO, "MANIFEST.md")
    if os.path.exists(manifest):
        names = []
        with open(manifest, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^\| \d+ \| ([^|]+?) \|", line)
                if m:
                    names.append(m.group(1).strip())
        if names:
            return names
    return None


def run_dirs(root, api):
    """The directories holding one API's run(s).

    A plain run writes its step files straight into ``root/<api>``. An API whose
    code is split across several sources, such as Bitwarden, gets one
    subdirectory per source instead, and those are summed into one row.
    """
    d = os.path.join(root, api)
    if not os.path.isdir(d):
        return []
    subs = [os.path.join(d, s) for s in sorted(os.listdir(d))
            if os.path.isdir(os.path.join(d, s))]
    return subs or [d]


def collect(path):
    """Sum one run directory's per-model tokens, costs and time.

    `elapsed_s` is the time spent inside that model's own calls. Older run output
    has no such field; `wc_seconds` (the step's wall-clock time) is then the only
    time available, and `per_model_time` stays False.
    """
    row = {
        p: {"tokens": 0, "cost_usd": 0.0, "calls": 0, "elapsed_s": 0.0}
        for p, _ in MODELS
    }
    row["wc_seconds"] = 0.0
    row["per_model_time"] = False
    row["complete"] = True

    for step in STEPS:
        f = os.path.join(path, step + ".json")
        if not os.path.exists(f):
            row["complete"] = False
            continue
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        usage = data.get("tokens") or {}
        by_name = {m.get("name"): m for m in (usage.get("by_model") or [])}
        for p, _ in MODELS:
            u = by_name.get(p) or {}
            row[p]["tokens"] += u.get("total_tokens", 0)
            row[p]["cost_usd"] += u.get("total_cost_usd", 0.0)
            row[p]["calls"] += u.get("calls", 0)
            row[p]["elapsed_s"] += u.get("elapsed_s", 0.0)
            if u.get("elapsed_s"):
                row["per_model_time"] = True
        row["wc_seconds"] += (data.get("duration_ms") or 0) / 1000.0
    return row


def merge(a, b):
    """Combine two runs of the same API (Bitwarden is run once per repository)."""
    for p, _ in MODELS:
        for k in ("tokens", "cost_usd", "calls", "elapsed_s"):
            a[p][k] += b[p][k]
    a["wc_seconds"] += b["wc_seconds"]
    a["per_model_time"] = a["per_model_time"] or b["per_model_time"]
    a["complete"] = a["complete"] and b["complete"]
    return a


def sum_rows(rows):
    total = {p: {"tokens": 0, "cost_usd": 0.0, "calls": 0, "elapsed_s": 0.0}
             for p, _ in MODELS}
    total["wc_seconds"] = 0.0
    for r in rows:
        for p, _ in MODELS:
            for k in ("tokens", "cost_usd", "calls", "elapsed_s"):
                total[p][k] += r[p][k]
        total["wc_seconds"] += r["wc_seconds"]
    return total


def wc_of(row, provider):
    """The wall-clock figure for one model column."""
    if row.get("per_model_time"):
        return row[provider]["elapsed_s"]
    return row["wc_seconds"]


def fmt_int(n):
    return f"{n:,}"


def fmt_cost(v):
    return f"{v:.2f}"


def fmt_wc(sec):
    return f"{sec:.1f}"


def build_markdown(table):
    head = "| API | " + " | ".join(
        f"{n} tokens | {n} WC time (s) | {n} USD" for _, n in MODELS) + " |"
    sep = "|---|" + "---|" * (3 * len(MODELS))
    lines = [head, sep]
    for api, row in table["rows"]:
        cells = [api]
        for p, _ in MODELS:
            cells += [fmt_int(row[p]["tokens"]), fmt_wc(wc_of(row, p)),
                      fmt_cost(row[p]["cost_usd"])]
        lines.append("| " + " | ".join(cells) + " |")
    for label, key in (("**Total**", "total"), ("**Average**", "average")):
        row = table[key]
        cells = [label]
        for p, _ in MODELS:
            cells += [fmt_int(row[p]["tokens"]), fmt_wc(wc_of(row, p)),
                      fmt_cost(row[p]["cost_usd"])]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=os.path.join(REPO, "output", "lrasgen_generated"),
                    help="pipeline output root (default: output/lrasgen_generated)")
    ap.add_argument("--out", default=os.path.join(REPO, "output"),
                    help="directory for the generated .md (default: output)")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.root):
        print(f"error: {args.root} does not exist", file=sys.stderr)
        return 1

    order = api_order() or sorted(
        d for d in os.listdir(args.root) if os.path.isdir(os.path.join(args.root, d)))

    rows = []
    missing = []
    for api in order:
        dirs = run_dirs(args.root, api)
        if not dirs:
            missing.append(api)
            continue
        merged = collect(dirs[0])
        for extra in dirs[1:]:                      # e.g. Bitwarden runs twice
            merged = merge(merged, collect(extra))
        rows.append((api, merged))

    if not rows:
        print("error: no pipeline output found under %s" % args.root, file=sys.stderr)
        return 1

    per_model_time = any(r["per_model_time"] for _, r in rows)

    total = sum_rows([r for _, r in rows])
    total["per_model_time"] = per_model_time
    average = {p: {"tokens": round(total[p]["tokens"] / len(rows)),
                   "cost_usd": total[p]["cost_usd"] / len(rows),
                   "calls": round(total[p]["calls"] / len(rows)),
                   "elapsed_s": total[p]["elapsed_s"] / len(rows)}
               for p, _ in MODELS}
    average["wc_seconds"] = total["wc_seconds"] / len(rows)
    average["per_model_time"] = per_model_time

    table = {"rows": rows, "total": total, "average": average}

    incomplete = [a for a, r in rows if not r["complete"]]
    if incomplete:
        print("warning: %d API(s) have incomplete step output: %s"
              % (len(incomplete), ", ".join(incomplete)), file=sys.stderr)
    if missing:
        print("warning: no output for: %s" % ", ".join(missing), file=sys.stderr)

    os.makedirs(args.out, exist_ok=True)
    md = os.path.join(args.out, "cost_table.md")
    with open(md, "w", encoding="utf-8") as f:
        f.write(build_markdown(table) + "\n")

    print(build_markdown(table))
    print()
    print("written: %s" % md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
